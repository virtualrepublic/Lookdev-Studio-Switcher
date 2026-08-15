"""Shared plumbing for the test suite. Standard library only, no Blender.

The toolchain is not a package -- `tools/` holds loose scripts that import each
other by bare name. So the path is put together here once, in the one place
that has to know, rather than in every test module.
"""

import os
import sys
import types

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)
TOOLS = os.path.join(REPO, "tools")

if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import make_migration as mm        # noqa: E402  (path set up above)
import compare_scenes as cs        # noqa: E402


def repo_path(*parts):
    """A path inside the repository, whatever the working directory is."""
    return os.path.join(REPO, *parts)


def quiet():
    """Swallow stdout. The toolchain and the generated code both report freely.

    Used where the output is not what is being asserted. Where it IS -- the
    deferred colour space prints rather than logs, on purpose -- capture it
    instead and assert on it.
    """
    import contextlib
    import io

    return contextlib.redirect_stdout(io.StringIO())


def read_text(*parts):
    with open(repo_path(*parts), encoding="utf-8") as handle:
        return handle.read()


def read_bytes(*parts):
    with open(repo_path(*parts), "rb") as handle:
        return handle.read()


def generate(changes, before=None, after=None, **kwargs):
    """Run the real generator over a list of changes, return the source text.

    Deliberately `build()` + `render()` and not `main()`: main() parses argv,
    reads snapshot files from disk and refuses to run unless their dumper stamp
    matches the current dump_scene.py. That check has its own tests
    (test_stamps.py); dragging it into every generator test would mean writing a
    stamped snapshot pair to disk for each one.
    """
    before = before or {}
    after = after or {}
    emitter = mm.build(before, after, changes)
    return mm.render(emitter, before, after, **kwargs)


def generate_from_snapshots(before, after, **kwargs):
    """Two snapshots -> the generated source, through the real differ.

    Use this instead of `generate()` whenever what is under test involves the
    diff itself -- the shape of the paths, above all. `generate()` takes the
    changes ready-made and would not notice a differ that mangles them.
    """
    return generate(cs.diff(before, after), before, after, **kwargs)


def run_generated(source, bpy, scene=None, migrate=True):
    """Execute a generated script once, the way Text Editor > Run Script does.

    Returns (module, changes) -- the module so a test can reach a single
    generated function, the change list because that is what the run reports.

    One run, one fresh module, on purpose. The generated `_changes` list is a
    module global and nothing resets it, so calling migrate() twice on the same
    module would accumulate and every idempotence test would be wrong in the
    direction that looks like a pass. Blender executes the file again from
    scratch; `run_twice()` below does the same.
    """
    import contextlib
    import io

    import fakebpy

    module = types.ModuleType("generated_migration")
    module.__file__ = "<generated>"
    printed = io.StringIO()
    with fakebpy.installed(bpy):
        # The generated script prints its progress. Captured rather than let
        # loose, so a failing assertion is readable -- and because some of what
        # it reports is printed instead of logged on purpose (a change that has
        # not happened yet must not show up in the count).
        with contextlib.redirect_stdout(printed):
            exec(compile(source, "<generated>", "exec"), module.__dict__)
            changes = module.migrate(scene) if migrate else None
    module.printed = printed.getvalue()
    return module, changes


def run_twice(source, bpy, scene=None):
    """Two separate runs against the same fake scene. Returns both change lists.

    "Run it, then run it again -- the second must report 0 change(s) applied"
    is the check that catches a step which assigns without comparing, and it is
    in docs/MAINTAINING.md as a property to keep. This is that check.
    """
    _first_module, first = run_generated(source, bpy, scene)
    _second_module, second = run_generated(source, bpy, scene)
    return first, second


def scene_change(section, prop, new, old=None, scene="Scene"):
    """One `scenes.<name>.<section>.<prop>` change, as the differ reports it.

    `section` may carry one dot -- "render.image_settings" -- which produces the
    five-element path the generator expects for a nested settings block.
    """
    path = ("scenes", scene) + tuple(section.split(".")) + (prop,)
    return ("changed", path, old, new)


def lines_of(source):
    """The generated source split into stripped lines, comments dropped.

    Order assertions are about emitted statements. A phase heading or a comment
    landing between them says nothing, and matching on raw text would make the
    tests fail on a reworded comment.
    """
    out = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            out.append(stripped)
    return out


def migrate_body(source):
    """Only the lines inside migrate(), where execution order is the question.

    A generated file is helpers first, then migrate(). `relink` and
    `compositor_tree` are *defined* near the top and *called* far below, so a
    naive search for "relink(" finds the definition and reports the call as
    happening before the nodes are made -- which is how this helper came to
    exist. Order assertions must look at the body, not the file.
    """
    body = lines_of(source)
    for number, line in enumerate(body):
        if line.startswith("def migrate("):
            return body[number:]
    return body


def index_of(source, needle, whole_file=False):
    """Position of the first line inside migrate() containing `needle`, or -1.

    Used for "A must be emitted before B" assertions. Pass whole_file=True to
    search the helpers and the embedded blocks as well.
    """
    haystack = lines_of(source) if whole_file else migrate_body(source)
    for number, line in enumerate(haystack):
        if needle in line:
            return number
    return -1

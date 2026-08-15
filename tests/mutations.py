"""Put each fixed defect back and check that its test notices.

Every bug in the table in docs/MAINTAINING.md was fixed years before these
tests existed, so no test here can ever have been red for the reason it claims.
A green suite therefore proves that the tests run -- not that they check
anything. This closes that gap: each mutation is the defect reintroduced, in
one edit, and the test that guards it must fail while the mutation is in place.

    python tests/mutations.py            all of them
    python tests/mutations.py log-line   one

Three runs per mutation: clean (must pass -- otherwise nothing is proved),
mutated (must fail), restored (must pass again, so a crashed run cannot leave
the tree edited without saying so). The source file is restored in a finally
block and byte for byte, line endings included.

NOT part of the CI run on every push. It rewrites tracked source files, and the
question it answers -- do these tests still discriminate -- only comes up when
somebody changes the tests or the generator, not on every commit.
"""

import os
import shutil
import subprocess
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)


class Mutation:
    """One defect, put back with a single textual replacement."""

    def __init__(self, key, defect, relative_path, old, new, tests, symptom):
        self.key = key
        self.defect = defect
        self.path = os.path.join(REPO, *relative_path.split("/"))
        self.old = old.encode("utf-8")
        self.new = new.encode("utf-8")
        self.tests = tests
        self.symptom = symptom

    def apply(self):
        """Returns the original bytes, for the caller to hand back to restore()."""
        with open(self.path, "rb") as handle:
            original = handle.read()
        found = original.count(self.old)
        if found != 1:
            raise SystemExit(
                "mutation %r does not apply: its anchor occurs %d times in %s.\n"
                "The file changed under it. Fix the anchor before trusting any\n"
                "of this -- a mutation that cannot be applied proves nothing."
                % (self.key, found, os.path.relpath(self.path, REPO)))
        with open(self.path, "wb") as handle:
            handle.write(original.replace(self.old, self.new))
        return original

    def restore(self, original):
        with open(self.path, "wb") as handle:
            handle.write(original)


MUTATIONS = [
    Mutation(
        key="log-line",
        defect="1  raw value interpolated into a generated log(\"...\")",
        relative_path="tools/make_migration.py",
        old="""    return '%slog(%s)' % (indent, lit(message))""",
        new="""    return '%slog("%s")' % (indent, message)""",
        tests=["test_generated_source.BackslashInALoggedValue"],
        symptom="a trailing backslash ends the string early -- the generated "
                "file does not parse at all",
    ),
    Mutation(
        key="name-pointers",
        defect="3  pointer-with-.name written as a plain string",
        relative_path="tools/make_migration.py",
        old='NAME_POINTERS = ("linear_colorspace_settings",)',
        new="NAME_POINTERS = ()",
        tests=["test_generated_source.NamePointersAreWrittenThroughName"],
        symptom="ACEScg silently never set -- TypeError swallowed by the "
                "generated except",
    ),
    Mutation(
        key="dotted-paths",
        defect="4  dotted path splitting",
        relative_path="tools/compare_scenes.py",
        old="            sub = path + (str(key),)",
        new='            sub = tuple(".".join(path + (str(key),)).split("."))',
        tests=["test_diff_paths"],
        symptom="GPM.005 truncated to GPM -- the generated .get() finds nothing "
                "and the step silently does nothing",
    ),
    Mutation(
        key="scene-order",
        defect="5  scene properties written alphabetically",
        relative_path="tools/make_migration.py",
        old="    for section, prop, value in sorted(scene_props, key=order):",
        new="    for section, prop, value in scene_props:",
        tests=["test_generated_source.SceneOrderIsDefinedNotAlphabetical"],
        symptom="look before view_transform, media_type after file_format -- "
                "refused, caught, logged as skipped",
    ),
    Mutation(
        key="phase-order",
        defect="7  compositor links emitted before the nodes",
        relative_path="tools/make_migration.py",
        old='              "compositor_nodes", "compositor_links")',
        new='              "compositor_links", "compositor_nodes")',
        tests=["test_generated_source.CompositorNodesBeforeLinks"],
        symptom="links hang in the void -- relink() names nodes nothing has "
                "created yet",
    ),
    Mutation(
        key="float-tolerance",
        defect="8  float32 in the scene against float64 from the snapshot",
        relative_path="tools/make_migration.py",
        old="    if isinstance(value, float):\n"
            "        return ('if abs(%s - %s) > max(1e-6, abs(%s) * 1e-6):'",
        new="    if False:\n"
            "        return ('if abs(%s - %s) > max(1e-6, abs(%s) * 1e-6):'",
        tests=["test_generated_source.FloatsAreComparedWithATolerance"],
        symptom="0.01 != 0.009999999776482582 for ever -- values rewritten on "
                "every run, a second run never reaches 0 changes",
    ),
    Mutation(
        key="except-type",
        defect="2  only TypeError caught around a generated assignment",
        relative_path="tools/make_migration.py",
        old="        'except (AttributeError, TypeError) as exc:',",
        new="        'except TypeError as exc:',",
        tests=["test_runtime.AReadOnlyPropertyDoesNotKillTheRun"],
        symptom="a read-only property raises AttributeError and kills the "
                "whole run, half converted",
    ),
    Mutation(
        key="focus-unconditional",
        defect="6  focus_object set without comparing first",
        relative_path="tools/make_migration.py",
        old="        'if data and target and data.dof.focus_object is not target:',",
        new="        'if data and target:',",
        tests=["test_runtime.ASecondRunChangesNothing"],
        symptom="the second run reports a change, so the one property that "
                "catches blind assignment stops working",
    ),
    Mutation(
        key="rename-phase-last",
        defect="13 renames emitted after the phases that use the new names",
        relative_path="tools/make_migration.py",
        old='              "renames", "camera_data", "objects", "focus",',
        new='              "camera_data", "objects", "focus", "renames",',
        tests=["test_runtime.ARenamedCameraDataBlockIsRenamedFirst"],
        symptom="a renamed camera keeps its original lens, sensor and DOF "
                "values on the first run, silently",
    ),
    Mutation(
        key="delete-inline",
        defect="9  workspaces deleted inside the running script",
        relative_path="tools/make_migration.py",
        old="        bpy.app.timers.register(again, first_interval=0.5)",
        new="        again()",
        tests=["test_deferred.WorkspacesAreDeletedFromATimer"],
        symptom="deleting frees the area the script is running in; Blender "
                "dies in ED_area_type_hud_clear when the operator finishes",
    ),
    Mutation(
        key="convert-inline",
        defect="10 working colour space converted inside the script",
        relative_path="tools/make_migration.py",
        old="        bpy.app.timers.register(run, first_interval=0.5)",
        new="        run()",
        tests=["test_deferred.TheColourSpaceIsNeverConvertedInline"],
        symptom="the undo push reallocates every data-block while a queued "
                "workspace switch holds the old address -- crash in "
                "wm_event_do_notifiers, after the script",
    ),
    Mutation(
        key="viewer-view-all",
        defect="11 image.view_all(fit_view=True) instead of setting the image",
        relative_path="tools/make_migration.py",
        old="    for space in area.spaces:\n"
            "        if space.type == 'IMAGE_EDITOR':\n"
            "            space.image = image",
        new="    bpy.ops.image.view_all(fit_view=True)",
        tests=["test_deferred.TheImageEditorIsPointedNotZoomed"],
        symptom="a 256x256 placeholder zoomed to fill the editor",
    ),
    Mutation(
        key="notes-encoding",
        defect="-- release notes written to gh in a lossy encoding",
        relative_path="tools/new-release.ps1",
        old="Set-Content -Path $notesFile.FullName -Value $notes -Encoding utf8",
        new="Set-Content -Path $notesFile.FullName -Value $notes -Encoding ascii",
        tests=["test_release_notes.TheNotesReachGitHubIntact"],
        symptom="every arrow in the four-step instructions becomes a question "
                "mark on the Releases page",
    ),
    Mutation(
        key="release-notes-cut",
        defect="12  release notes cut at any \"## \"",
        relative_path="tools/new-release.ps1",
        old=r"(?=^\#\#\s*\[|\z)",
        new=r"(?=^\#\#\s|\z)",
        tests=["test_release_notes.AnEntryIsCutAtTheNextVersion"],
        symptom="a version's own sub-heading truncates the published page -- "
                "v1.0.0 went out as two lines",
    ),
]


def run(tests):
    """Run the given unittest targets. Returns (passed, output)."""
    # A stale .pyc next to a file that was just rewritten would run the old
    # code and report a mutation as uncaught.
    shutil.rmtree(os.path.join(REPO, "tools", "__pycache__"), ignore_errors=True)
    shutil.rmtree(os.path.join(TESTS_DIR, "__pycache__"), ignore_errors=True)
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "-v"] + list(tests),
        cwd=TESTS_DIR, capture_output=True, text=True)
    return result.returncode == 0, result.stdout + result.stderr


def failures(output):
    """The test names unittest reported as FAIL or ERROR."""
    out = []
    for line in output.splitlines():
        if line.startswith(("FAIL: ", "ERROR: ")):
            out.append(line.split(" ", 1)[1].strip())
    return out


def check(mutation, verbose=False):
    """Clean, mutated, restored. Returns True when the mutation was caught."""
    print("=" * 74)
    print("  defect %s" % mutation.defect)
    print("  mutation %r in %s"
          % (mutation.key, os.path.relpath(mutation.path, REPO)))
    print("  symptom  %s" % mutation.symptom)
    print("-" * 74)

    passed, output = run(mutation.tests)
    if not passed:
        print("  !! the guard is already red before the mutation -- nothing is")
        print("     proved by making it redder. Fix the test first.")
        if verbose:
            print(output)
        return False
    print("  clean    pass")

    original = mutation.apply()
    try:
        passed, output = run(mutation.tests)
    finally:
        mutation.restore(original)

    caught = not passed
    if caught:
        names = failures(output)
        print("  mutated  FAIL -- caught by %d test(s):" % len(names))
        for name in names:
            print("             %s" % name)
    else:
        print("  mutated  pass  <-- NOT CAUGHT. The guard does not check this.")
    if verbose:
        print(output)

    passed_again, output = run(mutation.tests)
    if not passed_again:
        print("  !! restored, but still red -- the file may not be back as it")
        print("     was. Check `git diff` before going on.")
        print(output)
        return False
    print("  restored pass")
    return caught


def main(argv):
    verbose = "-v" in argv
    wanted = [a for a in argv if not a.startswith("-")]
    chosen = [m for m in MUTATIONS if not wanted or m.key in wanted]
    unknown = set(wanted) - {m.key for m in MUTATIONS}
    if unknown:
        raise SystemExit("unknown mutation(s): %s\nknown: %s"
                         % (", ".join(sorted(unknown)),
                            ", ".join(m.key for m in MUTATIONS)))

    results = [(m, check(m, verbose)) for m in chosen]

    print("=" * 74)
    uncaught = [m for m, caught in results if not caught]
    for mutation, caught in results:
        print("  %-16s %s" % (mutation.key, "caught" if caught else "NOT CAUGHT"))
    print("-" * 74)
    print("  %d of %d mutations caught" % (len(results) - len(uncaught), len(results)))
    return 1 if uncaught else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

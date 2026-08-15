"""Defects 9, 10 and 11 -- the three whose symptoms cannot be reproduced here.

Read this before trusting anything in it.

The recorded symptoms are:

  9   EXCEPTION_ACCESS_VIOLATION in ED_area_type_hud_clear, because deleting a
      workspace freed the screen area that bpy.ops.text.run_script() was about
      to build its redo panel for.
  10  EXCEPTION_ACCESS_VIOLATION in wm_event_do_notifiers, because the undo
      push for the colour conversion reallocated every data-block while a
      queued workspace switch still held the old address.
  11  a 256x256 placeholder zoomed to fill the image editor.

None of that can happen here. A fake bpy has no screens to free, no undo stack,
no notifier queue, no redo panel and no zoom. **These tests cannot show that
Blender does not crash.** What they check is narrower and worth saying plainly:
that the code still keeps the promise the fix was built on -- deletion and
conversion happen from a timer and not during the run, and the image editor is
pointed at a datablock rather than zoomed by an operator.

They are regression guards against the fix being undone. Read as anything more
they would be a lie, which is why this is at the top of the file rather than in
a commit message.

One thing here IS a real test rather than a guard: the precondition under which
deferring the colour conversion is safe at all -- that the migration writes no
colour anywhere -- is a statement about generated output, and it is checked.
"""

import ast
import contextlib
import io
import os
import tempfile
import unittest

import fakebpy
from _support import generate, mm, quiet, run_generated

WORKING_SPACE_CHANGE = [("changed", ("blend_file_settings", "working_space"),
                         "Linear Rec.709", "ACEScg")]


class TheColourSpaceIsNeverConvertedInline(unittest.TestCase):
    """Defect 10, as far as it can be reached.

    `bpy.data.colorspace.working_space` is read-only and the operator that
    changes it rewrites every colour in the file. Called as a phase it killed
    Blender after the script had finished. It now waits on a flag the workspace
    chain sets and converts in a tick of its own.
    """

    def a_run(self, target='ACEScg', start='Linear Rec.709'):
        bpy = fakebpy.make()
        bpy.data.colorspace.force("working_space", start)
        source = generate(WORKING_SPACE_CHANGE)
        module, changes = run_generated(source, bpy)
        return bpy, module, changes

    def converting_handler(self):
        """An operator that actually does the conversion, as Blender's does."""
        def handler(bpy, *args, **kwargs):
            bpy.data.colorspace.force("working_space", kwargs["working_space"])
        return handler

    def test_nothing_is_converted_while_the_script_runs(self):
        bpy, _module, _changes = self.a_run()
        self.assertEqual(bpy.ops.called("wm.set_working_color_space"), [],
                         "the operator ran inside the script")
        self.assertEqual(bpy.data.colorspace.working_space, 'Linear Rec.709')

    def test_it_is_queued_on_a_timer(self):
        bpy, _module, _changes = self.a_run()
        self.assertEqual(len(bpy.app.timers.registered), 1,
                         "expected exactly one deferred step")

    def test_a_queued_change_is_not_counted_as_applied(self):
        # Printed, not logged, and on purpose: nothing has happened yet, and a
        # change that has not happened must not show up in "n change(s)".
        _bpy, module, changes = self.a_run()
        self.assertEqual(changes, [])
        self.assertIn("queued", module.printed)

    def test_firing_the_timer_converts(self):
        bpy = fakebpy.make()
        bpy.data.colorspace.force("working_space", 'Linear Rec.709')
        bpy.ops.handlers["wm.set_working_color_space"] = self.converting_handler()
        module, changes = run_generated(generate(WORKING_SPACE_CHANGE), bpy)
        with quiet():
            bpy.app.timers.fire()
        self.assertEqual(bpy.data.colorspace.working_space, 'ACEScg')
        call, = bpy.ops.called("wm.set_working_color_space")
        self.assertTrue(call[2]["convert_colors"],
                        "without convert_colors the label changes and the "
                        "numbers stay -- it reinterprets instead of converting")
        self.assertIn("all colours converted", "\n".join(changes))

    def test_an_operator_that_declines_is_not_reported_as_success(self):
        # bpy.ops raises only when the poll fails. The fake's default operator
        # returns {'CANCELLED'} and changes nothing, which is exactly what
        # workspace.delete() did while the log claimed ten removals.
        bpy = fakebpy.make()
        bpy.data.colorspace.force("working_space", 'Linear Rec.709')
        _module, changes = run_generated(generate(WORKING_SPACE_CHANGE), bpy)
        with quiet():
            bpy.app.timers.fire()
        self.assertIn("NOT changed", "\n".join(changes))
        self.assertEqual(bpy.data.colorspace.working_space, 'Linear Rec.709')

    def test_a_file_already_in_the_target_space_queues_nothing(self):
        bpy = fakebpy.make()
        bpy.data.colorspace.force("working_space", 'ACEScg')
        _module, changes = run_generated(generate(WORKING_SPACE_CHANGE), bpy)
        self.assertEqual(bpy.app.timers.registered, [])
        self.assertEqual(changes, [])

    def test_it_waits_for_the_interface_and_gives_up_eventually(self):
        bpy = fakebpy.make()
        bpy.data.colorspace.force("working_space", 'Linear Rec.709')
        bpy.ops.handlers["wm.set_working_color_space"] = self.converting_handler()
        module, _changes = run_generated(generate(WORKING_SPACE_CHANGE), bpy)
        module._WS_FINISHED[0] = False       # the interface never reports back
        # The timer runs after the script has returned, so its output is not
        # part of what run_generated() captured -- which is the whole point of
        # deferring, and worth capturing separately rather than papering over.
        printed = io.StringIO()
        with fakebpy.installed(bpy), contextlib.redirect_stdout(printed):
            bpy.app.timers.fire()
        # Converting late is safe -- the script and its notifiers are long
        # finished. Never converting would lose the step altogether.
        self.assertEqual(bpy.data.colorspace.working_space, 'ACEScg')
        self.assertIn("never reported finished", printed.getvalue())

    def test_the_read_only_property_is_never_assigned(self):
        # working_space is read-only; the operator is the only way to change
        # it. An assignment would raise AttributeError, be caught by the
        # generated except, and log "skipped" -- silence, again.
        source = generate(WORKING_SPACE_CHANGE)
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Attribute):
                    self.assertNotEqual(target.attr, "working_space",
                                        "assigns a read-only property")


class TheMigrationWritesNoColour(unittest.TestCase):
    """The precondition that makes deferring defect 10 safe -- a real test.

    docs/MAINTAINING.md: "Deferring is safe **only because the migration writes
    no colour anywhere** -- every generated write is a bool, a string, a number
    or an enum. Check that again before adding a colour-valued step."

    That is a claim about generated output, so it can be checked instead of
    remembered. If a future scene difference introduces a colour-valued write,
    the conversion would run over a value the script had just set, and this
    fails instead of it being noticed in a render six months later.
    """

    # Three floats that are a position, not a colour.
    SPATIAL = {"location", "rotation_euler", "scale", "dimensions",
               "delta_location"}

    CHANGES = [
        ("added", ("collections", "FRAME"), None, {"color_tag": "COLOR_04"}),
        ("added", ("objects", "DOF"), None,
         {"type": "EMPTY", "location": [1.0, 2.0, 3.0]}),
        ("added", ("scenes", "Scene", "compositor", "nodes", "Blur"), None,
         {"type": "CompositorNodeBlur",
          "location": [10.0, 20.0],
          "inputs": {"Socket_7": 0.8, "Socket_10": True,
                     "Socket_46": "16 mm", "Socket_56": 400}}),
        ("changed", ("scenes", "Scene", "render", "image_settings",
                     "color_depth"), "8", "16"),
    ]

    def colour_like(self, value):
        """Three or four numbers -- what a colour looks like in a snapshot."""
        if not isinstance(value, (list, tuple)) or len(value) not in (3, 4):
            return False
        return all(isinstance(item, (int, float))
                   and not isinstance(item, bool) for item in value)

    def literals_written(self, source):
        """(target name, value) for every literal the generated code writes."""
        out = []
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if not isinstance(target, ast.Attribute):
                        continue
                    try:
                        out.append((target.attr, ast.literal_eval(node.value)))
                    except ValueError:
                        pass
            # for _id, _value in (('Socket_7', 0.8), ...): set_socket(...)
            elif isinstance(node, ast.For):
                try:
                    pairs = ast.literal_eval(node.iter)
                except ValueError:
                    continue
                if isinstance(pairs, tuple):
                    for pair in pairs:
                        if isinstance(pair, tuple) and len(pair) == 2:
                            out.append(("socket %s" % pair[0], pair[1]))
        return out

    def test_no_generated_write_is_a_colour(self):
        source = generate(self.CHANGES)
        written = self.literals_written(source)
        self.assertTrue(written, "nothing was written -- wrong fixture")
        for name, value in written:
            if name in self.SPATIAL:
                continue
            self.assertFalse(
                self.colour_like(value),
                "%s writes what looks like a colour: %r. Deferring the working "
                "colour space is only safe while the migration writes none -- "
                "see docs/MAINTAINING.md, 'The working colour space'."
                % (name, value))

    def test_the_check_would_notice_one(self):
        # Guards the check itself: a colour-valued socket must be caught.
        changes = list(self.CHANGES)
        changes[2] = ("added", ("scenes", "Scene", "compositor", "nodes",
                                "Blur"), None,
                      {"type": "CompositorNodeBlur",
                       "inputs": {"Socket_9": [0.8, 0.2, 0.1, 1.0]}})
        written = self.literals_written(generate(changes))
        self.assertTrue(any(self.colour_like(value) for _name, value in written),
                        "the scan misses a colour-valued socket")


class WorkspacesAreDeletedFromATimer(unittest.TestCase):
    """Defect 9, as far as it can be reached.

    See the file docstring: the crash is Blender's memory management and does
    not exist here. What is checked is that nothing is removed during the
    synchronous run, that the removal is queued, and that every removal is
    verified by looking the name up again -- the rule that came out of ten
    reported removals that never happened.
    """

    def setUp(self):
        self.workdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.workdir.cleanup)
        # The generated code writes a scratch .blend via tempfile.gettempdir()
        # and its log next to bpy.data.filepath. Both are pointed here so the
        # test owns everything it creates and cleans it up.
        previous = tempfile.tempdir
        tempfile.tempdir = self.workdir.name
        self.addCleanup(setattr, tempfile, "tempdir", previous)

    def a_run(self, existing=("Layout",), in_file=("Layout", "Shading")):
        payload = os.path.join(self.workdir.name, "workspace_ui.blend")
        with open(payload, "wb") as handle:
            handle.write(b"not a real .blend -- the fake never parses it")
        with quiet():
            stamp, data = mm.read_workspace(payload)

        bpy = fakebpy.make()
        bpy.data.filepath = os.path.join(self.workdir.name, "fixture.blend")
        for name in existing:
            bpy.data.workspaces.add(fakebpy.WorkSpace(name))
        bpy.data.libraries.workspaces_in_file = list(in_file)
        window = fakebpy.Window(workspace=bpy.data.workspaces.get(existing[0]),
                               screen=fakebpy.Screen("main"))
        bpy.context.window = window
        source = generate([], workspace_stamp=stamp, workspace_data=data)
        module, changes = run_generated(source, bpy)
        self.source = source
        return bpy, module, changes

    def test_nothing_is_removed_while_the_script_runs(self):
        bpy, _module, _changes = self.a_run()
        self.assertEqual(bpy.data.removed, [],
                         "a workspace was deleted inside the run")
        self.assertIsNotNone(bpy.data.workspaces.get("Layout [replaced]"),
                             "the old workspace should still be there, renamed")

    def test_the_replacement_took_the_name(self):
        # Documented behaviour: same name is replaced, not duplicated -- the
        # user must not end up with Layout and Layout.001.
        bpy, _module, _changes = self.a_run()
        self.assertIsNotNone(bpy.data.workspaces.get("Layout"))
        self.assertIsNone(bpy.data.workspaces.get("Layout.001"))

    def test_the_removal_is_queued(self):
        bpy, module, _changes = self.a_run()
        self.assertTrue(bpy.app.timers.registered, "nothing was queued")
        self.assertIn("will be removed once the script has finished",
                      "\n".join(module._ws_lines))

    def test_firing_the_timer_removes_it(self):
        bpy, module, _changes = self.a_run()
        with quiet():
            bpy.app.timers.fire()
        self.assertIsNone(bpy.data.workspaces.get("Layout [replaced]"))
        self.assertIn("removed 'Layout [replaced]'", "\n".join(module._ws_lines))

    def test_a_workspace_the_user_has_and_the_payload_does_not_is_left_alone(self):
        bpy, _module, _changes = self.a_run(existing=("Layout", "Mine"))
        with quiet():
            bpy.app.timers.fire()
        self.assertIsNotNone(bpy.data.workspaces.get("Mine"))

    def test_a_second_run_installs_nothing(self):
        # The stamp each installed workspace carries is what makes this
        # idempotent: a second run finds the interface already at this version.
        # Without it the user collects a Layout.001 on every run.
        bpy, _module, _changes = self.a_run()
        with quiet():
            bpy.app.timers.fire()
        before = sorted(bpy.data.workspaces.names())
        second, _changes = run_generated(self.source, bpy)
        self.assertEqual(sorted(bpy.data.workspaces.names()), before)
        self.assertIn("already at this version", "\n".join(second._ws_lines))

    def test_a_removal_that_silently_fails_is_reported_as_a_failure(self):
        """The rule: bpy.ops raises only when the poll fails.

        Every route in _drop_workspace is checked by looking the name up again.
        With all three routes made ineffective -- and none of them raising --
        the code must say the workspace is still there, not report success.
        """
        bpy, module, _changes = self.a_run()
        bpy.data.batch_remove = lambda ids: None      # succeeds, does nothing
        bpy.data.orphans_purge = lambda **kwargs: 0
        with quiet():
            bpy.app.timers.fire()
        log = "\n".join(module._ws_lines)
        self.assertIn("could not be removed", log)
        self.assertNotIn("removed 'Layout [replaced]'", log)
        self.assertIsNotNone(bpy.data.workspaces.get("Layout [replaced]"))


class TheImageEditorIsPointedNotZoomed(unittest.TestCase):
    """Defect 11, as far as it can be reached.

    `image.view_all(fit_view=True)` zoomed a 256x256 placeholder to fill the
    editor. The fix sets `space.image` to the compositor's Viewer Node image
    instead. A fake has no zoom, so what is checked is that the datablock is
    assigned and that no view operator is called.
    """

    def a_module(self):
        payload = os.path.join(self.workdir.name, "workspace_ui.blend")
        with open(payload, "wb") as handle:
            handle.write(b"payload")
        with quiet():
            stamp, data = mm.read_workspace(payload)
        bpy = fakebpy.make()
        bpy.data.filepath = os.path.join(self.workdir.name, "fixture.blend")
        source = generate([], workspace_stamp=stamp, workspace_data=data)
        module, _changes = run_generated(source, bpy, migrate=False)
        return bpy, module

    def setUp(self):
        self.workdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.workdir.cleanup)

    def an_image_editor(self):
        return fakebpy.Area('IMAGE_EDITOR', spaces=[fakebpy.Space('IMAGE_EDITOR')])

    def test_the_viewer_image_is_assigned(self):
        bpy, module = self.a_module()
        viewer = fakebpy.Image("Viewer Node")
        bpy.data.images.add(viewer)
        area = self.an_image_editor()
        with fakebpy.installed(bpy), quiet():
            module._ws_show_viewer(area)
        self.assertIs(area.spaces[0].image, viewer)

    def test_no_view_operator_is_called(self):
        bpy, module = self.a_module()
        bpy.data.images.add(fakebpy.Image("Viewer Node"))
        with fakebpy.installed(bpy):
            module._ws_show_viewer(self.an_image_editor())
        self.assertEqual(bpy.ops.called("image.view_all"), [])
        self.assertEqual([c for c in bpy.ops.calls if c[0].startswith("image.")],
                         [])

    def test_without_a_viewer_image_the_editor_is_left_empty(self):
        # Better an empty slot than something arbitrary: the alternative was
        # filling it with whatever image happened to be first.
        bpy, module = self.a_module()
        area = self.an_image_editor()
        with fakebpy.installed(bpy), quiet():
            module._ws_show_viewer(area)
        self.assertIsNone(area.spaces[0].image)
        self.assertIn("no 'Viewer Node' image yet", "\n".join(module._ws_lines))

    def test_only_image_editor_spaces_are_touched(self):
        bpy, module = self.a_module()
        viewer = fakebpy.Image("Viewer Node")
        bpy.data.images.add(viewer)
        other = fakebpy.Space('VIEW_3D')
        area = fakebpy.Area('IMAGE_EDITOR',
                            spaces=[other, fakebpy.Space('IMAGE_EDITOR')])
        with fakebpy.installed(bpy), quiet():
            module._ws_show_viewer(area)
        self.assertIsNone(other.image)
        self.assertIs(area.spaces[1].image, viewer)


if __name__ == "__main__":
    unittest.main()

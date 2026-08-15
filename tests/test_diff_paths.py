"""Paths stay tuples, because Blender names contain dots. No Blender involved.

Defect 4 in docs/MAINTAINING.md: dotted path splitting. Symptom recorded there
is `Camera` turning up in GONE *and* MODIFIED, and `GPM.005` truncated to `GPM`
-- a path joined to "cameras.Camera.001.lens" and split again on "." cuts the
datablock name in half and attributes `001` to `Camera` as a property.

Mutation: compare_scenes.diff joins and re-splits the path on "."
"""

import unittest

from _support import cs, generate_from_snapshots, index_of


def snapshot(objects=None, cameras=None):
    """A snapshot with just enough shape for the differ."""
    out = {"blend_file": "fixture.blend", "blender_version": "5.2.0"}
    if objects is not None:
        out["objects"] = objects
    if cameras is not None:
        out["cameras"] = cameras
    return out


class DottedNamesSurviveTheDiff(unittest.TestCase):

    def test_a_dotted_datablock_name_stays_one_path_element(self):
        before = snapshot(cameras={"Camera.001": {"lens": 50}})
        after = snapshot(cameras={"Camera.001": {"lens": 35}})
        self.assertEqual(cs.diff(before, after),
                         [("changed", ("cameras", "Camera.001", "lens"), 50, 35)])

    def test_the_path_is_as_deep_as_the_nesting_and_no_deeper(self):
        before = snapshot(objects={"GPM.005": {"location": [0, 0, 0]}})
        after = snapshot(objects={"GPM.005": {"location": [0, 0, 1]}})
        (_kind, path, _old, _new), = cs.diff(before, after)
        self.assertEqual(len(path), 3, "the name was split: %r" % (path,))
        self.assertNotIn("005", path)

    def test_a_name_of_nothing_but_dots_is_still_one_element(self):
        # Blender allows it; the point is that no amount of dots changes depth.
        before = snapshot(objects={"...": {"hide_render": False}})
        after = snapshot(objects={"...": {"hide_render": True}})
        (_kind, path, _old, _new), = cs.diff(before, after)
        self.assertEqual(path, ("objects", "...", "hide_render"))

    def test_paths_are_tuples_not_strings(self):
        before = snapshot(cameras={"Camera.001": {"lens": 50}})
        after = snapshot(cameras={"Camera.001": {"lens": 35}})
        for _kind, path, _old, _new in cs.diff(before, after):
            self.assertIsInstance(path, tuple)

    def test_fmt_is_display_only(self):
        # Written down as a test because the joined form is exactly what must
        # never be parsed back: these two different paths join identically.
        self.assertEqual(cs.fmt(("cameras", "Camera.001", "lens")),
                         cs.fmt(("cameras", "Camera", "001", "lens")))


class DottedNamesSurviveIntoTheGeneratedCode(unittest.TestCase):
    """The half that shows the recorded symptom rather than its cause.

    A truncated name does not raise -- it addresses a datablock that is not
    there, the generated `.get()` returns None, the step does nothing, and the
    run reports success. So the assertion is on the emitted name.
    """

    def test_a_modifier_on_a_dotted_object_addresses_the_full_name(self):
        before = snapshot(objects={
            "GPM.005": {"modifiers": {"Subdiv": {"type": "SUBSURF", "levels": 1}}}})
        after = snapshot(objects={
            "GPM.005": {"modifiers": {"Subdiv": {"type": "SUBSURF", "levels": 2}}}})
        source = generate_from_snapshots(before, after)
        self.assertIn("bpy.data.objects.get('GPM.005')", source)
        self.assertEqual(index_of(source, "bpy.data.objects.get('GPM')"), -1,
                         "the object name was truncated at the dot")

    def test_a_truncated_name_does_not_quietly_become_a_todo(self):
        # The failure mode this guards: the path no longer matches any rule in
        # build(), so the change lands in the TODO block and the generated file
        # looks healthy -- one step short, no error anywhere.
        before = snapshot(objects={
            "GPM.005": {"modifiers": {"Subdiv": {"type": "SUBSURF", "levels": 1}}}})
        after = snapshot(objects={
            "GPM.005": {"modifiers": {"Subdiv": {"type": "SUBSURF", "levels": 2}}}})
        source = generate_from_snapshots(before, after)
        self.assertNotIn("NOT HANDLED", source)


if __name__ == "__main__":
    unittest.main()

"""The generated code executed against the fake bpy.

The text tests say the generator writes the right thing. These say the written
thing does the right thing when it runs -- which for four of the twelve defects
is where the symptom actually lives:

  2  a read-only property raised AttributeError and killed the whole run
  3  ACEScg silently never set
  5  the file format refused, caught, logged as "skipped", scene left wrong
  6  a second run reported a change, so nothing else could be trusted either
  8  four values rewritten on every run, for ever

Every one of these is a case where the generated source looks perfectly
reasonable. Reading it would not have found them; executing it does.
"""

import unittest

import fakebpy
from _support import (generate, generate_from_snapshots, run_generated,
                      run_twice, scene_change)


def a_scene(**overrides):
    """A fake scene standing in for the untouched original."""
    scene = fakebpy.Scene("Scene")
    scene.display_settings.force("display_device", 'Rec.1886')
    scene.view_settings.force("view_transform", 'Standard')
    scene.view_settings.force("look", 'None')
    image_settings = scene.render.image_settings
    image_settings.force("media_type", 'IMAGE')
    image_settings.force("file_format", 'PNG')
    image_settings.force("color_depth", '8')
    image_settings.linear_colorspace_settings.force("name", 'sRGB')
    for key, value in overrides.items():
        scene.force(key, value)
    return scene


def logged(changes):
    return "\n".join(changes)


class AReadOnlyPropertyDoesNotKillTheRun(unittest.TestCase):
    """Defect 2: `except TypeError` only.

    A property that is read-only in this Blender raises AttributeError, not
    TypeError. Caught only for TypeError, it propagated out of migrate() and
    every step after it was lost -- and the ones before it had already been
    applied, so the file was half converted.

    `render.file_extension` is genuinely read-only in 5.2 (it derives from the
    file format) and the dumper skips it for that reason. A diff written by an
    older dumper, or a property that becomes read-only in a later Blender, puts
    exactly this in front of the generator.

    Mutation: except-type
    """

    CHANGES = [
        scene_change("render", "file_extension", ".exr"),
        scene_change("render", "resolution_x", 3840),
    ]

    def test_the_run_survives_and_reports_the_skip(self):
        bpy = fakebpy.make(scene=a_scene())
        _module, changes = run_generated(generate(self.CHANGES), bpy)
        self.assertIn("!! skipped render.file_extension", logged(changes))

    def test_the_steps_after_it_still_land(self):
        scene = a_scene()
        bpy = fakebpy.make(scene=scene)
        run_generated(generate(self.CHANGES), bpy)
        self.assertEqual(scene.render.resolution_x, 3840,
                         "the step after the read-only one never ran")

    def test_the_skip_is_visible_in_the_count(self):
        # A skip must be logged, not swallowed: the log is the only place a
        # user or a maintainer sees that something did not land.
        bpy = fakebpy.make(scene=a_scene())
        _module, changes = run_generated(generate(self.CHANGES), bpy)
        self.assertTrue(any(line.startswith("!! skipped") for line in changes))


class ThePointerIsWrittenThroughItsName(unittest.TestCase):
    """Defect 3: ACEScg silently never set.

    The snapshot records `linear_colorspace_settings` by its name, so it reads
    like a string. Assigning the string raises TypeError, the generated
    try/except swallows it, the run logs "skipped" and reports success. Twice
    this nearly shipped.

    Mutation: name-pointers
    """

    CHANGES = [scene_change("render.image_settings",
                            "linear_colorspace_settings", "ACEScg")]

    def test_acescg_actually_lands(self):
        scene = a_scene()
        bpy = fakebpy.make(scene=scene)
        run_generated(generate(self.CHANGES), bpy)
        self.assertEqual(
            scene.render.image_settings.linear_colorspace_settings.name,
            'ACEScg')

    def test_nothing_was_skipped_on_the_way(self):
        bpy = fakebpy.make(scene=a_scene())
        _module, changes = run_generated(generate(self.CHANGES), bpy)
        self.assertNotIn("skipped", logged(changes))

    def test_a_second_run_is_silent(self):
        scene = a_scene()
        bpy = fakebpy.make(scene=scene)
        _first, second = run_twice(generate(self.CHANGES), bpy)
        self.assertEqual(second, [])


class ColourManagementSurvivesItsOwnDependencies(unittest.TestCase):
    """Defect 5: scene properties written alphabetically.

    The fake models the dependency rather than asserting on the order: which
    view transforms exist depends on the display device, which looks exist
    depends on the view transform, and which file formats exist depends on the
    media type. Written in the wrong order the value is simply not in the enum,
    Blender raises TypeError, the generated except catches it, and the run says
    "skipped" while the scene keeps the old value.

    Fed in alphabetical order, which is the order the defect produced.

    Mutation: scene-order
    """

    CHANGES = [
        scene_change("display_settings", "display_device", "sRGB"),
        scene_change("view_settings", "look", "AgX - Punchy"),
        scene_change("view_settings", "view_transform", "AgX"),
        scene_change("render.image_settings", "color_depth", "16"),
        scene_change("render.image_settings", "file_format",
                     "OPEN_EXR_MULTILAYER"),
        scene_change("render.image_settings", "media_type",
                     "MULTI_LAYER_IMAGE"),
    ]

    def run_it(self):
        scene = a_scene()
        bpy = fakebpy.make(scene=scene)
        _module, changes = run_generated(generate(self.CHANGES), bpy)
        return scene, changes

    def test_the_look_lands(self):
        scene, _changes = self.run_it()
        self.assertEqual(scene.view_settings.view_transform, 'AgX')
        self.assertEqual(scene.view_settings.look, 'AgX - Punchy')

    def test_the_multilayer_format_lands(self):
        scene, _changes = self.run_it()
        self.assertEqual(scene.render.image_settings.media_type,
                         'MULTI_LAYER_IMAGE')
        self.assertEqual(scene.render.image_settings.file_format,
                         'OPEN_EXR_MULTILAYER')

    def test_nothing_reports_a_skip(self):
        # The failure this guards is quiet by construction: the value does not
        # land, the exception is caught, and the run still ends "n changes
        # applied". Only the word "skipped" in the log ever showed it.
        _scene, changes = self.run_it()
        self.assertNotIn("skipped", logged(changes))

    def test_the_fake_would_notice_the_wrong_order(self):
        # Guards the fake, not the generator: if assigning a look that does not
        # belong to the current view transform were accepted here, every
        # assertion above would pass no matter what the generator emitted.
        scene = a_scene()
        with self.assertRaises(TypeError):
            scene.view_settings.look = 'AgX - Punchy'


class ASecondRunChangesNothing(unittest.TestCase):
    """Defects 6 and 8: idempotence.

    "Run it twice, the second run reports 0 change(s) applied" is the property
    that catches a step which assigns without comparing. Two separate defects
    broke it: `focus_object` set unconditionally, and floats compared exactly
    against a scene that stores them as float32.

    Mutations: focus-unconditional, float-tolerance
    """

    # A newly created camera -- the route the generator handles cleanly. The
    # other route (a RENAMED camera data block) does not work on the first run
    # at all; that is a finding of its own, in the class below.
    BEFORE = {"objects": {}, "cameras": {}}
    AFTER = {
        "objects": {"frame": {"type": "CAMERA", "data": "Camera_frame"}},
        "cameras": {"Camera_frame": {"lens": 150.0,
                                     "dof": {"use_dof": True,
                                             "focus_object": "DOF"}}},
    }

    def a_file(self):
        """A fake .blend holding the empty the camera is to focus on."""
        scene = a_scene()
        bpy = fakebpy.make(scene=scene)
        bpy.data.objects.add(fakebpy.Object("DOF"))
        return bpy, scene

    def test_the_focus_is_set_on_the_first_run(self):
        bpy, _scene = self.a_file()
        source = generate_from_snapshots(self.BEFORE, self.AFTER)
        _module, changes = run_generated(source, bpy)
        camera_data = bpy.data.cameras.get("Camera_frame")
        self.assertIsNotNone(camera_data, "the camera data was never created")
        self.assertIs(camera_data.dof.focus_object, bpy.data.objects.get("DOF"))
        self.assertIn("focuses on DOF", logged(changes))

    def test_the_second_run_reports_nothing(self):
        bpy, _scene = self.a_file()
        source = generate_from_snapshots(self.BEFORE, self.AFTER)
        first, second = run_twice(source, bpy)
        self.assertTrue(first, "the first run applied nothing -- wrong fixture")
        self.assertEqual(second, [], "not idempotent: %s" % logged(second))

    def test_a_float_survives_the_round_trip_through_float32(self):
        # 0.01 comes out of JSON as float64 and goes into the scene as float32.
        # Compared exactly it never matches again.
        scene = a_scene()
        bpy = fakebpy.make(scene=scene)
        source = generate([scene_change("view_settings", "exposure", 0.01)])
        first, second = run_twice(source, bpy)
        self.assertTrue(first)
        self.assertEqual(second, [], "not idempotent: %s" % logged(second))

    def test_the_fake_really_stores_float32(self):
        # Guards the fake: without this the float test above proves nothing.
        scene = a_scene()
        scene.view_settings.exposure = 0.01
        self.assertNotEqual(scene.view_settings.exposure, 0.01)
        self.assertAlmostEqual(scene.view_settings.exposure, 0.01, places=7)


class ARenamedCameraDataBlockIsRenamedFirst(unittest.TestCase):
    """Defect 13. Not one of the twelve -- found here, 2026-08-15, then fixed.

    The generator used to emit its phases in this order:

        3  camera data     bpy.data.cameras.get('Camera_large')   <- NEW name
        5  focus objects   bpy.data.cameras.get('Camera_macro')   <- NEW name
        6  renames         obj.data.name = 'Camera_large'         <- only here

    A camera data block that is *renamed* rather than created still carried its
    old name during phases 3 and 5. `get()` returned None, the generated
    `if data:` skipped the whole block, and nothing was logged -- the run
    reported success. The rename landed afterwards, so a SECOND run applied the
    settings and reported them as changes, and only a third run was silent.

    Not hypothetical: the shipped setup_lookdev_scene.py has it.
    `bpy.data.cameras.get('Camera_large')` at line 3410 and
    `.get('Camera_macro')` at line 3523, against `obj.data.name =
    'Camera_large'` at line 3540. On a fresh copy of ALBIN_293 those data
    blocks are called Camera, Camera.001, Camera.002 and Camera.003, so four of
    the five cameras kept their original lens, sensor and depth-of-field values
    on the first run, and two of the three focus objects were never set.

    It broke two documented properties:
      * docs/MAINTAINING.md: "Every step compares before it acts, so a second
        run reports 0 change(s) applied."
      * the release procedure: run it a second time, it must report 0 changes.

    Fixed by moving `renames` ahead of the camera phases in Emitter.PHASES. The
    rename step needs only the OBJECT, and an object carrying a rename exists in
    both snapshots by definition -- the rename map is built from `objects.X.data`
    CHANGES -- so nothing that used to precede it was a prerequisite.

    THE INSTALLER IN THE REPOSITORY STILL HAS THE DEFECT. It is generated, and
    regenerating it needs `_local/` and a Blender that is not in this
    environment. Until then the fix exists in the generator only.

    Mutation: rename-phase-last
    """

    BEFORE = {
        "objects": {"medium": {"type": "CAMERA", "data": "Camera"}},
        "cameras": {"Camera": {"lens": 50.0}},
    }
    AFTER = {
        "objects": {"medium": {"type": "CAMERA", "data": "Camera_medium"}},
        "cameras": {"Camera_medium": {"lens": 35.0,
                                      "dof": {"use_dof": True,
                                              "focus_object": "DOF"}}},
    }

    def a_file(self):
        """A fresh copy, as a user has it: the data block still called Camera."""
        bpy = fakebpy.make(scene=a_scene())
        camera_data = fakebpy.CameraData("Camera")
        camera = fakebpy.Object("medium", type='CAMERA')
        camera.data = camera_data
        bpy.data.cameras.add(camera_data)
        bpy.data.objects.add(camera)
        bpy.data.objects.add(fakebpy.Object("DOF"))
        return bpy, camera_data

    def source(self):
        return generate_from_snapshots(self.BEFORE, self.AFTER)

    def test_the_lens_lands_on_the_first_run(self):
        bpy, camera_data = self.a_file()
        run_generated(self.source(), bpy)
        self.assertAlmostEqual(camera_data.lens, 35.0, places=5)

    def test_the_focus_lands_on_the_first_run(self):
        bpy, camera_data = self.a_file()
        run_generated(self.source(), bpy)
        self.assertIs(camera_data.dof.focus_object, bpy.data.objects.get("DOF"))

    def test_a_second_run_reports_nothing(self):
        bpy, _camera_data = self.a_file()
        _first, second = run_twice(self.source(), bpy)
        self.assertEqual(second, [], "not idempotent: %s" % logged(second))

    def test_the_rename_is_emitted_before_the_steps_that_need_it(self):
        """The cause, pinned separately from the three symptoms above.

        Worth its own test: the symptoms are about values in a fake scene and
        would also go red for a fixture mistake. This one is about the order in
        the file, and names the reason directly.
        """
        from _support import index_of
        source = self.source()
        rename = index_of(source, "obj.data.name = 'Camera_medium'")
        configure = index_of(source, "bpy.data.cameras.get('Camera_medium')")
        self.assertGreaterEqual(rename, 0, "no rename step emitted")
        self.assertGreaterEqual(configure, 0, "no camera data step emitted")
        self.assertLess(rename, configure,
                        "the camera data block is addressed by its new name "
                        "before the rename that gives it that name")


class LinksAreMadeAfterTheNodesExist(unittest.TestCase):
    """Defect 7, the runtime half.

    The text test says nodes are emitted before links. This says what happens
    when they are not: relink() looks up a node that nothing has created, skips
    the link, and the tree ends up unwired -- without an exception anywhere.

    Mutation: phase-order
    """

    CHANGES = [
        ("changed", ("scenes", "Scene", "compositor", "links"), [],
         [{"from": ["Blur", "Image"], "to": ["Composite", "Image"]}]),
        ("added", ("scenes", "Scene", "compositor", "nodes", "Blur"), None,
         {"type": "CompositorNodeBlur"}),
    ]

    def a_file(self):
        tree = fakebpy.NodeTree("Compositing", nodes=[
            fakebpy.Node("CompositorNodeComposite", "Composite")])
        scene = a_scene()
        scene.compositing_node_group = tree
        return fakebpy.make(scene=scene), tree

    def test_the_link_is_actually_made(self):
        bpy, tree = self.a_file()
        run_generated(generate(self.CHANGES), bpy)
        self.assertEqual(tree.links.as_tuples(),
                         [("Blur", "Image", "Composite", "Image")])

    def test_a_second_run_rewires_nothing(self):
        bpy, _tree = self.a_file()
        first, second = run_twice(generate(self.CHANGES), bpy)
        self.assertTrue(first)
        self.assertEqual(second, [], "not idempotent: %s" % logged(second))


if __name__ == "__main__":
    unittest.main()

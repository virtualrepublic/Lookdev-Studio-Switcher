"""What the generator writes, checked as text. No Blender involved.

`make_migration.py` produces Python source. Five of the twelve defects in
docs/MAINTAINING.md are visible in that source alone -- the wrong text was
emitted -- so they need no fake bpy at all, only the real generator and
`compile()`. The runtime half of the same defects (does the emitted code do the
right thing when executed) lives in the fake-bpy modules.

Every test names the defect it guards and the mutation that turns it red.
`tests/mutations.py` applies those mutations and checks that they do.
"""

import unittest

from _support import generate, scene_change, index_of, lines_of


class BackslashInALoggedValue(unittest.TestCase):
    """Defect 1: a raw value interpolated into a generated log("...").

    Symptom: a value ending in a backslash ended the string literal early and
    the generated file would not parse at all -- the whole migration was lost,
    not one setting. `log_line()` puts the message through repr().

    Mutation: log_line -> '%slog("%s")' % (indent, message)
    """

    def test_a_windows_path_still_parses(self):
        source = generate([scene_change("render", "filepath", "C:\\tmp\\")])
        compile(source, "<generated>", "exec")

    def test_the_value_is_not_mangled_on_the_way_in(self):
        source = generate([scene_change("render", "filepath", "C:\\tmp\\")])
        self.assertIn("scene.render.filepath = 'C:\\\\tmp\\\\'", source)

    def test_a_quote_in_a_value_still_parses(self):
        source = generate([scene_change("render", "filepath", "//it's here")])
        compile(source, "<generated>", "exec")

    def test_a_newline_in_a_value_still_parses(self):
        # Not a Blender path, but nothing stops a string property holding one,
        # and an unescaped newline breaks a single-quoted literal the same way.
        source = generate([scene_change("render", "filepath", "one\ntwo")])
        compile(source, "<generated>", "exec")


class NamePointersAreWrittenThroughName(unittest.TestCase):
    """Defect 3: a pointer-with-.name written as a plain string.

    Symptom: ACEScg silently never set. The snapshot records the struct by its
    name, so the value reads like a string; assigning the string raises
    TypeError, and the generated try/except swallows it and logs "skipped".

    Mutation: NAME_POINTERS = ()
    """

    def test_the_assignment_targets_name(self):
        source = generate([scene_change("render.image_settings",
                                        "linear_colorspace_settings", "ACEScg")])
        self.assertIn(
            "scene.render.image_settings.linear_colorspace_settings.name = 'ACEScg'",
            source)

    def test_the_bare_struct_is_never_assigned(self):
        source = generate([scene_change("render.image_settings",
                                        "linear_colorspace_settings", "ACEScg")])
        for line in lines_of(source):
            if "linear_colorspace_settings = " in line:
                self.fail("assigns the struct itself, not its name: %r" % line)

    def test_an_ordinary_string_property_is_not_given_a_name(self):
        # The rule must stay narrow: only the listed pointers get .name.
        source = generate([scene_change("view_settings", "view_transform", "AgX")])
        self.assertIn("scene.view_settings.view_transform = 'AgX'", source)
        self.assertNotIn("view_transform.name", source)


class SceneOrderIsDefinedNotAlphabetical(unittest.TestCase):
    """Defect 5: scene properties emitted in alphabetical order.

    Symptom: `look` before `view_transform` (the available looks depend on the
    view transform), and `media_type` last of all -- while it is still IMAGE the
    file format enum holds no OPEN_EXR_MULTILAYER, so the format is refused,
    caught, logged as "skipped", and the scene keeps the wrong one.

    Both chains are fed in here in alphabetical order on purpose: that is the
    order the defect produced, so a generator that does not sort fails.

    Mutation: build() emits scene_props unsorted
    """

    COLOUR = [
        scene_change("display_settings", "display_device", "sRGB"),
        scene_change("view_settings", "look", "AgX - Punchy"),
        scene_change("view_settings", "view_transform", "AgX"),
    ]
    FORMAT = [
        scene_change("render.image_settings", "color_depth", "16"),
        scene_change("render.image_settings", "exr_codec", "ZIP"),
        scene_change("render.image_settings", "file_format", "OPEN_EXR_MULTILAYER"),
        scene_change("render.image_settings", "media_type", "MULTI_LAYER_IMAGE"),
    ]

    def assert_emitted_in_order(self, source, needles):
        found = [(needle, index_of(source, needle)) for needle in needles]
        for needle, position in found:
            self.assertGreaterEqual(position, 0, "never emitted at all: %s" % needle)
        positions = [position for _needle, position in found]
        self.assertEqual(positions, sorted(positions),
                         "emitted in the wrong order: %r"
                         % [needle for needle, _position in found])

    def test_colour_management_follows_the_dependency_chain(self):
        self.assert_emitted_in_order(generate(self.COLOUR), [
            "display_settings.display_device",
            "view_settings.view_transform",
            "view_settings.look",
        ])

    def test_media_type_is_written_before_the_file_format(self):
        self.assert_emitted_in_order(generate(self.FORMAT), [
            "image_settings.media_type",
            "image_settings.file_format",
            "image_settings.color_depth",
        ])

    def test_the_order_does_not_depend_on_how_the_diff_arrived(self):
        # Same three, handed over already correct. A generator that merely
        # passes its input through would sail past the two tests above if the
        # diff happened to arrive in a helpful order.
        reversed_input = list(reversed(self.COLOUR))
        self.assert_emitted_in_order(generate(reversed_input), [
            "display_settings.display_device",
            "view_settings.view_transform",
            "view_settings.look",
        ])


class CompositorNodesBeforeLinks(unittest.TestCase):
    """Defect 7: compositor links emitted before the nodes they connect.

    Symptom: links hanging in the void -- relink() looks up node names that
    nothing has created yet.

    The two changes are handed in links-first, so an emitter that keeps input
    order fails.

    Mutation: Emitter.PHASES with compositor_links before compositor_nodes
    """

    CHANGES = [
        ("changed", ("scenes", "Scene", "compositor", "links"), [],
         [{"from": ["Blur", "Image"], "to": ["Composite", "Image"]}]),
        ("added", ("scenes", "Scene", "compositor", "nodes", "Blur"), None,
         {"type": "CompositorNodeBlur"}),
    ]

    def test_the_node_is_created_before_the_wiring(self):
        source = generate(self.CHANGES)
        node = index_of(source, "tree.nodes.new")
        links = index_of(source, "relink(tree")
        self.assertGreaterEqual(node, 0, "no node creation emitted")
        self.assertGreaterEqual(links, 0, "no relink emitted")
        self.assertLess(node, links,
                        "links are emitted before the nodes they connect")

    def test_a_removal_also_lands_before_the_wiring(self):
        # Removing a node while the old links still point at it is the same
        # ordering problem seen from the other side.
        changes = [
            ("changed", ("scenes", "Scene", "compositor", "links"), [],
             [{"from": ["Render Layers", "Image"], "to": ["Composite", "Image"]}]),
            ("removed", ("scenes", "Scene", "compositor", "nodes", "Blur"),
             {"type": "CompositorNodeBlur"}, None),
        ]
        source = generate(changes)
        self.assertLess(index_of(source, "tree.nodes.remove"),
                        index_of(source, "relink(tree"))


class FloatsAreComparedWithATolerance(unittest.TestCase):
    """Defect 8: float32 in the scene against float64 from the snapshot.

    Symptom: 0.01 is 0.009999999776482582 once Blender has stored it, so `!=`
    is true for ever. Four values were rewritten on every run and a second run
    never reached "0 change(s) applied" -- which is the check that catches a
    step assigning without comparing.

    This is the text half. The half that matters -- a second run really is
    silent -- needs the fake bpy and lives in the runtime tests.

    Mutation: compare_to() always returns the `!=` form
    """

    def test_a_float_gets_the_tolerance_form(self):
        source = generate([scene_change("view_settings", "exposure", 0.01)])
        self.assertIn(
            "if abs(scene.view_settings.exposure - 0.01) > "
            "max(1e-6, abs(0.01) * 1e-6):",
            source)

    def test_a_string_keeps_plain_inequality(self):
        # The tolerance must not spread: `abs()` on a string would raise
        # TypeError, be swallowed by the generated except, and log "skipped".
        source = generate([scene_change("view_settings", "view_transform", "AgX")])
        self.assertIn("if scene.view_settings.view_transform != 'AgX':", source)

    def test_an_integer_keeps_plain_inequality(self):
        source = generate([scene_change("render", "resolution_x", 1920)])
        self.assertIn("if scene.render.resolution_x != 1920:", source)

    def test_a_node_location_is_compared_with_the_same_tolerance(self):
        # Two float32 against two float64 -- the same problem, its own code path.
        source = generate([("changed",
                            ("scenes", "Scene", "compositor", "nodes", "Blur",
                             "location"),
                            [0.0, 0.0], [12.5, -3.25])])
        self.assertIn("max(1e-6, abs(b) * 1e-6)", source)


class WhateverIsGeneratedParses(unittest.TestCase):
    """Not one of the twelve: the floor under all of them.

    Defect 1 was a parse failure, and a parse failure loses the whole file
    rather than one setting. So every fixture in this module goes through
    compile() as well, and so does a mixed one.
    """

    def test_a_mixed_migration_compiles(self):
        changes = (
            SceneOrderIsDefinedNotAlphabetical.COLOUR
            + SceneOrderIsDefinedNotAlphabetical.FORMAT
            + CompositorNodesBeforeLinks.CHANGES
            + [
                scene_change("render", "filepath", "//sub\\dir\\"),
                scene_change("view_settings", "exposure", 0.01),
                ("added", ("collections", "FRAME"), None,
                 {"color_tag": "COLOR_04"}),
                ("changed", ("objects", "GPM.005", "modifiers", "Subdiv",
                             "levels"), 1, 2),
            ]
        )
        compile(generate(changes), "<generated>", "exec")

    def test_an_empty_diff_still_produces_a_runnable_script(self):
        compile(generate([]), "<generated>", "exec")


if __name__ == "__main__":
    unittest.main()

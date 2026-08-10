# ============================================================================
#  MAKE MIGRATION  v1.1  --  turn a scene diff into a runnable migration script
# ============================================================================
#  by Prof. Michael Klein
#     professor@virtualrepublic.org
#
#  Part of the Lookdev Switcher toolchain. Plain Python, no Blender needed.
#
#  USAGE:
#     1. Write both snapshots:
#        blender --background --python diff_blends.py -- ^
#            LOOKDEV_STUDIO_ORIGINAL.blend LOOKDEV_STUDIO_COPY.blend ^
#            --keep-snapshots snap --summary
#     2. Generate the migration:
#        python make_migration.py snap_original.json snap_modified.json ^
#            -o setup_lookdev_scene.py
#        (or via Blender's own python:
#         blender --background --python make_migration.py -- a.json b.json -o out.py)
#     3. Read it, then run it in Blender on the original scene.
#
#  ORDER MATTERS, so the output is built in PHASES:
#     1 collections      before anything gets linked into them
#     2 camera data      before a camera object can reference it
#     3 objects          create, place, link into their collections
#     4 focus objects    only now do the empties a camera focuses on exist
#     5 renames          data blocks, addressed via their OBJECT name
#     6 modifiers
#     7 scene settings
#
#  WHAT IT WILL NOT DO
#  It refuses to guess. Only EMPTY and CAMERA objects are generated -- they
#  carry no geometry. A new mesh would mean shipping the author's data, so it
#  is listed as TODO instead. Everything it cannot express as a reliable API
#  call ends up in that TODO block, never silently dropped.
# ============================================================================

import json
import argparse
import sys
import os
import zlib
import base64
import hashlib

# Import compare_scenes from THIS script's folder, not from the current
# directory -- so it works no matter where the terminal happens to stand.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# Values that must never end up in a migration: they belong to your project,
# not to the studio setup.
BLOCKED = {
    ("render", "frame_path"),
    # A statement about my computer, not about the scene. Forcing GPU denoising
    # on someone without a compatible card helps nobody.
    ("cycles", "denoising_use_gpu"),
}

# Project-specific values that must not travel -- but leaving them at the
# original's value is no better. Reset them to what a fresh scene would have.
# Emitted unconditionally, whether or not the diff mentions them.
#
# render.filepath used to live here, back when the scene still carried a private
# project path. It is now "//" -- the blend file's own folder -- which is exactly
# what a fresh scene should have, so the diff can carry it like any other value.
# Put it back if a project path ever creeps in again.
NEUTRALISE = {}

SCENE_SECTIONS = ("render", "unit_settings", "view_settings", "cycles", "eevee",
                  "display_settings", "sequencer_colorspace_settings")

# Colour management is order sensitive and would fail if written alphabetically:
# the available view transforms depend on the display device, and the available
# looks depend on the view transform. Anything not listed keeps its own order.
SCENE_PROP_ORDER = (
    ("display_settings", "display_device"),
    ("view_settings", "view_transform"),
    ("view_settings", "look"),
    # The output format is the same kind of chain. media_type decides which
    # file formats exist at all: while it is still IMAGE the enum holds
    # ('AVIF', 'JPEG', 'OPEN_EXR', 'PNG', ...) and no OPEN_EXR_MULTILAYER, so
    # writing file_format first is refused -- caught, logged as "skipped", and
    # the scene keeps the wrong format. Written alphabetically that is exactly
    # the order it happened in: color_depth, exr_codec, file_format, ...,
    # media_type. Depth, codec and the colour space in turn depend on the
    # format, so they follow it.
    ("render.image_settings", "media_type"),
    ("render.image_settings", "file_format"),
    ("render.image_settings", "color_depth"),
    ("render.image_settings", "exr_codec"),
    ("render.image_settings", "linear_colorspace_settings"),
)
# These look like plain strings in a snapshot, but they are structs carrying a
# .name -- the dump records the name, so the value reads like a string. Writing
# the string straight back raises TypeError, the generated try/except swallows
# it, and the setting you actually wanted (ACEScg) never lands. Write .name.
NAME_POINTERS = ("linear_colorspace_settings",)

COLLECTION_PROPS = ("color_tag", "hide_viewport", "hide_render")
MODIFIER_META = {"name", "type", "index"}

# Object types we are willing to create: neither carries geometry.
CREATABLE_TYPES = {'EMPTY', 'CAMERA'}

# Camera data properties worth writing back (dof is handled separately)
CAMERA_PROPS = ("lens", "lens_unit", "sensor_fit", "sensor_width", "sensor_height",
                "shift_x", "shift_y", "clip_start", "clip_end")
DOF_PROPS = ("use_dof", "focus_distance", "aperture_fstop", "aperture_blades",
             "aperture_rotation", "aperture_ratio")


def load(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def lit(value):
    return repr(value)


def log_line(message, indent=""):
    """A log() call whose message is a proper Python literal.

    Interpolating a value straight into a quoted string breaks the moment the
    value contains a backslash or a quote: a Windows path like /tmp\\ would end
    the string early and the generated file would not even parse.
    """
    return '%slog(%s)' % (indent, lit(message))


class Emitter:
    """Collects generated code in phases so ordering is guaranteed."""

    # working_space is first, and it has to be. The operator behind it converts
    # every colour in the file. The snapshot holds the reworked scene's values,
    # which are already in the new space -- so converting first and writing
    # afterwards is right, and writing first would convert those values a
    # second time.
    PHASES = ("working_space",
              "collections", "collection_order", "camera_data", "objects",
              "focus", "renames", "modifiers", "scene",
              # nodes before links: a link needs both ends to exist
              "compositor_nodes", "compositor_links")

    def __init__(self):
        self.phases = {name: [] for name in self.PHASES}
        self.todo = []
        self.count = 0

    def step(self, phase, lines, comment=None):
        body = self.phases[phase]
        if comment:
            body.append("    # %s" % comment)
        body.extend("    " + l if l else "" for l in lines)
        body.append("")
        self.count += 1

    def unhandled(self, kind, path, old, new):
        self.todo.append("#   %-8s %s" % (kind, ".".join(path)))
        if kind == "changed":
            self.todo.append("#            old: %s" % json.dumps(old)[:90])
            self.todo.append("#            new: %s" % json.dumps(new)[:90])

    def note(self, text):
        self.todo.append("#   %s" % text)

    def body(self):
        out = []
        titles = {
            "working_space": "1. Blend file working colour space (converts every colour)",
            "collections": "2. Collections",
            "collection_order": "3. Collection order (exact, as in the new scene)",
            "camera_data": "4. Camera data blocks",
            "objects": "5. Objects (create, place, link)",
            "focus": "6. Focus objects (need the objects above)",
            "renames": "7. Data block renames",
            "modifiers": "8. Modifiers",
            "scene": "9. Scene settings",
            "compositor_nodes": "10. Compositor nodes",
            "compositor_links": "11. Compositor links",
        }
        for name in self.PHASES:
            if not self.phases[name]:
                continue
            out.append('    print("\\n-- %s")' % titles[name])
            out.extend(self.phases[name])
        return out


# --- generators --------------------------------------------------------------

def gen_working_space(em, new):
    """Change the blend file's working colour space.

    Unlike every other step this is an operator call, and it has to be.
    bpy.data.colorspace.working_space is read-only; the value cannot be
    assigned. Measured on 5.2 LTS:

        bpy.ops.wm.set_working_color_space(convert_colors=..., working_space=...)
        'Set Blend File Working Color Space'
        'Change the working color space of all colors in this blend file'
        options: 'Linear Rec.709', 'Linear Rec.2020', 'ACEScg'

    convert_colors=True is the checkbox in the dialog, and it is what makes the
    step meaningful: without it the label changes and every colour in the file
    is reinterpreted rather than converted, which shifts the whole look.

    An operator is not an assignment, and bpy.ops is quiet about failing --
    workspace.delete() returned {'CANCELLED'} ten times while the log happily
    reported ten removals. So the result is read back and only then logged.
    """
    em.step("working_space", [
        'try:',
        '    space = getattr(bpy.data, "colorspace", None)',
        '    if space is None:',
        '        ' + log_line("!! this Blender has no blend file working colour "
                              "space -- nothing to set"),
        '    elif space.working_space != %s:' % lit(new),
        '        bpy.ops.wm.set_working_color_space(working_space=%s,'
        ' convert_colors=True)' % lit(new),
        '        if space.working_space == %s:' % lit(new),
        '            ' + log_line("working colour space -> %s "
                                  "(all colours in the file converted)" % new),
        '        else:',
        '            log(%s + repr(space.working_space))'
        % lit("!! working colour space NOT changed, still: "),
        # RuntimeError is what a refused operator raises; the other two are the
        # house convention for a property that moved or will not take the value.
        'except (AttributeError, TypeError, RuntimeError) as exc:',
        '    log(%s + str(exc))' % lit("!! skipped working colour space: "),
    ], "blend file working colour space")


def gen_collection_added(em, name, data):
    lines = [
        'coll = bpy.data.collections.get(%s)' % lit(name),
        'if coll is None:',
        '    coll = bpy.data.collections.new(%s)' % lit(name),
        '    ' + log_line("collection %s created" % name),
    ]
    tag = data.get("color_tag")
    if tag:
        lines.append('coll.color_tag = %s' % lit(tag))
    lines += [
        'if %s not in scene.collection.children:' % lit(name),
        '    scene.collection.children.link(coll)',
        '    ' + log_line("collection %s linked into the scene" % name),
    ]
    em.step("collections", lines, "new collection: %s" % name)


def gen_collection_prop(em, name, prop, new):
    em.step("collections", [
        'coll = bpy.data.collections.get(%s)' % lit(name),
        'if coll and coll.%s != %s:' % (prop, lit(new)),
        '    coll.%s = %s' % (prop, lit(new)),
        '    ' + log_line("%s.%s -> %s" % (name, prop, new)),
    ], "collection %s: %s" % (name, prop))


def gen_collection_order(em, container_expr, desired, label):
    """Reproduce the child order of the new scene exactly, 1:1.

    Blender has no reorder API for collection children -- the order IS the link
    order. So the only way to arrange them is to unlink everything and relink in
    the target sequence. Collections that are not part of the plan are relinked
    afterwards, so nothing can get lost.

    Note: relinking rebuilds the view layer, which resets the outliner exclude
    checkboxes. That is harmless here -- the migration runs once on the fresh
    original, and the Lookdev Switcher sets the checkboxes on every click.
    """
    em.step("collection_order", [
        'container = %s' % container_expr,
        'desired = %s' % lit(list(desired)),
        'current = [c.name for c in container.children]',
        'if current != desired:',
        '    existing = list(container.children)',
        '    extras = [c for c in existing if c.name not in desired]',
        '    for child in existing:',
        '        container.children.unlink(child)',
        '    for name in desired:',
        '        coll = bpy.data.collections.get(name)',
        '        if coll:',
        '            container.children.link(coll)',
        '    for child in extras:      # anything unplanned goes last, never lost',
        '        container.children.link(child)',
        '    ' + log_line("%s order: %s" % (label, ", ".join(desired))),
    ], "exact child order of %s" % label)


def gen_camera_data(em, data_name, cam, create):
    """Create (or just configure) a camera data block. focus_object comes later."""
    lines = []
    if create:
        lines += [
            'data = bpy.data.cameras.get(%s)' % lit(data_name),
            'if data is None:',
            '    data = bpy.data.cameras.new(%s)' % lit(data_name),
            '    ' + log_line("camera data %s created" % data_name),
        ]
    else:
        lines += [
            'data = bpy.data.cameras.get(%s)' % lit(data_name),
            'if data:',
        ]
    indent = "" if create else "    "
    for prop in CAMERA_PROPS:
        if prop in cam:
            lines.append('%sdata.%s = %s' % (indent, prop, lit(cam[prop])))
    dof = cam.get("dof") or {}
    for prop in DOF_PROPS:
        if prop in dof:
            lines.append('%sdata.dof.%s = %s' % (indent, prop, lit(dof[prop])))
    em.step("camera_data", lines,
            "%s camera data: %s" % ("new" if create else "configure", data_name))


def gen_camera_focus(em, data_name, focus_name):
    em.step("focus", [
        'data = bpy.data.cameras.get(%s)' % lit(data_name),
        'target = bpy.data.objects.get(%s)' % lit(focus_name),
        'if data and target and data.dof.focus_object is not target:',
        '    data.dof.focus_object = target',
        '    ' + log_line("%s focuses on %s" % (data_name, focus_name)),
    ], "focus object of %s" % data_name)


def gen_object_added(em, name, obj):
    """Create an EMPTY or CAMERA object, place it, link it into its collections."""
    otype = obj.get("type")
    data_name = obj.get("data")

    if otype == 'EMPTY':
        create = 'bpy.data.objects.new(%s, None)' % lit(name)
    elif otype == 'CAMERA' and data_name:
        create = 'bpy.data.objects.new(%s, bpy.data.cameras[%s])' % (lit(name),
                                                                     lit(data_name))
    else:
        em.note("object '%s' (%s) not generated: only EMPTY and CAMERA are "
                "created, anything else would mean shipping scene data"
                % (name, otype))
        return False

    lines = [
        'obj = bpy.data.objects.get(%s)' % lit(name),
        'if obj is None:',
        '    obj = %s' % create,
        '    ' + log_line("object %s created" % name),
    ]
    if otype == 'EMPTY':
        if "empty_display_type" in obj:
            lines.append('obj.empty_display_type = %s' % lit(obj["empty_display_type"]))
        if "empty_display_size" in obj:
            lines.append('obj.empty_display_size = %s' % lit(obj["empty_display_size"]))
    for prop in ("location", "rotation_euler", "scale"):
        if prop in obj and obj[prop] is not None:
            lines.append('obj.%s = %s' % (prop, tuple(obj[prop])))

    for coll_name in obj.get("users_collection", []):
        lines += [
            'coll = bpy.data.collections.get(%s)' % lit(coll_name),
            'if coll and %s not in coll.objects:' % lit(name),
            '    coll.objects.link(obj)',
            '    ' + log_line("%s linked into %s" % (name, coll_name)),
        ]
    em.step("objects", lines, "new object: %s (%s)" % (name, otype))
    return True


def gen_object_data_rename(em, obj_name, old, new):
    """objects.X.data changed -> the data block was renamed, not swapped.

    Addressed through the OBJECT name: the ".001" suffixes Blender hands out
    depend on load order and differ between copies of the same file.
    """
    em.step("renames", [
        'obj = bpy.data.objects.get(%s)' % lit(obj_name),
        'if obj and obj.data and obj.data.name != %s:' % lit(new),
        '    obj.data.name = %s' % lit(new),
        '    ' + log_line("%s data %s -> %s" % (obj_name, old, new)),
    ], "rename data of '%s': %s -> %s" % (obj_name, old, new))


def gen_modifier_added(em, obj_name, mod_name, data):
    mod_type = data.get("type")
    if not mod_type:
        return False
    lines = [
        'obj = bpy.data.objects.get(%s)' % lit(obj_name),
        'if obj:',
        '    mod = obj.modifiers.get(%s)' % lit(mod_name),
        '    if mod is None:',
        '        mod = obj.modifiers.new(%s, %s)' % (lit(mod_name), lit(mod_type)),
        '        ' + log_line("%s: %s modifier added" % (obj_name, mod_name)),
    ]
    for key in sorted(data):
        if key in MODIFIER_META:
            continue
        value = data[key]
        if isinstance(value, (dict, type(None))):
            continue
        lines += [
            '    if getattr(mod, %s, None) != %s:' % (lit(key), lit(value)),
            '        try:',
            '            mod.%s = %s' % (key, lit(value)),
            '        except (AttributeError, TypeError):',
            '            pass    # read-only or unknown in this version',
        ]
    em.step("modifiers", lines,
            "new modifier on '%s': %s (%s)" % (obj_name, mod_name, mod_type))
    return True


def gen_modifier_prop(em, obj_name, mod_name, prop, new):
    if prop in MODIFIER_META or isinstance(new, dict):
        return False
    em.step("modifiers", [
        'obj = bpy.data.objects.get(%s)' % lit(obj_name),
        'mod = obj.modifiers.get(%s) if obj else None' % lit(mod_name),
        'if mod and getattr(mod, %s, None) != %s:' % (lit(prop), lit(new)),
        '    try:',
        '        mod.%s = %s' % (prop, lit(new)),
        '        ' + log_line("%s: %s.%s -> %s" % (obj_name, mod_name, prop, new)),
        '    except (AttributeError, TypeError):',
        '        pass',
    ], "modifier %s on '%s': %s" % (mod_name, obj_name, prop))
    return True


def compare_to(target, value):
    """The 'has this already got the right value' test for one property.

    Floats need a tolerance. Blender stores them as float32 and the snapshot
    carries the float64 that json read back, so 0.01 is 0.009999999776482582 in
    the scene and != is true forever: the step fires on every run, reports a
    change that changed nothing, and a second run never reaches "0 changes" --
    which is the check that is supposed to catch steps that assign blindly.
    """
    if isinstance(value, float):
        return ('if abs(%s - %s) > max(1e-6, abs(%s) * 1e-6):'
                % (target, lit(value), lit(value)))
    return 'if %s != %s:' % (target, lit(value))


def gen_scene_prop(em, section, prop, new):
    target = "scene.%s.%s" % (section, prop)
    if prop in NAME_POINTERS:
        target += ".name"       # a struct, not a string -- see NAME_POINTERS
    em.step("scene", [
        'try:',
        '    ' + compare_to(target, new),
        '        %s = %s' % (target, lit(new)),
        '        ' + log_line("%s -> %s" % (target.replace("scene.", ""), new)),
        # AttributeError: read-only, or gone in this Blender version.
        # TypeError:      the value is not valid here (a missing OCIO look, say).
        # Catching only TypeError let a read-only property crash the whole run.
        'except (AttributeError, TypeError) as exc:',
        '    log(%s + str(exc))' % lit("!! skipped %s: "
                                       % target.replace("scene.", "")),
    ], target.replace("scene.", ""))


def gen_compositor_node(em, name, data):
    """Create a compositor node. Group nodes also need their node tree."""
    node_type = data.get("type")
    if not node_type:
        return False

    lines = [
        'tree = compositor_tree(scene)',
        'if tree is None:',
        '    ' + log_line("!! no compositor node tree in this scene"),
        'else:',
        '    node = tree.nodes.get(%s)' % lit(name),
        '    if node is None:',
        '        node = tree.nodes.new(%s)' % lit(node_type),
        '        node.name = %s' % lit(name),
        '        ' + log_line("compositor node %s created" % name),
    ]

    group_name = data.get("node_tree")
    if group_name:
        # A group node is useless without its tree, and the tree is not in the
        # original scene -- it comes from Blender's bundled assets.
        lines += [
            '    group = find_node_group(%s)' % lit(group_name),
            '    if group is None:',
            '        ' + log_line("!! node group %r not found -- add it by hand "
                                  "from Add > Group, then rerun" % group_name),
            '    elif node.node_tree is not group:',
            '        node.node_tree = group',
            '        ' + log_line("%s uses node group %s" % (name, group_name)),
        ]

    if data.get("label"):
        lines.append('    node.label = %s' % lit(data["label"]))
    if "mute" in data:
        lines.append('    node.mute = %s' % lit(data["mute"]))
    if data.get("location"):
        lines.append('    node.location = %s' % (tuple(data["location"]),))

    inputs = data.get("inputs") or {}
    if inputs:
        lines.append('    for _id, _value in %s:' % (tuple(sorted(inputs.items())),))
        lines.append('        set_socket(node, _id, _value)')

    em.step("compositor_nodes", lines,
            "compositor node: %s (%s)" % (name, node_type))
    return True


def gen_compositor_node_removed(em, name):
    """Remove a compositor node the original has and the reworked scene does not.

    The only step in the whole migration that takes something away, so it is
    narrow on purpose. A "removed" entry means the node was in the ORIGINAL
    snapshot: it is part of what the author ships, not something the user built.
    Anything the user added themselves appears in neither snapshot and is never
    named here, so it cannot be caught by this.

    If the node is already gone -- renamed, deleted by hand, a scene converted
    twice -- get() returns None and nothing happens, which is also what makes a
    second run report no changes.
    """
    em.step("compositor_nodes", [
        'tree = compositor_tree(scene)',
        'node = tree.nodes.get(%s) if tree else None' % lit(name),
        'if node is not None:',
        '    tree.nodes.remove(node)',
        '    ' + log_line("compositor node %s removed -- not in the reworked scene"
                          % name),
    ], "compositor node removed: %s" % name)
    return True


def gen_compositor_node_prop(em, name, prop, new):
    if prop not in ("location", "label", "mute"):
        return False
    value = tuple(new) if prop == "location" else lit(new)
    # A location is two float32 in the scene against two float64 from the
    # snapshot -- compared exactly it never matches and the node is "moved" to
    # where it already is on every run. Same tolerance as the scene properties.
    if prop == "location":
        test = ('if node is not None and any(abs(a - b) > max(1e-6, abs(b) * 1e-6)'
                ' for a, b in zip(node.location, %s)):' % (value,))
    else:
        test = 'if node is not None and node.%s != %s:' % (prop, value)
    em.step("compositor_nodes", [
        'tree = compositor_tree(scene)',
        'node = tree.nodes.get(%s) if tree else None' % lit(name),
        test,
        '    node.%s = %s' % (prop, value),
        '    ' + log_line("compositor %s.%s -> %s" % (name, prop, new)),
    ], "compositor node %s: %s" % (name, prop))
    return True


def gen_compositor_links(em, links):
    """Rewire the whole tree: links are a set, not settable properties."""
    wanted = tuple((tuple(l["from"]), tuple(l["to"])) for l in links)
    em.step("compositor_links", [
        'tree = compositor_tree(scene)',
        'if tree is None:',
        '    ' + log_line("!! no compositor node tree to wire up"),
        'else:',
        '    made = relink(tree, %s)' % (wanted,),
        '    if made is not None:',
        '        ' + log_line("compositor rewired: %d link(s)" % len(wanted)),
    ], "compositor links (%d)" % len(wanted))


# --- driver ------------------------------------------------------------------

def rename_map(changes):
    """old data name -> new data name, taken from objects.X.data changes.

    These pairs explain why a data block looks 'removed' and another 'added':
    it is one block that was renamed.
    """
    out = {}
    for kind, path, old, new in changes:
        if (kind == "changed" and path[:1] == ("objects",) and len(path) == 3
                and path[2] == "data" and isinstance(new, str) and isinstance(old, str)):
            out[old] = new
    return out


def build(before, after, changes):
    em = Emitter()
    scene_props = []          # collected, then emitted in a defined order
    renames = rename_map(changes)
    renamed_to = set(renames.values())
    renamed_from = set(renames)

    # Which camera data blocks does a NEW object need?
    needed_by_new_objects = {
        obj.get("data")
        for name, obj in (after.get("objects") or {}).items()
        if name not in (before.get("objects") or {}) and obj.get("type") == 'CAMERA'
    }

    for kind, path, old, new in changes:
        head = path[0] if path else ""

        # --- blend file ----------------------------------------------------
        if head == "blend_file_settings" and path[-1:] == ("working_space",):
            if kind == "changed" and new:
                gen_working_space(em, new)
                continue
        if head == "blend_file_settings" and len(path) == 1 and kind == "added":
            # The whole section is new: one snapshot predates the dumper knowing
            # about it. Both snapshots must come from the same dumper, so say so
            # rather than generating from half the evidence.
            em.note("blend_file_settings appeared as a whole -- one snapshot is "
                    "older than the other. Re-run the diff before trusting this.")
            value = (new or {}).get("working_space")
            if value:
                gen_working_space(em, value)
            continue

        # --- collections ---------------------------------------------------
        if head == "collections" and len(path) == 2 and kind == "added":
            gen_collection_added(em, path[1], new)
            continue
        if (head == "collections" and len(path) == 3 and kind == "changed"
                and path[2] in COLLECTION_PROPS):
            gen_collection_prop(em, path[1], path[2], new)
            continue
        # child order inside a collection -- taken 1:1 from the new scene
        if (head == "collections" and len(path) == 3 and kind == "changed"
                and path[2] == "children" and isinstance(new, list)):
            gen_collection_order(em, 'bpy.data.collections[%s]' % lit(path[1]),
                                 new, path[1])
            continue

        # --- camera data ---------------------------------------------------
        if head == "cameras" and len(path) == 2:
            name = path[1]
            if kind == "added":
                if name in renamed_to:
                    # not a new block: an existing one renamed. Configure it in
                    # phase 2, rename it in phase 5.
                    gen_camera_data(em, name, new, create=False)
                    focus = (new.get("dof") or {}).get("focus_object")
                    if focus:
                        gen_camera_focus(em, name, focus)
                elif name in needed_by_new_objects:
                    gen_camera_data(em, name, new, create=True)
                    focus = (new.get("dof") or {}).get("focus_object")
                    if focus:
                        gen_camera_focus(em, name, focus)
                else:
                    em.unhandled(kind, path, old, new)
                continue
            if kind == "removed":
                if name in renamed_from:
                    continue        # explained by the rename, not a deletion
                em.unhandled(kind, path, old, new)
                continue

        # --- objects -------------------------------------------------------
        if head == "objects" and len(path) == 2 and kind == "added":
            gen_object_added(em, path[1], new)
            continue
        if (head == "objects" and len(path) == 3 and path[2] == "data"
                and kind == "changed" and isinstance(new, str)):
            gen_object_data_rename(em, path[1], old, new)
            continue
        if (head == "objects" and len(path) == 4 and path[2] == "modifiers"
                and kind == "added"):
            if gen_modifier_added(em, path[1], path[3], new):
                continue
        if (head == "objects" and len(path) == 5 and path[2] == "modifiers"
                and kind == "changed"):
            if gen_modifier_prop(em, path[1], path[3], path[4], new):
                continue

        # --- compositor ----------------------------------------------------
        if (head == "scenes" and len(path) == 5 and path[2] == "compositor"
                and path[3] == "nodes" and kind == "added"):
            if gen_compositor_node(em, path[4], new):
                continue
        if (head == "scenes" and len(path) == 5 and path[2] == "compositor"
                and path[3] == "nodes" and kind == "removed"):
            if gen_compositor_node_removed(em, path[4]):
                continue
        if (head == "scenes" and len(path) == 6 and path[2] == "compositor"
                and path[3] == "nodes" and kind == "changed"):
            if gen_compositor_node_prop(em, path[4], path[5], new):
                continue
        if (head == "scenes" and len(path) == 4 and path[2] == "compositor"
                and path[3] == "links" and kind == "changed"
                and isinstance(new, list)):
            gen_compositor_links(em, new)
            continue

        # --- scene ---------------------------------------------------------
        # top level outliner order -- taken 1:1 from the new scene
        if (head == "scenes" and len(path) == 4 and kind == "changed"
                and path[2] == "master_collection" and path[3] == "children"
                and isinstance(new, list)):
            gen_collection_order(em, "scene.collection", new, "scene root")
            continue
        if (head == "scenes" and len(path) == 4 and path[2] in SCENE_SECTIONS
                and kind == "changed"):
            key = (path[2], path[3])
            if key in BLOCKED:
                em.note("skipped on purpose (project specific): %s" % ".".join(path))
                continue
            if key in NEUTRALISE:
                continue            # emitted below, with a neutral value
            scene_props.append((path[2], path[3], new))
            continue
        # one level deeper, e.g. render.image_settings.file_format
        if (head == "scenes" and len(path) == 5 and path[2] in SCENE_SECTIONS
                and kind == "changed"):
            if (path[3], path[4]) in BLOCKED:
                em.note("skipped on purpose (project specific): %s" % ".".join(path))
                continue
            scene_props.append(("%s.%s" % (path[2], path[3]), path[4], new))
            continue

        em.unhandled(kind, path, old, new)

    # Scene properties are emitted last and in a defined order: colour
    # management would break if written alphabetically.
    def order(item):
        section, prop, _value = item
        try:
            return SCENE_PROP_ORDER.index((section, prop))
        except ValueError:
            return len(SCENE_PROP_ORDER)

    for section, prop, value in sorted(scene_props, key=order):
        gen_scene_prop(em, section, prop, value)

    # Always reset the project-specific values, diff or no diff
    for (section, prop), value in sorted(NEUTRALISE.items()):
        gen_scene_prop(em, section, prop, value)
        em.note("%s.%s reset to %r instead of carrying my project path over"
                % (section, prop, value))

    return em


HEADER = '''# ============================================================================
#  GENERATED MIGRATION -- produced by make_migration.py
# ============================================================================
#  %s  ->  %s
#
#  Converts the original scene into the reworked layout. Read before running:
#  this is generated code, and the TODO list at the bottom shows everything the
#  generator would not guess at.
#
#  USAGE: open the original scene, Text Editor -> Run Script.
#  Safe to run twice -- every step checks before it acts.
#
#  This script removes itself from the .blend when it is done: it is a one-shot
#  job, and only the tool should stay behind. Save under a NEW name afterwards.
# ============================================================================

import bpy
import os

_changes = []


def log(msg):
    _changes.append(msg)
    print("  + %%s" %% msg)
'''

SELF_REMOVE_BLOCK = '''

SELF_NAME = %r


def remove_self():
    """Delete this one-shot script from the .blend -- only the tool should stay.

    Doing this from inside the running script is safe: Blender compiles a text
    block into a code object before executing it, so the datablock is no longer
    needed once we are running inside it.
    """
    text = bpy.data.texts.get(SELF_NAME)
    if text is None:
        # the block may carry a different name -- try the file we run from
        try:
            text = bpy.data.texts.get(os.path.basename(__file__))
        except (NameError, TypeError):
            text = None
    if text is None:
        return
    try:
        bpy.data.texts.remove(text)
        print("  + removed '%%s' from the file -- its job is done" %% SELF_NAME)
    except Exception as exc:
        print("  ! could not remove '%%s': %%s" %% (SELF_NAME, exc))
'''

MIGRATE_DEF = '''

def migrate(scene=None):
    scene = scene or bpy.context.scene
    print("\\n" + "=" * 74)
    print("GENERATED MIGRATION")
    print("=" * 74)
'''

COMPOSITOR_HELPERS = r'''

# ----------------------------------------------------------------------------
#  Compositor helpers
# ----------------------------------------------------------------------------

def compositor_tree(scene):
    """The compositor node tree, whatever this Blender calls it.

    Scene.node_tree up to 4.x, Scene.compositing_node_group in 5.x.
    """
    for attr in ("compositing_node_group", "node_tree", "compositor_node_group"):
        tree = getattr(scene, attr, None)
        if tree is not None and hasattr(tree, "nodes"):
            return tree
    return None


def find_node_group(name):
    """A node group by name: already in the file, or from Blender's own assets.

    No hard-coded path: Blender is asked where its datafiles live, and the
    bundled asset .blend files there are searched. That keeps this working
    across versions and installations.
    """
    group = bpy.data.node_groups.get(name)
    if group is not None:
        return group

    try:
        assets_dir = bpy.utils.system_resource('DATAFILES', path="assets")
    except Exception:
        assets_dir = None
    if not assets_dir or not os.path.isdir(assets_dir):
        return None

    for root, _dirs, files in os.walk(assets_dir):
        for filename in files:
            if not filename.lower().endswith(".blend"):
                continue
            path = os.path.join(root, filename)
            try:
                with bpy.data.libraries.load(path, link=False) as (src, dst):
                    if name not in src.node_groups:
                        continue
                    dst.node_groups = [name]
            except Exception:
                continue
            group = bpy.data.node_groups.get(name)
            if group is not None:
                print("      (appended '%s' from %s)" % (name, filename))
                return group
    return None


def set_socket(node, identifier, value):
    """Set an input socket by its identifier, tolerating type mismatches."""
    for socket in node.inputs:
        if socket.identifier != identifier:
            continue
        try:
            socket.default_value = value
        except (AttributeError, TypeError, ValueError) as exc:
            print("      ! %s.%s: %s" % (node.name, identifier, exc))
        return True
    return False


def socket_by_id(sockets, identifier):
    for socket in sockets:
        if socket.identifier == identifier:
            return socket
    return None


def relink(tree, wanted):
    """Rebuild the tree's links exactly as given.

    Links are a set, not a sequence of settable properties -- the only way to
    reproduce them is to clear and rewire. So look first: rewiring a tree that
    is already wired this way is not a change, and reporting it as one is what
    kept a second run from reaching "0 changes".

    Returns the number of links made, or None when there was nothing to do.
    """
    have = set()
    for link in tree.links:
        try:
            have.add((link.from_node.name, link.from_socket.identifier,
                      link.to_node.name, link.to_socket.identifier))
        except Exception:
            have = None
            break
    if have is not None:
        want = set((f[0], f[1], t[0], t[1]) for f, t in wanted)
        if have == want:
            return None
    for link in list(tree.links):
        tree.links.remove(link)
    made = 0
    for (from_name, from_id), (to_name, to_id) in wanted:
        from_node = tree.nodes.get(from_name)
        to_node = tree.nodes.get(to_name)
        if from_node is None or to_node is None:
            print("      ! link skipped, missing node: %s -> %s"
                  % (from_name, to_name))
            continue
        out_socket = socket_by_id(from_node.outputs, from_id)
        in_socket = socket_by_id(to_node.inputs, to_id)
        if out_socket is None or in_socket is None:
            print("      ! link skipped, missing socket: %s.%s -> %s.%s"
                  % (from_name, from_id, to_name, to_id))
            continue
        tree.links.new(out_socket, in_socket)
        made += 1
    return made

'''

SWITCHER_BLOCK = '''
# ============================================================================
#  EMBEDDED TOOL -- %s
# ============================================================================
#  Installed into the .blend as a text block with "Register" enabled, so it
#  comes back every time the file is opened. For that to work, the user needs
#  Edit > Preferences > Save & Load > Auto Run Python Scripts enabled -- once.
# ============================================================================

TOOL_NAME = %r

TOOL_SOURCE = r\'\'\'%s\'\'\'


def show_in_editor(text):
    """Make the tool the visible text in every Text Editor.

    Without this the editor would sit on an empty slot: the script it currently
    shows is this one, and this one deletes itself a moment later.
    """
    try:
        shown = False
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type != 'TEXT_EDITOR':
                    continue
                for space in area.spaces:
                    if space.type == 'TEXT_EDITOR':
                        space.text = text
                        space.top = 0           # scroll back to the first line
                        shown = True
        if shown:
            print("  . '%%s' is now open in the text editor" %% text.name)
    except Exception as exc:
        print("  ! could not show '%%s' in the editor: %%s" %% (text.name, exc))


def install_tool():
    """Put the tool into this .blend and register it right away.

    Only what actually changes is logged. Registering the classes and pointing
    the editor at the text happen on every run by design -- they are how the
    panel appears without reopening the file -- but they change nothing in the
    .blend, and counting them as changes meant a second run could never report
    zero, which is the check that catches steps assigning blindly.
    """
    text = bpy.data.texts.get(TOOL_NAME)
    if text is None:
        text = bpy.data.texts.new(TOOL_NAME)
        text.write(TOOL_SOURCE)
        log("text block '%%s' created" %% TOOL_NAME)
    elif text.as_string() != TOOL_SOURCE:
        text.clear()
        text.write(TOOL_SOURCE)
        log("text block '%%s' updated to this version" %% TOOL_NAME)

    if not text.use_module:
        text.use_module = True          # this is the "Register" checkbox
        log("'%%s' set to auto-register on file load" %% TOOL_NAME)

    # Register now, so the panel is there without reopening the file.
    # __name__ is deliberately NOT "__main__": that would auto-register on exec
    # and blow up on a second run, when the classes are already registered.
    namespace = {"__name__": "lookdev_embedded_tool", "__file__": TOOL_NAME}
    try:
        exec(compile(TOOL_SOURCE, TOOL_NAME, "exec"), namespace)
        try:
            namespace["unregister"]()   # a previous run may still be active
        except Exception:
            pass
        namespace["register"]()
        print("  . tool registered -- see the N-panel in the 3D viewport")
    except Exception as exc:
        print("  ! could not register '%%s' now: %%s" %% (TOOL_NAME, exc))
        print("    It will load by itself when the file is reopened with "
              "Auto Run Python Scripts enabled.")

    # Do this last: the editor must end up on the tool, not on the empty slot
    # left behind when this script removes itself.
    show_in_editor(text)
'''

WORKSPACE_BLOCK = '''
# ============================================================================
#  EMBEDDED INTERFACE -- the workspaces of the source file
# ============================================================================
#  Blender keeps the interface in the .blend, so a layout can be handed over --
#  but not through the diff. dump_scene.py records no interface data, and the
#  generator could not rebuild one anyway: the Python API has no way to create
#  screen areas, only bpy.ops.screen.area_split, which needs a real window.
#  What does work is appending a finished workspace, so one is carried here,
#  zlib-compressed and base64-encoded.
#
#  Interface data only. bpy.data.libraries.write() with a single workspace
#  pulls in its screens and nothing else -- no objects, meshes, materials or
#  scenes -- so nothing of the original download travels in this blob. That is
#  measured at export time, not assumed (tools/export_workspace.py).
#
#  It is added as its OWN tab. Your existing workspaces are left untouched, and
#  you can rearrange or delete this one like any other.
# ============================================================================

WORKSPACE_STAMP = %r

WORKSPACE_BLEND = (
%s)


_ws_lines = []


def _ws_log(text):
    """Log for the interface step -- to the console AND to a file.

    Everything else in this script reports to stdout, which on Windows means
    the system console, hidden unless someone opened it. For this step that is
    not good enough: if a workspace cannot be replaced, the visible result is a
    file full of "Layout.001" tabs and no reason anywhere.
    """
    print(text)
    _ws_lines.append(text)


def _ws_write_log():
    import tempfile
    folder = os.path.dirname(bpy.data.filepath) or tempfile.gettempdir()
    path = os.path.join(folder, "lookdev_workspace.log.txt")
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\\n".join(_ws_lines) + "\\n")
        print("  log written: %%s" %% path)
    except Exception as exc:
        print("  (could not write %%s: %%s)" %% (path, exc))


def _drop_workspace(old, name, window):
    """Delete one workspace. Returns which route worked, or None.

    Several routes, because which one a given Blender honours is not something
    this script can know: 5.2 has no bpy.data.workspaces.remove() at all
    ('attribute "remove" not found'), and bpy.ops.workspace.delete() answered
    {'CANCELLED'} without raising -- an operator that does nothing is silent,
    so every attempt here is CHECKED by looking the name up again afterwards.

    The operator deletes whatever workspace the CONTEXT holds, not one passed
    to it. Both operator routes therefore confirm that the context really shows
    this workspace before firing -- otherwise it would delete the wrong tab,
    quite possibly one of the ones just installed.
    """
    # 1. batch_remove works on any ID and needs no context at all.
    try:
        bpy.data.batch_remove([old])
        if bpy.data.workspaces.get(name) is None:
            return "batch_remove"
    except Exception as exc:
        _ws_log("      batch_remove: %%s" %% exc)

    # 2. the tab's right-click operator, with the workspace put into the
    #    context for the duration of the call.
    try:
        with bpy.context.temp_override(window=window, workspace=old):
            if getattr(bpy.context, "workspace", None) == old:
                bpy.ops.workspace.delete()
            else:
                _ws_log("      override did not reach context.workspace")
        if bpy.data.workspaces.get(name) is None:
            return "operator, context override"
    except Exception as exc:
        _ws_log("      operator/override: %%s" %% exc)

    # Deliberately NOT a route: assigning window.workspace to the doomed one and
    # firing the operator. The assignment is applied on the next UI pass, so the
    # operator would act on whatever is on screen -- possibly a tab just
    # installed -- and the window would be left pointing at a workspace meant to
    # go, which is what made the tab on screen survive both passes.

    # 3. drop the fake user and let the purge collect it.
    try:
        old.use_fake_user = False
        bpy.data.orphans_purge(do_local_ids=True, do_recursive=False)
        if bpy.data.workspaces.get(name) is None:
            return "orphans_purge"
    except Exception as exc:
        _ws_log("      orphans_purge: %%s" %% exc)

    return None


def install_workspace():
    """Wrapper: this step must never abort the migration, and must always log.

    It runs after the scene is already converted and the tool installed, so an
    exception here would leave the run without its final self-removal for the
    sake of a layout. Whatever happens, the reason ends up in the log file.
    """
    try:
        _install_workspace()
    except Exception as exc:
        import traceback
        _ws_log("  ! the interface step failed: %%s" %% exc)
        for line in traceback.format_exc().splitlines():
            _ws_log("      %%s" %% line)
        _ws_log("    Everything else was applied -- only the layout is missing.")
    finally:
        _ws_write_log()


def _install_workspace():
    """Put the interface from the source file into this one.

    A workspace of the same name is REPLACED, not duplicated: appending a
    "Layout" onto a file that already has one makes Blender call the new one
    "Layout.001", and the user would end up with two tabs of the same name.

    The stamp makes this idempotent -- run the script twice and the second run
    finds the interface already at this version and does nothing. A later
    release with a changed layout carries a different stamp and replaces it.
    """
    import base64
    import zlib
    import tempfile

    _ws_log("  interface stamp %%s" %% WORKSPACE_STAMP)
    for existing in bpy.data.workspaces:
        if existing.get("lookdev_ui") == WORKSPACE_STAMP:
            _ws_log("  already at this version -- nothing to do")
            return
    _ws_log("  workspaces in this file before: %%s"
            %% ", ".join(w.name for w in bpy.data.workspaces))

    tmp = os.path.join(tempfile.gettempdir(), "lookdev_ui_%%d.blend" %% os.getpid())
    wanted, loaded = [], []
    try:
        with open(tmp, "wb") as handle:
            handle.write(zlib.decompress(base64.b64decode(WORKSPACE_BLEND)))
        # load() appends and reports the names as they are in the source file,
        # which is what tells us who replaces whom.
        #
        # Hand it a SEPARATE list. Blender fills data_to in place, so passing
        # the same object we keep the names in turns `wanted` into WorkSpace
        # datablocks behind our back -- and workspaces.get() then raises
        # "key must be a string or tuple, not WorkSpace". str() because the
        # names must survive as plain Python strings either way.
        with bpy.data.libraries.load(tmp) as (src, dst):
            wanted = [str(n) for n in src.workspaces]
            dst.workspaces = list(wanted)
        loaded = [ws for ws in dst.workspaces if ws is not None]
    except Exception as exc:
        _ws_log("  ! could not read the embedded interface: %%s" %% exc)
        _ws_log("    Everything else was applied -- only the layout is missing.")
        return
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

    if len(loaded) != len(wanted):
        _ws_log("  ! %%d of %%d workspaces came through; names left as they are"
                %% (len(loaded), len(wanted)))
        for ws in loaded:
            ws["lookdev_ui"] = WORKSPACE_STAMP
        return

    # Free the names FIRST by renaming the old workspaces aside, then rename the
    # new ones onto them. Renaming always works; removing does not -- Blender
    # refuses to drop a workspace a window is showing. Doing it in this order
    # means the tabs carry the right names even when nothing can be removed.
    doomed = []
    for name, ws in zip(wanted, loaded):
        ws["lookdev_ui"] = WORKSPACE_STAMP
        old = bpy.data.workspaces.get(name)
        if old is None or old == ws:
            _ws_log("  + '%%s' added" %% ws.name)
            continue
        try:
            old.name = "%%s [replaced]" %% name
            doomed.append(old)
        except Exception as exc:
            _ws_log("  ! could not rename the existing '%%s': %%s" %% (name, exc))
            continue
        try:
            ws.name = name
            _ws_log("  + '%%s' replaced" %% name)
        except Exception as exc:
            _ws_log("  ! could not rename '%%s' to '%%s': %%s" %% (ws.name, name, exc))

    # Now drop the old ones.
    #
    # bpy.data.workspaces has no remove() -- Blender 5.2 answers
    # 'attribute "remove" not found'. The only way to drop a workspace is the
    # operator behind the tab's right-click menu, and it acts on the workspace
    # in the CONTEXT, not on one handed to it. Assigning window.workspace does
    # not help: that takes effect on the next UI pass, so the operator would
    # still see the workspace that was active when the script started.
    # temp_override puts the right one in the context for the call.
    #
    # And every attempt is CHECKED by looking. bpy.ops raises only when the
    # poll fails; an operator that does nothing returns {'CANCELLED'} quietly.
    # An earlier version treated "no exception" as success and reported ten
    # removals that never happened.
    # Move off the old tabs BEFORE deleting: Blender will not drop a workspace a
    # window is showing. The assignment only takes effect on the next UI pass,
    # which is why the tab that happens to be open survives the first pass and
    # is retried from a timer below.
    window = getattr(bpy.context, "window", None)
    if window is not None and loaded:
        target = bpy.data.workspaces.get("Layout") or loaded[0]
        try:
            window.workspace = target
            _ws_log("  active tab set to '%%s'" %% target.name)
        except Exception as exc:
            _ws_log("  could not switch to '%%s': %%s" %% (target.name, exc))

    # NOTHING is deleted here. This code runs inside bpy.ops.text.run_script(),
    # and deleting a workspace frees its screens and areas -- including, quite
    # possibly, the one the operator is running in. When the operator then
    # finishes, Blender builds its redo panel for that area and reads freed
    # memory:
    #
    #   EXCEPTION_ACCESS_VIOLATION
    #   ED_area_type_hud_clear <- ED_area_type_hud_ensure <- wm_operator_finished
    #
    # Appending and renaming are data-level and safe. Deleting is not, so it
    # waits for the timer below, which runs after the operator has finished.
    if doomed:
        _ws_retry([old.name for old in doomed], window)
    else:
        _ws_log("  nothing to remove")
        _ws_collapse_outliners(window)
    return

def _ws_collapse_all_levels(area):
    """One level per call; a lookdev scene is nowhere near this deep."""
    for _ in range(12):
        bpy.ops.outliner.show_one_level(open=False)


def _ws_show_tool(area):
    """Put the tool into the text editor.

    install_tool() already does this -- but it runs BEFORE the workspaces are
    appended, so the editor it fills is the one the user had, not the Scripting
    tab that arrives afterwards. That one comes in pointing at a text datablock
    from the source file, which was not appended: an empty slot.
    """
    name = globals().get("TOOL_NAME")
    text = bpy.data.texts.get(name) if name else None
    if text is None:
        return
    for space in area.spaces:
        if space.type == 'TEXT_EDITOR':
            space.text = text
            space.top = 0


def _ws_frame_nodes(area):
    """Frame the node tree -- but only where there is one.

    A Geometry Nodes editor with no matching object, or a Shading editor with
    no active material, has nothing to show. node.view_all() then answers
    "poll() failed, context is incorrect", which is correct behaviour but reads
    like a fault in the log. Ask first.
    """
    for space in area.spaces:
        if space.type != 'NODE_EDITOR':
            continue
        tree = getattr(space, "edit_tree", None) or getattr(space, "node_tree", None)
        if tree is None:
            return
    bpy.ops.node.view_all()


def _ws_show_viewer(area):
    """Point image editors at the Viewer Node image.

    An appended workspace arrives with an empty slot: the space pointed at an
    image datablock in the source file, and only workspaces were appended. The
    compositor's own preview image is what belongs there -- it is what the
    Rendering and Compositing tabs are for.

    "Viewer Node" is Blender's name for it and it exists in any scene whose
    compositor has a Viewer node, which this one does. If it is not there yet
    the slot is left empty rather than filled with something arbitrary.
    """
    image = bpy.data.images.get("Viewer Node")
    if image is None:
        _ws_log("      no 'Viewer Node' image yet -- editor left empty")
        return
    for space in area.spaces:
        if space.type == 'IMAGE_EDITOR':
            space.image = image


def _ws_panel_category():
    """The N-panel tab the add-on lives in, read out of the embedded source.

    Taken from bl_category in the switcher rather than written here as well --
    one place to change it.
    """
    import re
    source = globals().get("TOOL_SOURCE", "")
    found = re.search(r'bl_category\\s*=\\s*"([^"]+)"', source)
    return found.group(1) if found else None


def _ws_open_panel(area):
    """Try to put the add-on's tab in front in the sidebar.

    Region.active_panel_category measured as read-only, but that was on regions
    of no width. Attempt it and record what happened rather than assume: if it
    takes, the converted file opens on the Lookdev tab; if not, the log says so
    and this can be dropped.
    """
    category = _ws_panel_category()
    if not category:
        return
    for region in area.regions:
        if region.type != 'UI':
            continue
        try:
            region.active_panel_category = category
            _ws_log("      sidebar tab set to '%%s'" %% category)
        except Exception as exc:
            _ws_log("      sidebar tab '%%s' not settable: %%s" %% (category, exc))


# What to do in each kind of area once the interface is in place. None of this
# reproduces the source file's view -- that state cannot be read or written.
# These are the deterministic equivalents the API does offer, and they are much
# closer than what an appended workspace arrives with: outliners unfolded to
# every material, node trees parked wherever the region happened to sit, and a
# text editor showing nothing at all.
#
# The image editors get their image set, not their view framed. Framing them
# with image.view_all() was tried and was wrong: the slot holds a 256x256
# placeholder (the source file's own header reads "Render Size 1920 x 1080 /
# Image Size 256 x 256"), so fitting it to the area turned a small square
# sitting inside the render outline into a large one filling the editor. Pan and
# zoom are not reachable anyway; what IS reachable is which image is shown.
_WS_TIDY = {
    'OUTLINER': _ws_collapse_all_levels,
    'NODE_EDITOR': _ws_frame_nodes,
    'TEXT_EDITOR': _ws_show_tool,
    'IMAGE_EDITOR': _ws_show_viewer,
}


def _ws_collapse_outliners(window):
    """Tidy every installed workspace: collapse outliners, frame node trees.

    NOT a copy of the source file's state -- that cannot be read or written.
    SpaceOutliner exposes no treestore, tree, expanded, open or state; the
    expansion lives as references to the datablocks of the file it was saved
    in, so an appended workspace arrives with everything unfolded. Collapsing
    is the nearest thing the API offers, and it is much closer to a lookdev
    file's usual state than a tree opened down to every material.

    The operator needs an outliner in the ACTIVE window, so the workspaces are
    walked one at a time: switch, let the switch land, collapse, move on. It
    ends back on the tab it started from. All of this runs from a timer -- the
    script's own operator has long finished by then.
    """
    if window is None:
        _ws_log("  no window -- the interface is left as it is")
        _ws_write_log()
        return

    started_on = getattr(window, "workspace", None)
    names = [ws.name for ws in bpy.data.workspaces
             if ws.get("lookdev_ui") == WORKSPACE_STAMP]
    state = {"i": 0, "switched": False, "done": 0}

    def step():
        if state["i"] >= len(names):
            if not state.get("returned"):
                if started_on is not None:
                    try:
                        window.workspace = started_on
                    except Exception:
                        pass
                state["returned"] = True
                return 0.2          # let the switch land before the last step

            # The sidebar tab, once, here. Measured: Region.active_panel_category
            # is read-only on a region that has never been drawn, and a workspace
            # the walk only passes through is never drawn. Attempting it per
            # workspace produced ten refusals and one success -- the one that was
            # actually on screen. So it is tried on this tab alone, now that the
            # switch above has landed and it has been drawn.
            screen = getattr(window, "screen", None)
            for area in getattr(screen, "areas", []):
                if area.type == 'VIEW_3D':
                    _ws_open_panel(area)

            _ws_log("  tidied %%d area(s): outliners collapsed, views framed" %% state["done"])
            _ws_log("  (the source file's exact view cannot be carried: the")
            _ws_log("   outliner exposes nothing about expansion, and a region's")
            _ws_log("   pan and zoom are rebuilt on load. Collapsed and framed")
            _ws_log("   is the closest the API allows -- an approximation, not")
            _ws_log("   a copy.)")
            _ws_write_log()
            return None

        ws = bpy.data.workspaces.get(names[state["i"]])
        if ws is None:
            state["i"] += 1
            return 0.05

        if not state["switched"]:
            try:
                window.workspace = ws
            except Exception as exc:
                _ws_log("      could not show '%%s': %%s" %% (ws.name, exc))
                state["i"] += 1
                return 0.05
            state["switched"] = True
            return 0.15                 # let the switch reach the interface

        screen = getattr(window, "screen", None)
        for area in getattr(screen, "areas", []):
            job = _WS_TIDY.get(area.type)
            if job is None:
                continue
            # The override needs the REGION, not just the area: these operators
            # poll on the region type and answer "Expected an Outliner region"
            # when only the area is set. That is what left every outliner open.
            region = None
            for candidate in area.regions:
                if candidate.type == 'WINDOW':
                    region = candidate
                    break
            if region is None:
                continue
            try:
                with bpy.context.temp_override(window=window, area=area,
                                               region=region):
                    job(area)
                state["done"] += 1
            except Exception as exc:
                _ws_log("      %%s in '%%s': %%s" %% (area.type, ws.name, exc))
        state["switched"] = False
        state["i"] += 1
        return 0.05

    try:
        bpy.app.timers.register(step, first_interval=0.2)
    except Exception as exc:
        _ws_log("  could not collapse the outliners (%%s)" %% exc)
        _ws_write_log()


def _ws_retry(names, window):
    """Delete the replaced workspaces, from a timer -- never inline.

    Two reasons this cannot happen while the script is running:

    * Deleting a workspace frees its screens and areas. The script runs inside
      bpy.ops.text.run_script(), and when that operator finishes Blender builds
      its redo panel for the area it ran in. If that area has been freed, the
      access violation is immediate and Blender is gone.
    * The workspace a window is showing cannot be deleted at all, and switching
      away from it is applied on the next UI pass -- which has not happened
      while the script is still running.

    By the time this timer fires the operator has finished and the switch has
    landed, so neither problem applies.
    """
    def again():
        left = []
        for name in names:
            old = bpy.data.workspaces.get(name)
            if old is None:
                _ws_log("      removed '%%s' (after the interface caught up)" %% name)
                continue
            how = _drop_workspace(old, name, window)
            if how:
                _ws_log("      removed '%%s' (%%s, second pass)" %% (name, how))
            else:
                left.append(name)
        if left:
            _ws_log("")
            _ws_log("  %%d old workspace(s) could not be removed:" %% len(left))
            for name in left:
                _ws_log("      %%s" %% name)
            _ws_log("  They are marked [replaced] -- right-click the tab > Delete.")
        else:
            _ws_log("  all old workspaces removed")
        _ws_collapse_outliners(window)
        return None            # one shot

    try:
        bpy.app.timers.register(again, first_interval=0.5)
        _ws_log("  %%d old tab(s) will be removed once the script has finished" %% len(names))
    except Exception as exc:
        _ws_log("  no timer available (%%s) -- these stay:" %% exc)
        for name in names:
            _ws_log("      %%s" %% name)
        _ws_log("  They are marked [replaced] -- right-click the tab > Delete.")
'''



FOOTER = '''
    print("\\n" + "=" * 74)
    print("%s change(s) applied" % len(_changes))
    print("=" * 74)
    print("\\nSave under a NEW name to keep your original download intact.")
    return _changes


if __name__ == "__main__":
    migrate()
'''


def read_tool(path):
    """Read the tool source that gets embedded into the generated script."""
    with open(path, "r", encoding="utf-8") as handle:
        source = handle.read()
    # The source is embedded inside r'''...''' -- verify that survives verbatim.
    if "'''" in source:
        raise SystemExit(
            "Cannot embed %s: it contains ''' which would end the embedded\n"
            "string. Use \"\"\" for docstrings in that file." % path)
    if source.endswith("\\"):
        raise SystemExit("Cannot embed %s: it ends with a backslash." % path)
    return source


def read_workspace(path):
    """Read a workspace .blend and return it as chunked base64 source lines.

    Compressed first: a .blend written by libraries.write() is uncompressed, and
    the payload lands in a file people are asked to read before running it. Every
    kilobyte saved is a kilobyte of opaque blob they do not have to scroll past.
    """
    with open(path, "rb") as handle:
        raw = handle.read()

    # The workspace names are not needed here: the generated code reads them
    # from the file itself via libraries.load(), which is also what tells it
    # which existing workspace each one replaces.
    stamp = hashlib.sha256(raw).hexdigest()[:16]
    packed = base64.b64encode(zlib.compress(raw, 9)).decode("ascii")
    chunks = [packed[i:i + 76] for i in range(0, len(packed), 76)]
    lines = "".join('    "%s"\n' % chunk for chunk in chunks)
    print("  interface: %.0f KB -> %.0f KB embedded (%.0f%%), stamp %s"
          % (len(raw) / 1024.0, len(packed) / 1024.0,
             100.0 * len(packed) / len(raw), stamp))
    return stamp, lines


def render(em, before, after, tool_name=None, tool_source=None, self_name=None,
           workspace_stamp=None, workspace_data=None):
    out = [HEADER % (before.get("blend_file") or "original",
                     after.get("blend_file") or "modified")]

    # module level: helpers first, then the embedded tool, then migrate()
    if em.phases["compositor_nodes"] or em.phases["compositor_links"]:
        out.append(COMPOSITOR_HELPERS)
    if tool_source is not None:
        out.append(SWITCHER_BLOCK % (tool_name, tool_name, tool_source))
    if workspace_data is not None:
        out.append(WORKSPACE_BLOCK % (workspace_stamp, workspace_data))
    if self_name:
        out.append(SELF_REMOVE_BLOCK % self_name)

    out.append(MIGRATE_DEF)
    out.extend(em.body())

    # last steps inside migrate(): the scene is ready, hand over the tool,
    # then clear this one-shot script out of the file
    if tool_source is not None:
        out.append('    print("\\n-- 11. Lookdev tool")')
        out.append("    install_tool()")
        out.append("")
    # After the tool, not before: install_tool() puts the tool into every open
    # Text Editor, and appending the workspace switches the visible one. Doing
    # the layout last also makes it the thing the user is left looking at.
    if workspace_data is not None:
        out.append('    print("\\n-- 12. Workspace")')
        out.append("    install_workspace()")
        out.append("")
    if self_name:
        out.append("    remove_self()")
        out.append("")

    out.append(FOOTER)
    if em.todo:
        out.append("\n# " + "=" * 72)
        out.append("# NOT HANDLED -- decide these by hand")
        out.append("# " + "=" * 72)
        out.extend(em.todo)
    return "\n".join(out)


def main():
    from compare_scenes import diff

    parser = argparse.ArgumentParser(
        description="Turn two dump_scene.py snapshots into a migration script")
    parser.add_argument("original", help="snapshot of the untouched scene")
    parser.add_argument("modified", help="snapshot of your reworked scene")
    parser.add_argument("-o", "--out", default="setup_lookdev_scene.py",
                        help="output script (default setup_lookdev_scene.py). "
                             "This is the name users will see, and the name the "
                             "script removes itself under -- keep it meaningful")
    parser.add_argument("--switcher", default=None, metavar="PATH",
                        help="embed this tool (e.g. config_switcher.py) into the "
                             "generated script: it is installed into the .blend "
                             "as a text block with Register enabled")
    parser.add_argument("--workspace", default=None, metavar="PATH",
                        help="embed this interface .blend (from "
                             "tools/export_workspace.py) so the generated script "
                             "carries the workspaces. A workspace of the same "
                             "name at the user end is replaced, not duplicated. "
                             "Optional: without it the script carries no layout")


    # Works standalone and under Blender's bundled interpreter
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)

    before, after = load(args.original), load(args.modified)
    changes = diff(before, after)
    em = build(before, after, changes)

    tool_name = tool_source = None
    if args.switcher:
        tool_name = os.path.basename(args.switcher)
        tool_source = read_tool(args.switcher)

    workspace_stamp = workspace_data = None
    if args.workspace:
        if not os.path.isfile(args.workspace):
            raise SystemExit("Workspace file not found: %s\n"
                             "Export it first with tools/export_workspace.py, or "
                             "leave --workspace off." % args.workspace)
        workspace_stamp, workspace_data = read_workspace(args.workspace)

    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(render(em, before, after, tool_name, tool_source,
                            self_name=os.path.basename(args.out),
                            workspace_stamp=workspace_stamp,
                            workspace_data=workspace_data))

    print("Wrote %s" % args.out)
    print("  %d step(s) generated" % em.count)
    if tool_source:
        print("  embedded tool: %s (%d lines)"
              % (tool_name, tool_source.count("\n") + 1))
    if workspace_data:
        print("  embedded interface: stamp %s" % workspace_stamp)
    todo_count = len([l for l in em.todo if l.startswith("#   ")])
    print("  %d item(s) left for you to decide" % todo_count)
    if em.todo:
        print("\nNot handled automatically:")
        for line in em.todo:
            print("  " + line.lstrip("# "))
    return 0


if __name__ == "__main__":
    sys.exit(main())

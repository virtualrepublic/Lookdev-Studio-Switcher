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

    PHASES = ("collections", "collection_order", "camera_data", "objects",
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
            "collections": "1. Collections",
            "collection_order": "2. Collection order (exact, as in the new scene)",
            "camera_data": "3. Camera data blocks",
            "objects": "4. Objects (create, place, link)",
            "focus": "5. Focus objects (need the objects above)",
            "renames": "6. Data block renames",
            "modifiers": "7. Modifiers",
            "scene": "8. Scene settings",
            "compositor_nodes": "9. Compositor nodes",
            "compositor_links": "10. Compositor links",
        }
        for name in self.PHASES:
            if not self.phases[name]:
                continue
            out.append('    print("\\n-- %s")' % titles[name])
            out.extend(self.phases[name])
        return out


# --- generators --------------------------------------------------------------

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


def gen_scene_prop(em, section, prop, new):
    target = "scene.%s.%s" % (section, prop)
    if prop in NAME_POINTERS:
        target += ".name"       # a struct, not a string -- see NAME_POINTERS
    em.step("scene", [
        'try:',
        '    if %s != %s:' % (target, lit(new)),
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


def gen_compositor_node_prop(em, name, prop, new):
    if prop not in ("location", "label", "mute"):
        return False
    value = tuple(new) if prop == "location" else lit(new)
    em.step("compositor_nodes", [
        'tree = compositor_tree(scene)',
        'node = tree.nodes.get(%s) if tree else None' % lit(name),
        'if node is not None and tuple(node.%s) != %s:'
        % (prop, value) if prop == "location" else
        'if node is not None and node.%s != %s:' % (prop, value),
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
        '    ' + log_line("compositor rewired: %d link(s)" % len(wanted)),
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
    reproduce them is to clear and rewire.
    """
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
            log("'%%s' is now open in the text editor" %% text.name)
    except Exception as exc:
        print("  ! could not show '%%s' in the editor: %%s" %% (text.name, exc))


def install_tool():
    """Put the tool into this .blend and register it right away."""
    text = bpy.data.texts.get(TOOL_NAME)
    if text is None:
        text = bpy.data.texts.new(TOOL_NAME)
        log("text block '%%s' created" %% TOOL_NAME)
    text.clear()
    text.write(TOOL_SOURCE)

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
        log("tool registered -- see the N-panel in the 3D viewport")
    except Exception as exc:
        print("  ! could not register '%%s' now: %%s" %% (TOOL_NAME, exc))
        print("    It will load by itself when the file is reopened with "
              "Auto Run Python Scripts enabled.")

    # Do this last: the editor must end up on the tool, not on the empty slot
    # left behind when this script removes itself.
    show_in_editor(text)
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


def render(em, before, after, tool_name=None, tool_source=None, self_name=None):
    out = [HEADER % (before.get("blend_file") or "original",
                     after.get("blend_file") or "modified")]

    # module level: helpers first, then the embedded tool, then migrate()
    if em.phases["compositor_nodes"] or em.phases["compositor_links"]:
        out.append(COMPOSITOR_HELPERS)
    if tool_source is not None:
        out.append(SWITCHER_BLOCK % (tool_name, tool_name, tool_source))
    if self_name:
        out.append(SELF_REMOVE_BLOCK % self_name)

    out.append(MIGRATE_DEF)
    out.extend(em.body())

    # last steps inside migrate(): the scene is ready, hand over the tool,
    # then clear this one-shot script out of the file
    if tool_source is not None:
        out.append('    print("\\n-- 9. Lookdev tool")')
        out.append("    install_tool()")
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

    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(render(em, before, after, tool_name, tool_source,
                            self_name=os.path.basename(args.out)))

    print("Wrote %s" % args.out)
    print("  %d step(s) generated" % em.count)
    if tool_source:
        print("  embedded tool: %s (%d lines)"
              % (tool_name, tool_source.count("\n") + 1))
    todo_count = len([l for l in em.todo if l.startswith("#   ")])
    print("  %d item(s) left for you to decide" % todo_count)
    if em.todo:
        print("\nNot handled automatically:")
        for line in em.todo:
            print("  " + line.lstrip("# "))
    return 0


if __name__ == "__main__":
    sys.exit(main())

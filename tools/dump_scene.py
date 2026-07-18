# ============================================================================
#  DUMP SCENE  v1.0  --  structural snapshot of a .blend for comparison
# ============================================================================
#  by Prof. Michael Klein
#     professor@virtualrepublic.org
#
#  Part of the Lookdev Switcher toolchain. Writes everything structural about a
#  .blend to JSON so two scenes can be diffed with compare_scenes.py.
#
#  It deliberately records NO geometry data (only vertex/face counts), so the
#  resulting JSON describes structure, not the author's content.
#
#  USAGE (headless):
#     blender original.blend --background --python dump_scene.py -- --out original.json
#     blender modified.blend --background --python dump_scene.py -- --out modified.json
#
#  Options:
#     --out PATH     output file (default: <blendname>.json)
#     --full         also dump full material/world node trees (large)
# ============================================================================

import bpy
import sys
import json
import argparse

PRECISION = 5

# Properties that only describe UI state or change per session. Dumping them
# would report differences that say nothing about how to rebuild a scene.
MODIFIER_SKIP = ("is_active", "is_override_data", "execution_time",
                 "show_expanded", "persistent_uid")
CONSTRAINT_SKIP = ("error_location", "error_rotation", "is_valid",
                   "is_override_data", "active", "show_expanded")
# Machine dependent -- says nothing about the scene, differs per computer.
# file_extension is read-only: it follows from image_settings.file_format.
RENDER_SKIP = ("threads", "use_lock_interface", "file_extension")
# has_linear_colorspace is read-only too, derived from the format
IMAGE_SETTINGS_SKIP = ("has_linear_colorspace",)
# Derived from white_balance_temperature/_tint. Those two compare equal, yet the
# computed whitepoint drifts in the fourth decimal -- noise, not a setting.
VIEW_SKIP = ("white_balance_whitepoint",)


# --- helpers ----------------------------------------------------------------

def r(value):
    """Round a float so tiny FP noise does not show up as a difference."""
    try:
        return round(float(value), PRECISION)
    except (TypeError, ValueError):
        return None


def vec(value):
    return [r(v) for v in value]


def matrix(m):
    return [vec(row) for row in m]


def jsonable(value):
    """Convert Blender/ID property values into something json can write."""
    if isinstance(value, (bool, int, str)) or value is None:
        return value
    if isinstance(value, float):
        return r(value)
    if hasattr(value, "to_list"):
        return jsonable(value.to_list())
    if hasattr(value, "to_dict"):
        return jsonable(value.to_dict())
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    try:
        return [jsonable(v) for v in value]
    except TypeError:
        return str(value)


def safe(fn, default=None, label=""):
    """Run a dump step; on an API mismatch record the problem instead of dying.

    Blender moves properties between versions (Scene.node_tree vanished in 5.x).
    One such change must not take down the whole run.
    """
    try:
        return fn()
    except Exception as exc:                       # noqa: BLE001 -- report anything
        print("  ! skipped %s: %s: %s" % (label or "section",
                                          type(exc).__name__, exc))
        return {"__error__": "%s: %s" % (type(exc).__name__, exc)} \
            if default is None else default


# The compositor node tree moved between Blender versions:
#   3.x / 4.x : Scene.node_tree
#   5.x       : Scene.compositing_node_group  (confirmed on 5.2 LTS)
# Probe the candidates rather than assuming one API.
COMPOSITOR_ATTRS = ("compositing_node_group", "node_tree", "compositor_node_group")


def get_compositor_tree(scene):
    """Return (node tree, attribute name it was found under) or (None, None)."""
    for attr in COMPOSITOR_ATTRS:
        tree = getattr(scene, attr, None)
        if tree is not None and hasattr(tree, "nodes"):
            return tree, attr
    return None, None


def node_tree_of(owner):
    """Node tree of a world/material/light, if this Blender version has one."""
    tree = getattr(owner, "node_tree", None)
    return tree if tree is not None and hasattr(tree, "nodes") else None


def custom_props(owner):
    """Custom properties, without Blender's internal UI bookkeeping."""
    out = {}
    for key in owner.keys():
        if key in ("_RNA_UI", "cycles"):
            continue
        out[key] = jsonable(owner[key])
    return out


def rna_dump(owner, skip=()):
    """Generic RNA dump: every simple, writable property of a struct.

    Used for constraints and modifiers, where the interesting fields differ per
    type and hand-listing them would miss things.
    """
    out = {}
    for prop in owner.bl_rna.properties:
        ident = prop.identifier
        if ident in ("rna_type",) or ident in skip:
            continue
        try:
            value = getattr(owner, ident)
        except Exception:
            continue

        if prop.type == 'POINTER':
            out[ident] = getattr(value, "name", None) if value else None
        elif prop.type == 'COLLECTION':
            continue                     # handled explicitly where it matters
        elif prop.type == 'FLOAT':
            if getattr(prop, "is_array", False) and prop.array_length:
                out[ident] = vec(value)
            else:
                out[ident] = r(value)
        elif prop.type in ('BOOLEAN', 'INT'):
            if getattr(prop, "is_array", False) and prop.array_length:
                out[ident] = list(value)
            else:
                out[ident] = value
        elif prop.type in ('STRING', 'ENUM'):
            out[ident] = value
    return out


# --- animation --------------------------------------------------------------

def iter_fcurves(action):
    """Yield an action's F-Curves across Blender's two action APIs.

    <= 4.3 : Action.fcurves
    >= 4.4 : slotted actions, Action.layers[].strips[].channelbags[].fcurves
    """
    fcurves = getattr(action, "fcurves", None)
    if fcurves is not None:
        for fcurve in fcurves:
            yield fcurve
        return
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for bag in getattr(strip, "channelbags", []):
                for fcurve in getattr(bag, "fcurves", []):
                    yield fcurve


def dump_animation(anim_data):
    """Action with all f-curves and keyframes (this is what drives the turntable)."""
    if not anim_data or not anim_data.action:
        return None
    curves = []
    for fc in iter_fcurves(anim_data.action):
        curves.append({
            "data_path": fc.data_path,
            "array_index": fc.array_index,
            "extrapolation": fc.extrapolation,
            # f-curve modifiers matter: a Cycles modifier makes a turntable loop
            "modifiers": [m.type for m in fc.modifiers],
            "keyframes": [
                {
                    "frame": r(kp.co[0]),
                    "value": r(kp.co[1]),
                    "interpolation": kp.interpolation,
                    "easing": kp.easing,
                }
                for kp in fc.keyframe_points
            ],
        })
    return {"action": anim_data.action.name, "fcurves": curves}


# --- node trees -------------------------------------------------------------

def dump_node_tree(tree):
    """Nodes with their unlinked input values, plus the links between them."""
    if tree is None:
        return None
    nodes = {}
    for node in tree.nodes:
        entry = {
            "type": node.bl_idname,
            "label": node.label,
            "mute": node.mute,
            "location": vec(node.location),
            "inputs": {},
        }
        for index, socket in enumerate(node.inputs):
            if socket.is_linked or not hasattr(socket, "default_value"):
                continue
            try:
                entry["inputs"][socket.identifier or str(index)] = jsonable(socket.default_value)
            except Exception:
                pass
        # image / node group references are worth knowing about
        for attr in ("image", "node_tree", "object"):
            ref = getattr(node, attr, None)
            if ref is not None:
                entry[attr] = getattr(ref, "name", str(ref))
        nodes[node.name] = entry

    links = [
        {
            "from": [link.from_node.name, link.from_socket.identifier],
            "to": [link.to_node.name, link.to_socket.identifier],
        }
        for link in tree.links
    ]
    return {"nodes": nodes, "links": links}


# --- view layer -------------------------------------------------------------

def dump_layer_collection(lc):
    """The outliner checkboxes, recursively."""
    return {
        "exclude": lc.exclude,
        "hide_viewport": lc.hide_viewport,
        "holdout": lc.holdout,
        "indirect_only": lc.indirect_only,
        "children": {c.name: dump_layer_collection(c) for c in lc.children},
    }


# --- data blocks ------------------------------------------------------------

def dump_collections():
    out = {}
    for coll in bpy.data.collections:
        out[coll.name] = {
            "color_tag": coll.color_tag,
            "hide_viewport": coll.hide_viewport,
            "hide_render": coll.hide_render,
            # Objects are sorted: their order inside a collection is not
            # something you control, and the outliner sorts them anyway.
            "objects": sorted(o.name for o in coll.objects),
            # Children are NOT sorted: collections keep their link order, that
            # is what the outliner shows and what you arranged by hand.
            "children": [c.name for c in coll.children],
            "custom_props": custom_props(coll),
        }
    return out


def dump_objects():
    out = {}
    for obj in bpy.data.objects:
        entry = {
            "type": obj.type,
            "data": getattr(obj.data, "name", None),
            "parent": obj.parent.name if obj.parent else None,
            "parent_type": obj.parent_type,
            "location": vec(obj.location),
            "rotation_mode": obj.rotation_mode,
            "rotation_euler": vec(obj.rotation_euler),
            "scale": vec(obj.scale),
            "matrix_world": matrix(obj.matrix_world),
            "matrix_parent_inverse": matrix(obj.matrix_parent_inverse),
            "hide_viewport": obj.hide_viewport,
            "hide_render": obj.hide_render,
            "hide_select": obj.hide_select,
            "users_collection": sorted(c.name for c in obj.users_collection),
            # Keyed by NAME, not a plain list: a list compares as one opaque blob,
            # so "Subdivision added, levels=2" would only ever show up as two
            # truncated dumps. Keyed, the diff reports it property by property.
            # "index" keeps the stack order visible.
            "constraints": {
                c.name: dict(rna_dump(c, skip=CONSTRAINT_SKIP), type=c.type, index=i)
                for i, c in enumerate(obj.constraints)
            },
            "modifiers": {
                m.name: dict(rna_dump(m, skip=MODIFIER_SKIP), type=m.type, index=i)
                for i, m in enumerate(obj.modifiers)
            },
            "custom_props": custom_props(obj),
            # per object: a single odd action must not cost us all objects
            "animation": safe(lambda o=obj: dump_animation(o.animation_data),
                              label="animation of '%s'" % obj.name),
        }
        if obj.type == 'EMPTY':
            entry["empty_display_type"] = obj.empty_display_type
            entry["empty_display_size"] = r(obj.empty_display_size)
        if obj.type == 'MESH' and obj.data:
            # counts only -- enough to spot changed geometry, without copying it
            entry["mesh_stats"] = {
                "vertices": len(obj.data.vertices),
                "polygons": len(obj.data.polygons),
                "materials": [m.name if m else None for m in obj.data.materials],
            }
        out[obj.name] = entry
    return out


def dump_cameras():
    out = {}
    for cam in bpy.data.cameras:
        dof = cam.dof
        out[cam.name] = {
            "type": cam.type,
            "lens": r(cam.lens),
            "lens_unit": cam.lens_unit,
            "sensor_fit": cam.sensor_fit,
            "sensor_width": r(cam.sensor_width),
            "sensor_height": r(cam.sensor_height),
            "shift_x": r(cam.shift_x),
            "shift_y": r(cam.shift_y),
            "clip_start": r(cam.clip_start),
            "clip_end": r(cam.clip_end),
            "dof": {
                "use_dof": dof.use_dof,
                "focus_object": dof.focus_object.name if dof.focus_object else None,
                "focus_distance": r(dof.focus_distance),
                "aperture_fstop": r(dof.aperture_fstop),
                "aperture_blades": dof.aperture_blades,
                "aperture_rotation": r(dof.aperture_rotation),
                "aperture_ratio": r(dof.aperture_ratio),
            },
            "animation": safe(lambda c=cam: dump_animation(c.animation_data),
                              label="animation of camera '%s'" % cam.name),
        }
    return out


def dump_lights():
    out = {}
    for light in bpy.data.lights:
        out[light.name] = {
            "type": light.type,
            "energy": r(light.energy),
            "color": vec(light.color),
            "shape": getattr(light, "shape", None),
            "size": r(getattr(light, "size", 0.0)),
            "size_y": r(getattr(light, "size_y", 0.0)),
            "use_nodes": getattr(light, "use_nodes", None),
            "animation": safe(lambda l=light: dump_animation(l.animation_data),
                              label="animation of light '%s'" % light.name),
        }
    return out


def dump_worlds(full):
    out = {}
    for world in bpy.data.worlds:
        entry = {
            "use_nodes": getattr(world, "use_nodes", None),
            "color": vec(world.color),
        }
        tree = node_tree_of(world)
        if tree is not None:
            entry["node_tree"] = (dump_node_tree(tree) if full
                                  else {"node_count": len(tree.nodes)})
        out[world.name] = entry
    return out


def dump_materials(full):
    out = {}
    for mat in bpy.data.materials:
        entry = {
            "use_nodes": getattr(mat, "use_nodes", None),
            "blend_method": getattr(mat, "blend_method", None),
            "diffuse_color": vec(mat.diffuse_color),
        }
        tree = node_tree_of(mat)
        if tree is not None:
            entry["node_tree"] = (dump_node_tree(tree) if full
                                  else {"node_count": len(tree.nodes)})
        out[mat.name] = entry
    return out


def dump_render(render):
    """The complete render settings, not a hand-picked subset.

    A hand-picked list silently drops whatever it does not know about -- sample
    counts, denoising, motion blur. Those would then never show up in a diff and
    never get migrated. rna_dump takes every simple property there is.
    """
    entry = rna_dump(render, skip=RENDER_SKIP)
    # image_settings is a pointer, so rna_dump only sees an unnamed struct
    entry["image_settings"] = safe(
        lambda: rna_dump(render.image_settings, skip=IMAGE_SETTINGS_SKIP),
        label="image_settings")
    return entry


def dump_scene(scene, full):
    render = scene.render
    entry = {
        "camera": scene.camera.name if scene.camera else None,
        "world": scene.world.name if scene.world else None,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "frame_step": scene.frame_step,
        "render": safe(lambda: dump_render(render), label="render settings"),
        "unit_settings": {
            "system": scene.unit_settings.system,
            "scale_length": r(scene.unit_settings.scale_length),
            "length_unit": scene.unit_settings.length_unit,
        },
        # Colour management is spread over three structs, not one. Reading only
        # view_settings would miss the display device -- which is where ACES
        # lives -- and the sequencer colour space entirely.
        "view_settings": safe(lambda: rna_dump(scene.view_settings, skip=VIEW_SKIP),
                              label="view_settings"),
        "display_settings": safe(lambda: rna_dump(scene.display_settings),
                                 label="display_settings"),
        "sequencer_colorspace_settings": safe(
            lambda: rna_dump(scene.sequencer_colorspace_settings),
            label="sequencer_colorspace_settings"),
        "markers": {m.name: m.frame for m in scene.timeline_markers},
        "master_collection": {
            "objects": sorted(o.name for o in scene.collection.objects),
            # link order, not sorted -- this is the outliner's top level
            "children": [c.name for c in scene.collection.children],
        },
        "view_layers": {
            vl.name: dump_layer_collection(vl.layer_collection)
            for vl in scene.view_layers
        },
        "use_nodes": getattr(scene, "use_nodes", None),
        "custom_props": custom_props(scene),
    }
    # Engine settings live outside scene.render: samples, denoising, motion blur.
    # Present only when the engine is available, so probe rather than assume.
    for section in ("cycles", "eevee"):
        data = getattr(scene, section, None)
        if data is not None:
            entry[section] = safe(lambda d=data: rna_dump(d), label=section)

    tree, attr = get_compositor_tree(scene)
    if tree is not None:
        entry["compositor_api"] = attr          # which property it was found under
        # In 5.x the compositor is its own datablock, so the migration script may
        # have to create and assign it by name.
        entry["compositor_name"] = getattr(tree, "name", None)
        entry["compositor"] = safe(lambda: dump_node_tree(tree),
                                   label="compositor of scene '%s'" % scene.name)
    return entry


# --- main -------------------------------------------------------------------

def snapshot(full=False, frame=None):
    """Return the whole structural snapshot as plain Python data.

    Plain dicts/lists on purpose: the result survives bpy.ops.wm.open_mainfile(),
    so one session can snapshot several .blend files in a row (see diff_blends.py).

    frame: set every scene to this frame first. Two files saved at different
    current frames would otherwise report every animated object as "changed" --
    a turntable at frame 3 vs frame 140 is not a structural difference.
    """
    if frame is not None:
        for scene in bpy.data.scenes:
            scene.frame_set(frame)
    return {
        "blend_file": bpy.path.basename(bpy.data.filepath),
        "blender_version": bpy.app.version_string,
        "scenes": {s.name: safe(lambda s=s: dump_scene(s, full), label="scene '%s'" % s.name)
                   for s in bpy.data.scenes},
        "collections": safe(dump_collections, label="collections"),
        "objects": safe(dump_objects, label="objects"),
        "cameras": safe(dump_cameras, label="cameras"),
        "lights": safe(dump_lights, label="lights"),
        "worlds": safe(lambda: dump_worlds(full), label="worlds"),
        "materials": safe(lambda: dump_materials(full), label="materials"),
        "counts": {
            "objects": len(bpy.data.objects),
            "collections": len(bpy.data.collections),
            "meshes": len(bpy.data.meshes),
            "materials": len(bpy.data.materials),
            "images": len(bpy.data.images),
            "actions": len(bpy.data.actions),
        },
        "images": sorted(i.name for i in bpy.data.images),
        "actions": sorted(a.name for a in bpy.data.actions),
    }


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="Dump a .blend structure to JSON")
    parser.add_argument("--out", default=None, help="output json path")
    parser.add_argument("--full", action="store_true",
                        help="also dump full material/world node trees")
    parser.add_argument("--frame", type=int, default=0,
                        help="set every scene to this frame first, so animation "
                             "state is not mistaken for a structural change "
                             "(default 0, use -1 to leave the frame alone)")
    args = parser.parse_args(argv)

    out_path = args.out
    if not out_path:
        out_path = (bpy.data.filepath or "scene") + ".json"

    data = snapshot(args.full, None if args.frame < 0 else args.frame)

    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True, ensure_ascii=False)

    print("Wrote %s  (%d objects, %d collections)"
          % (out_path, data["counts"]["objects"], data["counts"]["collections"]))


if __name__ == "__main__":
    main()

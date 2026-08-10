# ============================================================================
#  GENERATED MIGRATION -- produced by make_migration.py
# ============================================================================
#  LOOKDEV_STUDIO_ORIGINAL_520.blend  ->  LOOKDEV_STUDIO_MODIFIED_520.blend
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
    print("  + %s" % msg)



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



# ============================================================================
#  EMBEDDED TOOL -- lookdev_switcher.py
# ============================================================================
#  Installed into the .blend as a text block with "Register" enabled, so it
#  comes back every time the file is opened. For that to work, the user needs
#  Edit > Preferences > Save & Load > Auto Run Python Scripts enabled -- once.
# ============================================================================

TOOL_NAME = 'lookdev_switcher.py'

TOOL_SOURCE = r'''# ============================================================================
#  LOOKDEV SWITCHER  v1.2.3
# ============================================================================
#  by Prof. Michael Klein
#     professor@virtualrepublic.org
#
#  The version above must match bl_info["version"] below -- new-release.ps1
#  refuses to release when they disagree. It used to read "v1.2" while bl_info
#  said (1, 2, 3), which made a current file look stale to anyone reading the
#  first line. A date used to stand here too and rotted the same way; the
#  CHANGELOG and the git history carry that.
#
#  Copyright (C) 2026  Prof. Michael Klein
#
#  This program is free software: you can redistribute it and/or modify it under
#  the terms of the GNU General Public License as published by the Free Software
#  Foundation, either version 3 of the License, or (at your option) any later
#  version.
#
#  This program is distributed in the hope that it will be useful, but WITHOUT
#  ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#  FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#  You should have received a copy of the GNU General Public License along with
#  this program. If not, see <https://www.gnu.org/licenses/>.
#
#  SPDX-License-Identifier: GPL-3.0-or-later
#
#  The licence above covers this script only. The Studio Lookdev scene is not
#  part of it and stays under its author's own terms -- download it yourself:
#
#  albin. (2021, November 10). Studio Lookdev [3D model]. CGTrader.
#      https://www.cgtrader.com/free-3d-models/architectural/other/studio-lookdev
# ----------------------------------------------------------------------------
#  Buttons that each activate one collection (including all of its contents)
#  and set the matching camera as the scene camera, plus "Align & Link Model"
#  for a turntable setup of all models.
#
#  INSTALLATION:
#  1. In Blender open a Text Editor -> Open -> lookdev_switcher.py
#     (or paste the content into a new text block).
#  2. Run Script (play icon). In the N-panel (press N) the "Lookdev" tab
#     appears with the buttons.
#  3. To load it automatically the next time the file is opened:
#     enable "Register" in the Text Editor header and, once,
#     Edit -> Preferences -> Save & Load -> enable "Auto Run Python Scripts".
#
#  CUSTOMIZE:  Names are defined in the CONFIGS list below.
#              The button colors follow the collection color tags in the
#              outliner, so set a color there and the panel follows.
#              A collection without a color tag (e.g. MODEL) stays neutral.
#              The number "01".."08" in CONFIGS is only used to seed a
#              collection that has no color tag yet
#              (01 red, 02 orange, 03 yellow, 04 green, 05 blue,
#               06 violet, 07 pink, 08 brown).
# ============================================================================

bl_info = {
    "name": "Lookdev Switcher",
    "author": "Prof. Michael Klein <professor@virtualrepublic.org>",
    "version": (1, 2, 3),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar (N-Panel) > Lookdev",
    "description": "Collection/camera switcher and turntable setup for lookdev",
    "doc_url": "https://www.cgtrader.com/free-3d-models/architectural/other/studio-lookdev",
    "category": "3D View",
}

import bpy
import mathutils

# (collection name, camera object name, color number "01".."08")
CONFIGS = [
    ("MACRO",  "macro",  "01"),   # red
    ("SMALL",  "small",  "02"),   # orange
    ("MEDIUM", "medium", "03"),   # yellow
    ("LARGE",  "large",  "04"),   # green
]
COLLECTIONS = [c[0] for c in CONFIGS]

# --- FRAME button -------------------------------------------------------------
FRAME_COLLECTION = "FRAME"            # collection for the framing setup
FRAME_CAMERA     = "frame"            # camera used for framing
FRAME_LENS       = 150.0              # focal length in mm
DOF_EMPTY        = "DOF"              # empty in FRAME used as "Focus on Object"
# Slider range for the DOF empty depth, in meters (-200 cm .. 200 cm).
# These are soft limits: you can still type any value into the field.
DOF_DEPTH_MIN    = -2.0
DOF_DEPTH_MAX    = 2.0
# The models rotate on the turntable, so the visible extent is measured at
# these frames and the framing fits the union of all of them.
FRAME_CHECK_FRAMES = (0, 75)
# How much of the frame the model fills. 1.0 = maximum crop (the silhouette
# touches the frame edge); below 1.0 dollies the camera back and leaves a
# margin all around -- a "safe action" border. 0.9 = 5 % on each side.
FRAME_FILL = 0.9

# All collections that switch each other off
ALL_COLLECTIONS = COLLECTIONS + [FRAME_COLLECTION]
# All cameras driven by the DOF / F-Stop settings
ALL_CAMERAS = [c[1] for c in CONFIGS] + [FRAME_CAMERA]

# --- Set Render Path button ---------------------------------------------------
# The output path is set relative to the .blend ("//") so renders always land
# next to the file, never in a machine-specific absolute folder. The folder and
# image prefix follow the SAVED .blend's name (not the scene name). Layout:
#     //Render/<blend file name>/<blend file name>_
# Blender appends the frame number (4 digits) and the extension, e.g. for
# MyProject.blend:
#     Render/MyProject/MyProject_0001.exr
RENDER_SUBDIR = "Render"             # top-level output folder next to the .blend

# --- Align & Link Model button ------------------------------------------------
MODEL_COLLECTION = "MODEL"            # collection holding the imported models
EMPTY_NAME       = "LINKED_ROTATION"  # name of the created empty
ROTATION_TARGET  = "ROTATION_LINK"    # target object for the Child Of constraint
GEO_TYPES = {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}

# --- Auto-collect imported objects into MODEL --------------------------------
# A lightweight timer watches for things that appear (an import, or Add) and
# moves them into MODEL so a freshly imported model lands on the turntable
# without a manual drag.
#
# Two cases, handled differently:
#   * a whole imported COLLECTION is re-parented under MODEL as a child -- the
#     collection and its contents move together (earlier this stripped the
#     objects out and left the imported collection behind, empty);
#   * loose OBJECTS imported without a collection are linked into MODEL directly.
# Only geometry and empties are moved as loose objects; cameras, lights and the
# tool's own rotation empty are left where they are.
AUTO_MODEL_POLL   = 0.5               # seconds between checks for new datablocks
_seen_object_names = set()            # object names known at the previous check
_seen_collection_names = set()        # collection names known at the previous check

# Collections the auto-collect must never pull into MODEL: the lookdev rig's own
# collections, MODEL itself, and RENDER. (They exist at load time, so they are
# never "new" anyway -- this is a belt-and-braces guard.)
PROTECTED_COLLECTIONS = set(ALL_COLLECTIONS) | {MODEL_COLLECTION, "RENDER"}


def _current_object_names():
    return {o.name for o in bpy.data.objects}


def _current_collection_names():
    return {c.name for c in bpy.data.collections}


def _collection_parents(coll):
    """Return the collections (and scene master collections) that link `coll`.

    Blender has no `collection.parent`; a collection's parents are whoever lists
    it in their `children`. The scene master collections count too, so a
    freshly appended collection linked at the scene root is found here.
    """
    parents = []
    for parent in bpy.data.collections:
        if parent != coll and parent.children.get(coll.name) is not None:
            parents.append(parent)
    for scene in bpy.data.scenes:
        if scene.collection.children.get(coll.name) is not None:
            parents.append(scene.collection)
    return parents


def _relink_collection_into_model(coll, model_coll):
    """Link `coll` under MODEL and unlink it from its previous parents.

    Moves the whole collection (with its objects and sub-collections) rather
    than emptying it. Returns True if it ended up under MODEL.
    """
    parents = _collection_parents(coll)
    if model_coll.children.get(coll.name) is None:
        try:
            model_coll.children.link(coll)
        except RuntimeError:
            return False               # would create a cycle -- leave it be
    for parent in parents:
        if parent != model_coll:
            try:
                parent.children.unlink(coll)
            except RuntimeError:
                pass
    return True


def auto_collect_into_model():
    """Move things that appeared since the last check into MODEL.

    A whole imported collection is re-parented under MODEL (contents and all);
    loose imported objects are linked into MODEL individually. Returns the list
    of names that were moved (collections shown with a trailing '/'). Objects
    already in MODEL, non-geometry (cameras, lights) and the rotation empty are
    left alone.
    """
    global _seen_object_names, _seen_collection_names
    model_coll = bpy.data.collections.get(MODEL_COLLECTION)
    current_objs = _current_object_names()
    current_colls = _current_collection_names()
    moved = []
    if model_coll is not None:
        # 1. Whole imported collections -> re-parent the collection under MODEL,
        #    so it keeps its objects instead of being emptied out.
        new_coll_names = current_colls - _seen_collection_names
        new_colls = [bpy.data.collections.get(n) for n in sorted(new_coll_names)]
        new_colls = [c for c in new_colls if c is not None]
        new_set = set(new_colls)
        for coll in new_colls:
            if coll == model_coll or coll.name in PROTECTED_COLLECTIONS:
                continue
            if model_coll.children.get(coll.name) is not None:
                continue                       # already under MODEL
            parents = _collection_parents(coll)
            if not parents:
                continue                       # not in the scene tree (e.g. only instanced)
            if any(p in new_set for p in parents):
                continue                       # nested inside another new collection -- moves with it
            if _relink_collection_into_model(coll, model_coll):
                moved.append(coll.name + "/")

        # 2. Loose objects imported without a collection -> link into MODEL.
        #    Objects that arrived inside a collection moved above are already in
        #    MODEL now, so they fall through the `in model_objs` check.
        model_objs = set(model_coll.all_objects)
        for name in sorted(current_objs - _seen_object_names):
            obj = bpy.data.objects.get(name)
            if obj is None or obj.name == EMPTY_NAME:
                continue
            if obj.type not in GEO_TYPES and obj.type != 'EMPTY':
                continue
            if obj in model_objs:
                continue
            # Leave objects that belong to a newly imported collection we chose
            # not to move (instanced-only, protected): that collection is the
            # import unit, don't strip its contents out.
            if any(c.name in new_coll_names for c in obj.users_collection):
                continue
            for coll in list(obj.users_collection):
                coll.objects.unlink(obj)
            model_coll.objects.link(obj)
            moved.append(name)
    _seen_object_names = current_objs
    _seen_collection_names = current_colls
    return moved


def _auto_model_timer():
    """Timer callback: collect new objects when the panel toggle is on.

    Restricted to OBJECT mode so nothing is relinked mid edit. When the toggle
    is off the baseline is still refreshed, so switching it on later only
    affects things imported from that point on, not everything already there.
    """
    global _seen_object_names, _seen_collection_names
    scene = getattr(bpy.context, "scene", None)
    on = bool(getattr(scene, "lookdev_auto_model", False)) if scene else False
    if on and getattr(bpy.context, "mode", 'OBJECT') == 'OBJECT':
        auto_collect_into_model()
    else:
        _seen_object_names = _current_object_names()
        _seen_collection_names = _current_collection_names()
    return AUTO_MODEL_POLL


def find_layer_collection(layer_coll, name):
    """Recursively find a layer collection by its name."""
    if layer_coll.collection.name == name:
        return layer_coll
    for child in layer_coll.children:
        found = find_layer_collection(child, name)
        if found:
            return found
    return None


def activate_subtree(lc):
    """Activate a layer collection including ALL sub-collections and objects."""
    lc.exclude = False
    lc.hide_viewport = False          # clear temporary hide
    lc.collection.hide_viewport = False
    lc.collection.hide_render = False
    for obj in lc.collection.objects:
        obj.hide_viewport = False     # eye icon in the outliner
        obj.hide_render = False       # camera icon (render)
        obj.hide_set(False)           # H / local hide
    for child in lc.children:
        activate_subtree(child)


def apply_color_tags():
    """Seed the outliner colors from CONFIGS, but never override a manual choice."""
    for coll_name, _cam, num in CONFIGS:
        coll = bpy.data.collections.get(coll_name)
        if coll and coll.color_tag == 'NONE':
            coll.color_tag = 'COLOR_' + num


def collection_icon(coll_name):
    """Return the icon matching the collection's color tag in the outliner.

    Collections without a color tag (e.g. MODEL) get the neutral icon.
    """
    coll = bpy.data.collections.get(coll_name)
    if coll and coll.color_tag != 'NONE':
        return 'COLLECTION_' + coll.color_tag   # -> COLLECTION_COLOR_01 ... _08
    return 'OUTLINER_COLLECTION'                # neutral


def get_dof_empty():
    """Return the DOF empty from the FRAME collection (falls back to any object)."""
    coll = bpy.data.collections.get(FRAME_COLLECTION)
    if coll:
        obj = coll.all_objects.get(DOF_EMPTY)
        if obj:
            return obj
    return bpy.data.objects.get(DOF_EMPTY)


def apply_dof_settings(scene):
    """Push the panel DOF settings onto every lookdev camera.

    FRAME speciality: the frame camera focuses on the DOF empty, and that empty
    is moved along Y by the depth slider.
    """
    for cam_name in ALL_CAMERAS:
        cam = bpy.data.objects.get(cam_name)
        if cam and cam.type == 'CAMERA':
            cam.data.dof.use_dof = scene.lookdev_dof
            cam.data.dof.aperture_fstop = scene.lookdev_fstop

    empty = get_dof_empty()
    if empty:
        empty.location.y = scene.lookdev_dof_depth      # depth slider
        frame_cam = bpy.data.objects.get(FRAME_CAMERA)
        if frame_cam and frame_cam.type == 'CAMERA':
            frame_cam.data.dof.focus_object = empty     # Focus on Object


def _update_dof_settings(self, context):
    """Panel callback: self is the scene."""
    apply_dof_settings(self)


def switch_config(context, coll_name, cam_name):
    """Activate one collection, hide all other lookdev collections, set the camera.

    Returns (camera object or None, list of missing collection names).
    """
    root = context.view_layer.layer_collection
    missing = []
    for name in ALL_COLLECTIONS:
        lc = find_layer_collection(root, name)
        if not lc:
            missing.append(name)
            continue
        if name == coll_name:
            activate_subtree(lc)      # fully activate (incl. contents)
        else:
            lc.exclude = True         # fully hide

    cam = bpy.data.objects.get(cam_name)
    if cam:
        context.scene.camera = cam
    return cam, missing


class SCENE_OT_set_config(bpy.types.Operator):
    bl_idname = "scene.set_config"
    bl_label = "Set Config"
    bl_options = {'REGISTER', 'UNDO'}

    collection: bpy.props.StringProperty()
    camera: bpy.props.StringProperty()

    def execute(self, context):
        cam, missing = switch_config(context, self.collection, self.camera)
        for name in missing:
            self.report({'WARNING'}, "Collection '%s' not found" % name)
        if cam is None:
            self.report({'WARNING'}, "Camera '%s' not found" % self.camera)
        return {'FINISHED'}


def collect_bbox_corners(objects, depsgraph=None):
    """Return all world-space bounding box corners of the given objects.

    Geo objects are measured directly (evaluated through the depsgraph when one is
    given, so modifiers, constraints and animation at the current frame count). A
    collection-instance empty carries no geometry of its own -- its meshes exist
    only as depsgraph instances -- so those are expanded to their evaluated world
    matrices too. That also covers nested and library-linked collections.
    """
    coords = []
    instancers = set()
    for obj in objects:
        if obj.type in GEO_TYPES:
            src = obj.evaluated_get(depsgraph) if depsgraph else obj
            for corner in src.bound_box:
                coords.append(src.matrix_world @ mathutils.Vector(corner))
        elif obj.type == 'EMPTY' and obj.instance_collection is not None:
            instancers.add(obj)

    # Expand collection instances. object_instances yields every instanced object
    # with its evaluated world matrix; keep the ones whose instancer sits in MODEL.
    if instancers and depsgraph is not None:
        for inst in depsgraph.object_instances:
            if not inst.is_instance:
                continue
            parent = inst.parent
            if parent is None or parent.original not in instancers:
                continue
            ob = inst.object
            if ob is None or ob.type not in GEO_TYPES:
                continue
            mw = inst.matrix_world
            for corner in ob.bound_box:
                coords.append(mw @ mathutils.Vector(corner))
    return coords


def visible_geo_objects(objects):
    """Return only the geo objects that are actually visible in the view layer.

    visible_get() covers the eye icon, the monitor icon, local hide (H) and
    excluded collections in one go.
    """
    return [o for o in objects if o.type in GEO_TYPES and o.visible_get()]


def visible_instance_empties(objects):
    """Return visible empties that instance a collection.

    A collection linked or instanced from elsewhere appears as an EMPTY with an
    instance_collection, not as real meshes in MODEL, so it is invisible to a
    plain geo scan and has to be gathered separately for measuring.
    """
    return [o for o in objects
            if o.type == 'EMPTY' and o.instance_collection is not None
            and o.visible_get()]


def compute_bbox_center_floor(objects, depsgraph=None):
    """Return (X center, Y center, Z floor) of the world bounding box of all geo objects."""
    coords = collect_bbox_corners(objects, depsgraph)
    if not coords:
        return None
    xs = [v.x for v in coords]
    ys = [v.y for v in coords]
    zs = [v.z for v in coords]
    return mathutils.Vector((
        (min(xs) + max(xs)) / 2.0,   # X centered
        (min(ys) + max(ys)) / 2.0,   # Y centered
        min(zs),                     # Z at the floor
    ))


def camera_sensor_tangents(cam_data, scene):
    """Return (tan of half horizontal FOV, tan of half vertical FOV).

    Takes the render resolution, pixel aspect and the camera sensor fit into account.
    """
    render = scene.render
    width = render.resolution_x * render.pixel_aspect_x
    height = render.resolution_y * render.pixel_aspect_y
    aspect = width / height

    if cam_data.sensor_fit == 'VERTICAL':
        sensor_y = cam_data.sensor_height
        sensor_x = sensor_y * aspect
    elif cam_data.sensor_fit == 'HORIZONTAL':
        sensor_x = cam_data.sensor_width
        sensor_y = sensor_x / aspect
    else:   # AUTO: sensor_width applies to the longer image axis
        if aspect >= 1.0:
            sensor_x = cam_data.sensor_width
            sensor_y = sensor_x / aspect
        else:
            sensor_y = cam_data.sensor_width
            sensor_x = sensor_y * aspect

    return (sensor_x * 0.5) / cam_data.lens, (sensor_y * 0.5) / cam_data.lens


def fit_camera_to_points(cam_obj, points, scene, fill=1.0):
    """Keep the camera rotation, move it so all points are centered and fill the frame.

    The limiting axis decides the distance, so the models are framed either to
    width or to height depending on the bounding box aspect ratio. ``fill`` is
    the fraction of the frame the model should occupy: 1.0 is maximum crop,
    below 1.0 pulls the camera back and leaves a safe-action margin around it.
    """
    rot = cam_obj.matrix_world.to_3x3().normalized()
    rot_inv = rot.inverted()
    local = [rot_inv @ p for p in points]     # points in camera axes

    xs = [v.x for v in local]
    ys = [v.y for v in local]
    cx = (min(xs) + max(xs)) / 2.0            # centered horizontally
    cy = (min(ys) + max(ys)) / 2.0            # centered vertically

    tan_x, tan_y = camera_sensor_tangents(cam_obj.data, scene)
    # Shrink the effective field of view so the model fills only ``fill`` of it;
    # the camera then sits further back and a margin appears around the subject.
    tan_x *= fill
    tan_y *= fill

    # The camera looks along its local -Z. For every corner the camera must be at
    # least this far back so the corner still fits; the maximum wins.
    cam_z = max(v.z + max(abs(v.x - cx) / tan_x, abs(v.y - cy) / tan_y) for v in local)

    mw = cam_obj.matrix_world.copy()
    mw.translation = rot @ mathutils.Vector((cx, cy, cam_z))
    cam_obj.matrix_world = mw


def fit_camera_clip_end(cam_obj, points, margin=2.0):
    """Push the camera's far clip out so a large model is not clipped away.

    Only ever grows clip_end -- to the distance from the camera to the farthest
    point times a margin -- so small models keep the studio camera's original
    near/far range while big ones get enough depth to render in full.
    """
    if not points:
        return
    cam_pos = cam_obj.matrix_world.translation
    far = max((p - cam_pos).length for p in points)
    needed = far * margin
    if needed > cam_obj.data.clip_end:
        cam_obj.data.clip_end = needed


def get_framing_objects(context, model_coll):
    """Pick the objects to frame and describe where they came from.

    Priority:
    1. selected geo objects that live inside MODEL  (most specific)
    2. any selected geo objects
    3. everything in MODEL                          (nothing selected)
    """
    selected = [o for o in context.selected_objects
                if o.type in GEO_TYPES
                or (o.type == 'EMPTY' and o.instance_collection is not None)]
    if selected:
        in_model = set(model_coll.all_objects)
        inside = [o for o in selected if o in in_model]
        if inside:
            return inside, "%d selected object(s) in '%s'" % (len(inside), MODEL_COLLECTION)
        return selected, "%d selected object(s)" % len(selected)
    return list(model_coll.all_objects), "all of '%s'" % MODEL_COLLECTION


class SCENE_OT_frame_model(bpy.types.Operator):
    bl_idname = "scene.frame_model"
    bl_label = "FRAME"
    bl_description = ("Activate '%s', switch to camera '%s', set %d mm and fit the "
                      "frame to the selection (or all of '%s' if nothing is "
                      "selected) as seen at frames %s"
                      % (FRAME_COLLECTION, FRAME_CAMERA, int(FRAME_LENS),
                         MODEL_COLLECTION,
                         ", ".join(str(f) for f in FRAME_CHECK_FRAMES)))
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene

        model_coll = bpy.data.collections.get(MODEL_COLLECTION)
        if not model_coll:
            self.report({'ERROR'}, "Collection '%s' not found" % MODEL_COLLECTION)
            return {'CANCELLED'}

        # Read the selection BEFORE switching collections: excluding a collection
        # drops its objects from the view layer and thus from the selection.
        targets, source = get_framing_objects(context, model_coll)
        if not targets:
            self.report({'ERROR'}, "Nothing to frame")
            return {'CANCELLED'}

        cam_obj, missing = switch_config(context, FRAME_COLLECTION, FRAME_CAMERA)
        for name in missing:
            self.report({'WARNING'}, "Collection '%s' not found" % name)
        if cam_obj is None or cam_obj.type != 'CAMERA':
            self.report({'ERROR'}, "Camera '%s' not found" % FRAME_CAMERA)
            return {'CANCELLED'}

        original_frame = scene.frame_current
        cam_obj.data.lens = FRAME_LENS        # set focal length before fitting
        apply_dof_settings(scene)             # DOF / F-Stop also apply to this camera

        # The models rotate, so sample the bounding box at every check frame and
        # fit the union: the widest silhouette decides the distance.
        corners = []
        for frame in FRAME_CHECK_FRAMES:
            scene.frame_set(frame)
            depsgraph = context.evaluated_depsgraph_get()
            corners.extend(collect_bbox_corners(targets, depsgraph))

        if not corners:
            self.report({'ERROR'}, "No geometry found to frame")
            scene.frame_set(original_frame)
            return {'CANCELLED'}

        # Fit with a deterministic camera orientation (first check frame),
        # leaving a safe-action margin so the silhouette does not touch the edge.
        scene.frame_set(FRAME_CHECK_FRAMES[0])
        fit_camera_to_points(cam_obj, corners, scene, FRAME_FILL)
        fit_camera_clip_end(cam_obj, corners)   # grow far clip for large models
        context.view_layer.update()

        scene.frame_set(original_frame)       # restore the original frame
        self.report({'INFO'}, "Framed %s with camera '%s' at %d mm (frames %s)"
                    % (source, FRAME_CAMERA, int(FRAME_LENS),
                       ", ".join(str(f) for f in FRAME_CHECK_FRAMES)))
        return {'FINISHED'}


class SCENE_OT_link_model(bpy.types.Operator):
    bl_idname = "scene.link_model"
    bl_label = "Align & Link Model"
    bl_description = ("At frame 0: center empty '%s' on the floor midpoint of the "
                      "models in '%s', group the models, move to '%s' and bind "
                      "via Child Of"
                      % (EMPTY_NAME, MODEL_COLLECTION, ROTATION_TARGET))
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        model_coll = bpy.data.collections.get(MODEL_COLLECTION)
        if not model_coll:
            self.report({'ERROR'}, "Collection '%s' not found" % MODEL_COLLECTION)
            return {'CANCELLED'}

        # Always align and bind at frame 0 (rest pose of ROTATION_LINK)
        scene = context.scene
        original_frame = scene.frame_current
        scene.frame_set(0)

        # Remember top-level groups across ALL sub-collections
        # (all_objects also covers nested collections like 10497_Galaxy_Explorer)
        roots = [o for o in model_coll.all_objects
                 if o.parent is None and o.name != EMPTY_NAME]
        if not roots:
            self.report({'WARNING'}, "No model groups found in '%s'" % MODEL_COLLECTION)

        # 1. Floor midpoint of the overall bounding box (X/Y centered, Z at the floor).
        #    Only visible meshes are measured, so hidden parts cannot skew the result.
        #    A collection instance (a collection linked from elsewhere) has no meshes
        #    of its own, so gather its instancer empties too and let the depsgraph
        #    expand them.
        depsgraph = context.evaluated_depsgraph_get()
        model_objs = model_coll.all_objects
        measurable = (visible_geo_objects(model_objs)
                      + visible_instance_empties(model_objs))
        center = compute_bbox_center_floor(measurable, depsgraph)
        if center is None:
            self.report({'ERROR'}, "No visible geometry found to measure")
            scene.frame_set(original_frame)
            return {'CANCELLED'}

        # Create the empty (or reuse an existing one)
        empty = bpy.data.objects.get(EMPTY_NAME)
        if empty is None or empty.type != 'EMPTY':
            empty = bpy.data.objects.new(EMPTY_NAME, None)
            empty.empty_display_type = 'PLAIN_AXES'
        if empty.name not in model_coll.objects:
            model_coll.objects.link(empty)

        empty.location = center
        empty.rotation_euler = (0.0, 0.0, 0.0)
        context.view_layer.update()   # refresh matrix_world

        # 2. Parent all top-level groups under the empty (keep transform)
        inv = empty.matrix_world.inverted()
        for obj in roots:
            obj.parent = empty
            obj.matrix_parent_inverse = inv

        # 3. Move the empty (with all sub-groups) to the position of ROTATION_LINK,
        #    then bind via Child Of
        target = bpy.data.objects.get(ROTATION_TARGET)
        if target:
            empty.location = target.matrix_world.translation.copy()  # moves everything along
            context.view_layer.update()

            con = empty.constraints.get("Child Of Rotation")
            if con is None:
                con = empty.constraints.new('CHILD_OF')
                con.name = "Child Of Rotation"
            con.target = target
            context.view_layer.update()
            con.inverse_matrix = target.matrix_world.inverted()  # = "Set Inverse"
        else:
            self.report({'WARNING'}, "Target '%s' not found - constraint skipped"
                        % ROTATION_TARGET)

        scene.frame_set(original_frame)   # restore the original frame
        self.report({'INFO'}, "'%s' created and linked at frame 0" % EMPTY_NAME)
        return {'FINISHED'}


class SCENE_OT_set_render_path(bpy.types.Operator):
    bl_idname = "scene.set_render_path"
    bl_label = "Set Render Path"
    bl_description = ("Set the output path relative to this .blend to "
                      "//%s/<blend name>/<blend name>_ so frames render into a "
                      "folder named after the saved project file, e.g. "
                      "%s/MyProject/MyProject_0001.exr"
                      % (RENDER_SUBDIR, RENDER_SUBDIR))
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        # Folder and image prefix follow the SAVED .blend's name, not the scene
        # name. A "//" output path needs a saved file anyway, so require one and
        # report clearly rather than writing next to an unnamed file.
        blend_path = bpy.data.filepath
        if not blend_path:
            self.report({'ERROR'}, "Save the .blend first -- the render path "
                                   "follows the project file name")
            return {'CANCELLED'}
        name = bpy.path.display_name_from_filepath(blend_path)  # .blend name, no extension
        # "//" keeps the path relative to the .blend; forward slashes are
        # accepted by Blender on every OS. The trailing "_" is the image name
        # prefix -- Blender appends the 4-digit frame number and the extension.
        path = "//%s/%s/%s_" % (RENDER_SUBDIR, name, name)
        scene.render.filepath = path
        self.report({'INFO'}, "Render path set to '%s' (+ frame number)" % path)
        return {'FINISHED'}


class VIEW3D_PT_lookdev_switcher(bpy.types.Panel):
    # Read from bl_info, so the panel cannot disagree with the file about which
    # version is registered. Without this there is no way to tell from inside
    # Blender which build a converted scene actually carries.
    bl_label = "Lookdev Switcher %d.%d.%d" % bl_info["version"]
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Lookdev"         # tab name in the N-panel

    def draw(self, context):
        layout = self.layout
        active_cam = context.scene.camera.name if context.scene.camera else ""

        col = layout.column(align=True)
        for coll_name, cam_name, _num in CONFIGS:
            op = col.operator(
                "scene.set_config",
                text=coll_name,
                icon=collection_icon(coll_name),    # color follows the outliner
                depress=(active_cam == cam_name),   # active button stays pressed
            )
            op.collection = coll_name
            op.camera = cam_name

        col.operator("scene.frame_model", text="FRAME",
                     icon=collection_icon(FRAME_COLLECTION),
                     depress=(active_cam == FRAME_CAMERA))

        layout.separator()
        layout.prop(context.scene, "lookdev_dof", toggle=True,
                    icon='CAMERA_DATA')   # depth of field on/off (all cameras)
        col = layout.column(align=True)
        col.enabled = context.scene.lookdev_dof   # only editable when DOF is on
        col.prop(context.scene, "lookdev_fstop")
        col.prop(context.scene, "lookdev_dof_depth", slider=True)

        layout.separator()
        layout.prop(context.scene, "lookdev_auto_model", toggle=True,
                    icon='IMPORT')   # auto-move imports into MODEL
        layout.operator("scene.link_model", text="Align & Link Model",
                        icon=collection_icon(MODEL_COLLECTION))   # neutral, matching MODEL

        layout.separator()
        layout.operator("scene.set_render_path", text="Set Render Path",
                        icon='OUTPUT')   # //Render/<scene>/<scene>_


classes = (SCENE_OT_set_config, SCENE_OT_frame_model, SCENE_OT_link_model,
           SCENE_OT_set_render_path, VIEW3D_PT_lookdev_switcher)

# The tool ships as this text block inside the .blend. Its name is the marker for
# "this is a Lookdev file": if the block is absent after a load, the scene is not
# ours and the panel must not follow it (see _lookdev_load_post).
SELF_TEXT_NAME = "lookdev_switcher.py"
_is_registered = False


@bpy.app.handlers.persistent
def _lookdev_load_post(_dummy):
    """After every File > New / Open, drop the panel unless this is a Lookdev
    file. Class registration is per Blender session, not per .blend, so without
    this the panel would linger in a new scene until Blender is restarted."""
    if bpy.data.texts.get(SELF_TEXT_NAME) is None:
        _teardown()


def _teardown():
    """Remove the panel, its Scene properties and the background timer. Leaves the
    load_post guard in place so it keeps watching later loads. Safe to call when
    nothing is registered."""
    global _is_registered
    if not _is_registered:
        return
    if bpy.app.timers.is_registered(_auto_model_timer):
        bpy.app.timers.unregister(_auto_model_timer)
    for prop in ("lookdev_auto_model", "lookdev_dof_depth",
                 "lookdev_fstop", "lookdev_dof"):
        if hasattr(bpy.types.Scene, prop):
            delattr(bpy.types.Scene, prop)
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    _is_registered = False


def register():
    global _is_registered, _seen_object_names, _seen_collection_names
    if _is_registered:          # re-run in the same session: reset to a clean slate
        _teardown()
    for cls in classes:
        # A previous session or an already-open Lookdev file may have registered an
        # equally-named class; swap it out so re-registration cannot collide.
        existing = getattr(bpy.types, cls.__name__, None)
        if existing is not None:
            try:
                bpy.utils.unregister_class(existing)
            except Exception:
                pass
        bpy.utils.register_class(cls)

    bpy.types.Scene.lookdev_dof = bpy.props.BoolProperty(
        name="Depth of Field",
        description="Enable depth of field on all lookdev cameras",
        default=True,
        update=_update_dof_settings,
    )
    bpy.types.Scene.lookdev_fstop = bpy.props.FloatProperty(
        name="F-Stop",
        description="Aperture f-stop for all lookdev cameras",
        default=2.8,
        min=0.1,
        soft_min=1.0,
        soft_max=22.0,
        precision=2,
        update=_update_dof_settings,
    )
    bpy.types.Scene.lookdev_dof_depth = bpy.props.FloatProperty(
        name="FRAME DOF",
        description=("Y position of the '%s' empty in '%s', used as focus object "
                     "by camera '%s'. Drag within the slider range or type any "
                     "value into the field"
                     % (DOF_EMPTY, FRAME_COLLECTION, FRAME_CAMERA)),
        default=0.0,
        subtype='DISTANCE',           # shown in scene units (cm)
        unit='LENGTH',
        soft_min=DOF_DEPTH_MIN,       # soft limits: typing beyond them is allowed
        soft_max=DOF_DEPTH_MAX,
        update=_update_dof_settings,
    )
    bpy.types.Scene.lookdev_auto_model = bpy.props.BoolProperty(
        name="Auto-collect to MODEL",
        description=("Automatically move newly imported or added geometry into "
                     "'%s' so it lands on the turntable" % MODEL_COLLECTION),
        default=True,
    )

    # Start watching for new objects and collections (imports) to pull into MODEL.
    _seen_object_names = _current_object_names()
    _seen_collection_names = _current_collection_names()
    if not bpy.app.timers.is_registered(_auto_model_timer):
        bpy.app.timers.register(_auto_model_timer, first_interval=AUTO_MODEL_POLL)

    # Guard file loads so the panel does not follow the scene into File > New or an
    # unrelated file. Dedup by name: a reopened file re-runs this as a fresh module
    # with a new function object, so match on __name__, not identity.
    for h in list(bpy.app.handlers.load_post):
        if getattr(h, "__name__", "") == "_lookdev_load_post":
            bpy.app.handlers.load_post.remove(h)
    bpy.app.handlers.load_post.append(_lookdev_load_post)
    _is_registered = True

    apply_color_tags()      # set outliner colors once on load
    # Apply the SAVED panel values to the cameras (do not force fixed defaults,
    # otherwise a reload would reset the f-stop you set earlier).
    scene = getattr(bpy.context, "scene", None)
    if scene is None and bpy.data.scenes:
        scene = bpy.data.scenes[0]
    if scene is not None:
        apply_dof_settings(scene)


def unregister():
    for h in list(bpy.app.handlers.load_post):
        if getattr(h, "__name__", "") == "_lookdev_load_post":
            bpy.app.handlers.load_post.remove(h)
    _teardown()


if __name__ == "__main__":
    register()
'''


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
            print("  . '%s' is now open in the text editor" % text.name)
    except Exception as exc:
        print("  ! could not show '%s' in the editor: %s" % (text.name, exc))


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
        log("text block '%s' created" % TOOL_NAME)
    elif text.as_string() != TOOL_SOURCE:
        text.clear()
        text.write(TOOL_SOURCE)
        log("text block '%s' updated to this version" % TOOL_NAME)

    if not text.use_module:
        text.use_module = True          # this is the "Register" checkbox
        log("'%s' set to auto-register on file load" % TOOL_NAME)

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
        print("  ! could not register '%s' now: %s" % (TOOL_NAME, exc))
        print("    It will load by itself when the file is reopened with "
              "Auto Run Python Scripts enabled.")

    # Do this last: the editor must end up on the tool, not on the empty slot
    # left behind when this script removes itself.
    show_in_editor(text)


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

WORKSPACE_STAMP = 'c1bd8304c174c41c'

WORKSPACE_BLEND = (
    "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"
    "av7KY5nJ3jX1+956v+5Xf3pSvn5r1I/qs5HfrToLl8o5j1fXK22Q31Ky/G4rZdlYfpG/yt2YtFf9"
    "zd+LbEm9fnGW+2Rx7SisI98OyRpS7HVL8cSRYhI8bGhydg3aL7xdg/t70e6JjdLfv8Pve8D57w6b"
    "8h62yHPgaVbUfaGP9edvUWgHljEo45nq7XHKfbxdEyP0ln2cDl73hdw5lxOzeu/uUvtrvHcp71ss"
    "df3SH1hHyNnYX4N2jXI32jXsamDPuUI+psyPx2n7UYEuqjONv+I1Cl+x1LVrMufvm3DOJfJ3aIHw"
    "10Hw1wlwXTkuILtGrQ922LhzLkuyedP1DX+dBH/dAHfsp/yVz6ssAP66Cf56AO7U8Nc7WRB+rdq/"
    "JF2Lv5Sv1ecMzgckq+Aa951Ucb9zSdl3Uqo9Z/AiC8vp/bksM96+UYDnDHoI/uJ7063hb2Wd4F2V"
    "XBcUTlGuxTu2rpOuNgD0VXD+rOX4u5b7XY+/Qyxq/m4Q/mJbJ2WaDia7KL9v6M57Bpa/cYN5j2c/"
    "0g+K/TBN9bm29qovk3dc6v7YjbYkPGzT8vf47U+knH255Ox/pMAeEcQeQc5KWvrauk2y/vvbizV/"
    "3B7tfnrVBXKd58663DW7dXzNqWc91S2bD/WlG4453e86ZdI7Nez6hLPe3/ST7n/2XP3OnZuZHXGo"
    "VH+rVGdfb+96dvsOCdcsqX6FVIddb5TwnizhOlmpL65e1FD77KXbIi/eeaxsizz78DBX5dQJPS+s"
    "vqBHakNPxeq1rlseW1cz/OynWBtqyismbBj/nT+5Zte80y21oXvWjx3PVp9/caR20521Uhtqp8fv"
    "rmlZebrruit/u77ysNNG/rf+iu41r7w06XfHW2R6On80ctvJi1bUrTj0n1un7pu25fO5I+tDE1Zs"
    "3fGXz+vO7502mY8JVb/7zzVjnniheyPwY+qVza47z5tacwrwY+28SzY9dJLfdSbwA9NJL7fJ/Pjd"
    "84e5qha19LQ/ekGPhKPnkJPWup549x81D4x9iuGouf3jn23a8Uub+/Xp73RLOLqx/om/bKmVcNQK"
    "B0m68XePu3KFCVwsruyT6Kq/bJzrnZff7l7t+Gn3TWs+6b5GkiX89e2L9078v7/VuW7686buB0a9"
    "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"
    "zIlf/KO7f/DkC24NT4dy3vJWZTicPH9rDIfPgN8bn4Uyz3/vf/35t1348PyCXSu7XrLrE3a9bNcb"
    "lfWiA/b9W9nn7zrW1ufkyh55Ze33f0/n/Str3r9q8PMr5Tz9Wd33r655/5rB99fjJS+K37+25v3r"
    "Br+67/vd96+vef8pg19bef/+F3fr/9Sa95N3Kfz6vve73/fnVt8/YfCn9r3//x6P3z+x5v2TBvfy"
    "2/Z33z+55n2fnydW3v+S47+HZ3t//8K69q/WI7z/khf5+6AFff6/bOX9UyvvXV8zH7wcf361nLPv"
    "6q6zdePq5ZxdU855g59a6dfra8o5v6acCwY/u1LOU2vKubCmnMrg/h0fp3XtqtaUc8ngF1bKWdfP"
    "l9aU84T380o5q/PPy3liTTmXDe7fWYdHvJzLa8q5YvAnVvp33XhdWVPOVYP7d3w+r6vP1TXlXPN+"
    "XSlnXX2urSnnuvfLu7r7yNU15VxfN+6+DlbKWTcPL61Zp8lKvQI+OGDcIU/2/e3qKr5ds96TQ+al"
    "xw0FL/7XIdQ7jtihHz5+WJzb5N1Wjl1P2PXkuw/fd2/EZ/Ry9ulFH1ju/M7Fub30bRaf8NvuSJzb"
    "f35c+/P5Fuf21Jr+Pbkyjgr9d9IPvxXJISR/9nsD39ztF35mTXDpL7Hrmvuqd96xX/jS5GeP49+N"
    "+/ePmH3gP5Pn9GnoCh9LTpzwnBTs7bzN+Xg7/Qv7Bf/erdovnH/Lm84//Ja3vvbhR2C+MMt2ijGj"
    "rqf9rL5lHvMnn376S4ET7kL/6PVOz6OTa+ZRcuB6/ZWHkrNviOQtyOs8+svy4g/e1Z1Hv+uurrzl"
    "r991+DyK5Fkyj37wrp89jn/r59HbIryHeaRPewe2ufPWjgvP8Tw6v2YeVYfUw+ThMoeywbzYydN5"
    "WU7S4aKaFINsfmuq1r/y9NNPY2y+OtEx+upnoZ3VmnZeMvj5Ne1t24kGNib8b/JJPrilMYK61pdK"
    "O79XPvxeSfs1/r3gDrTz0pp2PmHw6hbbOZ8Xs3Fza+38fZ/Qdn7sLm3nhVVGbZS+bPW5cpPz3tt5"
    "eU07r970vI3bOSgn5a2hP7Tzl6ydP2Xj+VO38P41q6dfP/eAdh4/1j538hA8fz1q9+fa+zH8C1fe"
    "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"
    "eb4="
)


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
            handle.write("\n".join(_ws_lines) + "\n")
        print("  log written: %s" % path)
    except Exception as exc:
        print("  (could not write %s: %s)" % (path, exc))


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
        _ws_log("      batch_remove: %s" % exc)

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
        _ws_log("      operator/override: %s" % exc)

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
        _ws_log("      orphans_purge: %s" % exc)

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
        _ws_log("  ! the interface step failed: %s" % exc)
        for line in traceback.format_exc().splitlines():
            _ws_log("      %s" % line)
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

    _ws_log("  interface stamp %s" % WORKSPACE_STAMP)
    for existing in bpy.data.workspaces:
        if existing.get("lookdev_ui") == WORKSPACE_STAMP:
            _ws_log("  already at this version -- nothing to do")
            return
    _ws_log("  workspaces in this file before: %s"
            % ", ".join(w.name for w in bpy.data.workspaces))

    tmp = os.path.join(tempfile.gettempdir(), "lookdev_ui_%d.blend" % os.getpid())
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
        _ws_log("  ! could not read the embedded interface: %s" % exc)
        _ws_log("    Everything else was applied -- only the layout is missing.")
        return
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

    if len(loaded) != len(wanted):
        _ws_log("  ! %d of %d workspaces came through; names left as they are"
                % (len(loaded), len(wanted)))
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
            _ws_log("  + '%s' added" % ws.name)
            continue
        try:
            old.name = "%s [replaced]" % name
            doomed.append(old)
        except Exception as exc:
            _ws_log("  ! could not rename the existing '%s': %s" % (name, exc))
            continue
        try:
            ws.name = name
            _ws_log("  + '%s' replaced" % name)
        except Exception as exc:
            _ws_log("  ! could not rename '%s' to '%s': %s" % (ws.name, name, exc))

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
            _ws_log("  active tab set to '%s'" % target.name)
        except Exception as exc:
            _ws_log("  could not switch to '%s': %s" % (target.name, exc))

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
    found = re.search(r'bl_category\s*=\s*"([^"]+)"', source)
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
            _ws_log("      sidebar tab set to '%s'" % category)
        except Exception as exc:
            _ws_log("      sidebar tab '%s' not settable: %s" % (category, exc))


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

            _ws_log("  tidied %d area(s): outliners collapsed, views framed" % state["done"])
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
                _ws_log("      could not show '%s': %s" % (ws.name, exc))
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
                _ws_log("      %s in '%s': %s" % (area.type, ws.name, exc))
        state["switched"] = False
        state["i"] += 1
        return 0.05

    try:
        bpy.app.timers.register(step, first_interval=0.2)
    except Exception as exc:
        _ws_log("  could not collapse the outliners (%s)" % exc)
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
                _ws_log("      removed '%s' (after the interface caught up)" % name)
                continue
            how = _drop_workspace(old, name, window)
            if how:
                _ws_log("      removed '%s' (%s, second pass)" % (name, how))
            else:
                left.append(name)
        if left:
            _ws_log("")
            _ws_log("  %d old workspace(s) could not be removed:" % len(left))
            for name in left:
                _ws_log("      %s" % name)
            _ws_log("  They are marked [replaced] -- right-click the tab > Delete.")
        else:
            _ws_log("  all old workspaces removed")
        _ws_collapse_outliners(window)
        return None            # one shot

    try:
        bpy.app.timers.register(again, first_interval=0.5)
        _ws_log("  %d old tab(s) will be removed once the script has finished" % len(names))
    except Exception as exc:
        _ws_log("  no timer available (%s) -- these stay:" % exc)
        for name in names:
            _ws_log("      %s" % name)
        _ws_log("  They are marked [replaced] -- right-click the tab > Delete.")



SELF_NAME = 'setup_lookdev_scene.py'


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
        print("  + removed '%s' from the file -- its job is done" % SELF_NAME)
    except Exception as exc:
        print("  ! could not remove '%s': %s" % (SELF_NAME, exc))



def migrate(scene=None):
    scene = scene or bpy.context.scene
    print("\n" + "=" * 74)
    print("GENERATED MIGRATION")
    print("=" * 74)

    print("\n-- 1. Collections")
    # new collection: FRAME
    coll = bpy.data.collections.get('FRAME')
    if coll is None:
        coll = bpy.data.collections.new('FRAME')
        log('collection FRAME created')
    coll.color_tag = 'COLOR_05'
    if 'FRAME' not in scene.collection.children:
        scene.collection.children.link(coll)
        log('collection FRAME linked into the scene')

    # collection LARGE: color_tag
    coll = bpy.data.collections.get('LARGE')
    if coll and coll.color_tag != 'COLOR_04':
        coll.color_tag = 'COLOR_04'
        log('LARGE.color_tag -> COLOR_04')

    # collection MEDIUM: color_tag
    coll = bpy.data.collections.get('MEDIUM')
    if coll and coll.color_tag != 'COLOR_03':
        coll.color_tag = 'COLOR_03'
        log('MEDIUM.color_tag -> COLOR_03')

    # new collection: MODEL
    coll = bpy.data.collections.get('MODEL')
    if coll is None:
        coll = bpy.data.collections.new('MODEL')
        log('collection MODEL created')
    coll.color_tag = 'NONE'
    if 'MODEL' not in scene.collection.children:
        scene.collection.children.link(coll)
        log('collection MODEL linked into the scene')

    # collection RENDER: color_tag
    coll = bpy.data.collections.get('RENDER')
    if coll and coll.color_tag != 'COLOR_06':
        coll.color_tag = 'COLOR_06'
        log('RENDER.color_tag -> COLOR_06')

    # collection SMALL: color_tag
    coll = bpy.data.collections.get('SMALL')
    if coll and coll.color_tag != 'COLOR_02':
        coll.color_tag = 'COLOR_02'
        log('SMALL.color_tag -> COLOR_02')

    print("\n-- 2. Collection order (exact, as in the new scene)")
    # exact child order of scene root
    container = scene.collection
    desired = ['MACRO', 'SMALL', 'MEDIUM', 'LARGE', 'FRAME', 'RENDER', 'MODEL']
    current = [c.name for c in container.children]
    if current != desired:
        existing = list(container.children)
        extras = [c for c in existing if c.name not in desired]
        for child in existing:
            container.children.unlink(child)
        for name in desired:
            coll = bpy.data.collections.get(name)
            if coll:
                container.children.link(coll)
        for child in extras:      # anything unplanned goes last, never lost
            container.children.link(child)
        log('scene root order: MACRO, SMALL, MEDIUM, LARGE, FRAME, RENDER, MODEL')

    print("\n-- 3. Camera data blocks")
    # new camera data: Camera_frame
    data = bpy.data.cameras.get('Camera_frame')
    if data is None:
        data = bpy.data.cameras.new('Camera_frame')
        log('camera data Camera_frame created')
    data.lens = 150.0
    data.lens_unit = 'MILLIMETERS'
    data.sensor_fit = 'AUTO'
    data.sensor_width = 36.0
    data.sensor_height = 24.0
    data.shift_x = 0.0
    data.shift_y = 0.0
    data.clip_start = 0.1
    data.clip_end = 1000.0
    data.dof.use_dof = True
    data.dof.focus_distance = 10.0
    data.dof.aperture_fstop = 22.0
    data.dof.aperture_blades = 0
    data.dof.aperture_rotation = 0.0
    data.dof.aperture_ratio = 1.0

    # configure camera data: Camera_large
    data = bpy.data.cameras.get('Camera_large')
    if data:
        data.lens = 100.0
        data.lens_unit = 'MILLIMETERS'
        data.sensor_fit = 'AUTO'
        data.sensor_width = 36.0
        data.sensor_height = 24.0
        data.shift_x = 0.0
        data.shift_y = 0.0
        data.clip_start = 0.1
        data.clip_end = 1000.0
        data.dof.use_dof = True
        data.dof.focus_distance = 10.394
        data.dof.aperture_fstop = 22.0
        data.dof.aperture_blades = 12
        data.dof.aperture_rotation = 0.0
        data.dof.aperture_ratio = 1.0

    # configure camera data: Camera_macro
    data = bpy.data.cameras.get('Camera_macro')
    if data:
        data.lens = 150.0
        data.lens_unit = 'MILLIMETERS'
        data.sensor_fit = 'AUTO'
        data.sensor_width = 36.0
        data.sensor_height = 24.0
        data.shift_x = 0.0
        data.shift_y = 0.0
        data.clip_start = 0.1
        data.clip_end = 1000.0
        data.dof.use_dof = True
        data.dof.focus_distance = 10.0
        data.dof.aperture_fstop = 22.0
        data.dof.aperture_blades = 0
        data.dof.aperture_rotation = 0.0
        data.dof.aperture_ratio = 1.0

    # configure camera data: Camera_medium
    data = bpy.data.cameras.get('Camera_medium')
    if data:
        data.lens = 100.0
        data.lens_unit = 'MILLIMETERS'
        data.sensor_fit = 'AUTO'
        data.sensor_width = 36.0
        data.sensor_height = 24.0
        data.shift_x = 0.0
        data.shift_y = 0.0
        data.clip_start = 0.1
        data.clip_end = 1000.0
        data.dof.use_dof = True
        data.dof.focus_distance = 10.394
        data.dof.aperture_fstop = 22.0
        data.dof.aperture_blades = 12
        data.dof.aperture_rotation = 0.0
        data.dof.aperture_ratio = 1.0

    # configure camera data: Camera_small
    data = bpy.data.cameras.get('Camera_small')
    if data:
        data.lens = 150.0
        data.lens_unit = 'MILLIMETERS'
        data.sensor_fit = 'AUTO'
        data.sensor_width = 36.0
        data.sensor_height = 24.0
        data.shift_x = 0.0
        data.shift_y = 0.0
        data.clip_start = 0.1
        data.clip_end = 1000.0
        data.dof.use_dof = True
        data.dof.focus_distance = 10.0
        data.dof.aperture_fstop = 22.0
        data.dof.aperture_blades = 0
        data.dof.aperture_rotation = 0.0
        data.dof.aperture_ratio = 1.0

    print("\n-- 4. Objects (create, place, link)")
    # new object: DOF (EMPTY)
    obj = bpy.data.objects.get('DOF')
    if obj is None:
        obj = bpy.data.objects.new('DOF', None)
        log('object DOF created')
    obj.empty_display_type = 'PLAIN_AXES'
    obj.empty_display_size = 1.0
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    coll = bpy.data.collections.get('FRAME')
    if coll and 'DOF' not in coll.objects:
        coll.objects.link(obj)
        log('DOF linked into FRAME')

    # new object: frame (CAMERA)
    obj = bpy.data.objects.get('frame')
    if obj is None:
        obj = bpy.data.objects.new('frame', bpy.data.cameras['Camera_frame'])
        log('object frame created')
    obj.location = (0.0, -2.43436, 0.49423)
    obj.rotation_euler = (1.35075, -0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    coll = bpy.data.collections.get('FRAME')
    if coll and 'frame' not in coll.objects:
        coll.objects.link(obj)
        log('frame linked into FRAME')

    print("\n-- 5. Focus objects (need the objects above)")
    # focus object of Camera_frame
    data = bpy.data.cameras.get('Camera_frame')
    target = bpy.data.objects.get('DOF')
    if data and target and data.dof.focus_object is not target:
        data.dof.focus_object = target
        log('Camera_frame focuses on DOF')

    # focus object of Camera_macro
    data = bpy.data.cameras.get('Camera_macro')
    target = bpy.data.objects.get('ROTATION_LINK')
    if data and target and data.dof.focus_object is not target:
        data.dof.focus_object = target
        log('Camera_macro focuses on ROTATION_LINK')

    # focus object of Camera_small
    data = bpy.data.cameras.get('Camera_small')
    target = bpy.data.objects.get('ROTATION_LINK')
    if data and target and data.dof.focus_object is not target:
        data.dof.focus_object = target
        log('Camera_small focuses on ROTATION_LINK')

    print("\n-- 6. Data block renames")
    # rename data of 'large': Camera.003 -> Camera_large
    obj = bpy.data.objects.get('large')
    if obj and obj.data and obj.data.name != 'Camera_large':
        obj.data.name = 'Camera_large'
        log('large data Camera.003 -> Camera_large')

    # rename data of 'macro': Camera.001 -> Camera_macro
    obj = bpy.data.objects.get('macro')
    if obj and obj.data and obj.data.name != 'Camera_macro':
        obj.data.name = 'Camera_macro'
        log('macro data Camera.001 -> Camera_macro')

    # rename data of 'medium': Camera -> Camera_medium
    obj = bpy.data.objects.get('medium')
    if obj and obj.data and obj.data.name != 'Camera_medium':
        obj.data.name = 'Camera_medium'
        log('medium data Camera -> Camera_medium')

    # rename data of 'small': Camera.002 -> Camera_small
    obj = bpy.data.objects.get('small')
    if obj and obj.data and obj.data.name != 'Camera_small':
        obj.data.name = 'Camera_small'
        log('small data Camera.002 -> Camera_small')

    print("\n-- 7. Modifiers")
    # new modifier on 'GPM.005': Subdivision (SUBSURF)
    obj = bpy.data.objects.get('GPM.005')
    if obj:
        mod = obj.modifiers.get('Subdivision')
        if mod is None:
            mod = obj.modifiers.new('Subdivision', 'SUBSURF')
            log('GPM.005: Subdivision modifier added')
        if getattr(mod, 'adaptive_object_edge_length', None) != 0.01:
            try:
                mod.adaptive_object_edge_length = 0.01
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'adaptive_pixel_size', None) != 1.0:
            try:
                mod.adaptive_pixel_size = 1.0
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'adaptive_space', None) != 'PIXEL':
            try:
                mod.adaptive_space = 'PIXEL'
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'boundary_smooth', None) != 'ALL':
            try:
                mod.boundary_smooth = 'ALL'
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'levels', None) != 2:
            try:
                mod.levels = 2
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'open_adaptive_subdivision_panel', None) != False:
            try:
                mod.open_adaptive_subdivision_panel = False
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'open_advanced_panel', None) != False:
            try:
                mod.open_advanced_panel = False
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'quality', None) != 3:
            try:
                mod.quality = 3
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'render_levels', None) != 2:
            try:
                mod.render_levels = 2
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'show_in_editmode', None) != True:
            try:
                mod.show_in_editmode = True
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'show_on_cage', None) != False:
            try:
                mod.show_on_cage = False
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'show_only_control_edges', None) != True:
            try:
                mod.show_only_control_edges = True
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'show_render', None) != True:
            try:
                mod.show_render = True
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'show_viewport', None) != True:
            try:
                mod.show_viewport = True
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'subdivision_type', None) != 'CATMULL_CLARK':
            try:
                mod.subdivision_type = 'CATMULL_CLARK'
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'use_adaptive_subdivision', None) != False:
            try:
                mod.use_adaptive_subdivision = False
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'use_apply_on_spline', None) != False:
            try:
                mod.use_apply_on_spline = False
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'use_creases', None) != True:
            try:
                mod.use_creases = True
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'use_custom_normals', None) != False:
            try:
                mod.use_custom_normals = False
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'use_limit_surface', None) != True:
            try:
                mod.use_limit_surface = True
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'use_pin_to_last', None) != False:
            try:
                mod.use_pin_to_last = False
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'uv_smooth', None) != 'PRESERVE_BOUNDARIES':
            try:
                mod.uv_smooth = 'PRESERVE_BOUNDARIES'
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version

    # new modifier on 'TTPM': Subdivision (SUBSURF)
    obj = bpy.data.objects.get('TTPM')
    if obj:
        mod = obj.modifiers.get('Subdivision')
        if mod is None:
            mod = obj.modifiers.new('Subdivision', 'SUBSURF')
            log('TTPM: Subdivision modifier added')
        if getattr(mod, 'adaptive_object_edge_length', None) != 0.01:
            try:
                mod.adaptive_object_edge_length = 0.01
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'adaptive_pixel_size', None) != 1.0:
            try:
                mod.adaptive_pixel_size = 1.0
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'adaptive_space', None) != 'PIXEL':
            try:
                mod.adaptive_space = 'PIXEL'
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'boundary_smooth', None) != 'ALL':
            try:
                mod.boundary_smooth = 'ALL'
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'levels', None) != 2:
            try:
                mod.levels = 2
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'open_adaptive_subdivision_panel', None) != False:
            try:
                mod.open_adaptive_subdivision_panel = False
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'open_advanced_panel', None) != False:
            try:
                mod.open_advanced_panel = False
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'quality', None) != 3:
            try:
                mod.quality = 3
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'render_levels', None) != 2:
            try:
                mod.render_levels = 2
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'show_in_editmode', None) != True:
            try:
                mod.show_in_editmode = True
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'show_on_cage', None) != False:
            try:
                mod.show_on_cage = False
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'show_only_control_edges', None) != True:
            try:
                mod.show_only_control_edges = True
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'show_render', None) != True:
            try:
                mod.show_render = True
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'show_viewport', None) != True:
            try:
                mod.show_viewport = True
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'subdivision_type', None) != 'CATMULL_CLARK':
            try:
                mod.subdivision_type = 'CATMULL_CLARK'
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'use_adaptive_subdivision', None) != False:
            try:
                mod.use_adaptive_subdivision = False
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'use_apply_on_spline', None) != False:
            try:
                mod.use_apply_on_spline = False
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'use_creases', None) != True:
            try:
                mod.use_creases = True
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'use_custom_normals', None) != False:
            try:
                mod.use_custom_normals = False
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'use_limit_surface', None) != True:
            try:
                mod.use_limit_surface = True
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'use_pin_to_last', None) != False:
            try:
                mod.use_pin_to_last = False
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version
        if getattr(mod, 'uv_smooth', None) != 'PRESERVE_BOUNDARIES':
            try:
                mod.uv_smooth = 'PRESERVE_BOUNDARIES'
            except (AttributeError, TypeError):
                pass    # read-only or unknown in this version

    print("\n-- 8. Scene settings")
    # view_settings.view_transform
    try:
        if scene.view_settings.view_transform != 'ACES 2.0':
            scene.view_settings.view_transform = 'ACES 2.0'
            log('view_settings.view_transform -> ACES 2.0')
    except (AttributeError, TypeError) as exc:
        log('!! skipped view_settings.view_transform: ' + str(exc))

    # view_settings.look
    try:
        if scene.view_settings.look != 'ACES 2.0 - Reference Gamut Compression':
            scene.view_settings.look = 'ACES 2.0 - Reference Gamut Compression'
            log('view_settings.look -> ACES 2.0 - Reference Gamut Compression')
    except (AttributeError, TypeError) as exc:
        log('!! skipped view_settings.look: ' + str(exc))

    # render.image_settings.media_type
    try:
        if scene.render.image_settings.media_type != 'MULTI_LAYER_IMAGE':
            scene.render.image_settings.media_type = 'MULTI_LAYER_IMAGE'
            log('render.image_settings.media_type -> MULTI_LAYER_IMAGE')
    except (AttributeError, TypeError) as exc:
        log('!! skipped render.image_settings.media_type: ' + str(exc))

    # render.image_settings.file_format
    try:
        if scene.render.image_settings.file_format != 'OPEN_EXR_MULTILAYER':
            scene.render.image_settings.file_format = 'OPEN_EXR_MULTILAYER'
            log('render.image_settings.file_format -> OPEN_EXR_MULTILAYER')
    except (AttributeError, TypeError) as exc:
        log('!! skipped render.image_settings.file_format: ' + str(exc))

    # render.image_settings.color_depth
    try:
        if scene.render.image_settings.color_depth != '16':
            scene.render.image_settings.color_depth = '16'
            log('render.image_settings.color_depth -> 16')
    except (AttributeError, TypeError) as exc:
        log('!! skipped render.image_settings.color_depth: ' + str(exc))

    # render.image_settings.exr_codec
    try:
        if scene.render.image_settings.exr_codec != 'DWAB':
            scene.render.image_settings.exr_codec = 'DWAB'
            log('render.image_settings.exr_codec -> DWAB')
    except (AttributeError, TypeError) as exc:
        log('!! skipped render.image_settings.exr_codec: ' + str(exc))

    # render.image_settings.linear_colorspace_settings.name
    try:
        if scene.render.image_settings.linear_colorspace_settings.name != 'ACEScg':
            scene.render.image_settings.linear_colorspace_settings.name = 'ACEScg'
            log('render.image_settings.linear_colorspace_settings.name -> ACEScg')
    except (AttributeError, TypeError) as exc:
        log('!! skipped render.image_settings.linear_colorspace_settings.name: ' + str(exc))

    # cycles.adaptive_min_samples
    try:
        if scene.cycles.adaptive_min_samples != 0:
            scene.cycles.adaptive_min_samples = 0
            log('cycles.adaptive_min_samples -> 0')
    except (AttributeError, TypeError) as exc:
        log('!! skipped cycles.adaptive_min_samples: ' + str(exc))

    # cycles.adaptive_threshold
    try:
        if abs(scene.cycles.adaptive_threshold - 0.01) > max(1e-6, abs(0.01) * 1e-6):
            scene.cycles.adaptive_threshold = 0.01
            log('cycles.adaptive_threshold -> 0.01')
    except (AttributeError, TypeError) as exc:
        log('!! skipped cycles.adaptive_threshold: ' + str(exc))

    # cycles.caustics_reflective
    try:
        if scene.cycles.caustics_reflective != True:
            scene.cycles.caustics_reflective = True
            log('cycles.caustics_reflective -> True')
    except (AttributeError, TypeError) as exc:
        log('!! skipped cycles.caustics_reflective: ' + str(exc))

    # cycles.caustics_refractive
    try:
        if scene.cycles.caustics_refractive != True:
            scene.cycles.caustics_refractive = True
            log('cycles.caustics_refractive -> True')
    except (AttributeError, TypeError) as exc:
        log('!! skipped cycles.caustics_refractive: ' + str(exc))

    # cycles.diffuse_bounces
    try:
        if scene.cycles.diffuse_bounces != 32:
            scene.cycles.diffuse_bounces = 32
            log('cycles.diffuse_bounces -> 32')
    except (AttributeError, TypeError) as exc:
        log('!! skipped cycles.diffuse_bounces: ' + str(exc))

    # cycles.film_transparent_glass
    try:
        if scene.cycles.film_transparent_glass != True:
            scene.cycles.film_transparent_glass = True
            log('cycles.film_transparent_glass -> True')
    except (AttributeError, TypeError) as exc:
        log('!! skipped cycles.film_transparent_glass: ' + str(exc))

    # cycles.glossy_bounces
    try:
        if scene.cycles.glossy_bounces != 32:
            scene.cycles.glossy_bounces = 32
            log('cycles.glossy_bounces -> 32')
    except (AttributeError, TypeError) as exc:
        log('!! skipped cycles.glossy_bounces: ' + str(exc))

    # cycles.max_bounces
    try:
        if scene.cycles.max_bounces != 32:
            scene.cycles.max_bounces = 32
            log('cycles.max_bounces -> 32')
    except (AttributeError, TypeError) as exc:
        log('!! skipped cycles.max_bounces: ' + str(exc))

    # cycles.preview_denoiser
    try:
        if scene.cycles.preview_denoiser != 'OPENIMAGEDENOISE':
            scene.cycles.preview_denoiser = 'OPENIMAGEDENOISE'
            log('cycles.preview_denoiser -> OPENIMAGEDENOISE')
    except (AttributeError, TypeError) as exc:
        log('!! skipped cycles.preview_denoiser: ' + str(exc))

    # cycles.samples
    try:
        if scene.cycles.samples != 512:
            scene.cycles.samples = 512
            log('cycles.samples -> 512')
    except (AttributeError, TypeError) as exc:
        log('!! skipped cycles.samples: ' + str(exc))

    # cycles.transmission_bounces
    try:
        if scene.cycles.transmission_bounces != 32:
            scene.cycles.transmission_bounces = 32
            log('cycles.transmission_bounces -> 32')
    except (AttributeError, TypeError) as exc:
        log('!! skipped cycles.transmission_bounces: ' + str(exc))

    # cycles.transparent_max_bounces
    try:
        if scene.cycles.transparent_max_bounces != 32:
            scene.cycles.transparent_max_bounces = 32
            log('cycles.transparent_max_bounces -> 32')
    except (AttributeError, TypeError) as exc:
        log('!! skipped cycles.transparent_max_bounces: ' + str(exc))

    # cycles.use_adaptive_sampling
    try:
        if scene.cycles.use_adaptive_sampling != True:
            scene.cycles.use_adaptive_sampling = True
            log('cycles.use_adaptive_sampling -> True')
    except (AttributeError, TypeError) as exc:
        log('!! skipped cycles.use_adaptive_sampling: ' + str(exc))

    # cycles.use_denoising
    try:
        if scene.cycles.use_denoising != True:
            scene.cycles.use_denoising = True
            log('cycles.use_denoising -> True')
    except (AttributeError, TypeError) as exc:
        log('!! skipped cycles.use_denoising: ' + str(exc))

    # cycles.use_light_tree
    try:
        if scene.cycles.use_light_tree != True:
            scene.cycles.use_light_tree = True
            log('cycles.use_light_tree -> True')
    except (AttributeError, TypeError) as exc:
        log('!! skipped cycles.use_light_tree: ' + str(exc))

    # cycles.use_preview_denoising
    try:
        if scene.cycles.use_preview_denoising != True:
            scene.cycles.use_preview_denoising = True
            log('cycles.use_preview_denoising -> True')
    except (AttributeError, TypeError) as exc:
        log('!! skipped cycles.use_preview_denoising: ' + str(exc))

    # cycles.volume_bounces
    try:
        if scene.cycles.volume_bounces != 32:
            scene.cycles.volume_bounces = 32
            log('cycles.volume_bounces -> 32')
    except (AttributeError, TypeError) as exc:
        log('!! skipped cycles.volume_bounces: ' + str(exc))

    # render.compositor_device
    try:
        if scene.render.compositor_device != 'GPU':
            scene.render.compositor_device = 'GPU'
            log('render.compositor_device -> GPU')
    except (AttributeError, TypeError) as exc:
        log('!! skipped render.compositor_device: ' + str(exc))

    # render.filepath
    try:
        if scene.render.filepath != '//':
            scene.render.filepath = '//'
            log('render.filepath -> //')
    except (AttributeError, TypeError) as exc:
        log('!! skipped render.filepath: ' + str(exc))

    # render.film_transparent
    try:
        if scene.render.film_transparent != True:
            scene.render.film_transparent = True
            log('render.film_transparent -> True')
    except (AttributeError, TypeError) as exc:
        log('!! skipped render.film_transparent: ' + str(exc))

    # render.use_persistent_data
    try:
        if scene.render.use_persistent_data != True:
            scene.render.use_persistent_data = True
            log('render.use_persistent_data -> True')
    except (AttributeError, TypeError) as exc:
        log('!! skipped render.use_persistent_data: ' + str(exc))

    # unit_settings.length_unit
    try:
        if scene.unit_settings.length_unit != 'CENTIMETERS':
            scene.unit_settings.length_unit = 'CENTIMETERS'
            log('unit_settings.length_unit -> CENTIMETERS')
    except (AttributeError, TypeError) as exc:
        log('!! skipped unit_settings.length_unit: ' + str(exc))

    print("\n-- 9. Compositor nodes")
    # compositor node: Film Grain (CompositorNodeGroup)
    tree = compositor_tree(scene)
    if tree is None:
        log('!! no compositor node tree in this scene')
    else:
        node = tree.nodes.get('Film Grain')
        if node is None:
            node = tree.nodes.new('CompositorNodeGroup')
            node.name = 'Film Grain'
            log('compositor node Film Grain created')
        group = find_node_group('Film Grain')
        if group is None:
            log("!! node group 'Film Grain' not found -- add it by hand from Add > Group, then rerun")
        elif node.node_tree is not group:
            node.node_tree = group
            log('Film Grain uses node group Film Grain')
        node.mute = False
        node.location = (475.00208, 105.41433)
        for _id, _value in (('Socket_10', True), ('Socket_46', '16 mm'), ('Socket_47', 'Studio Broadcast'), ('Socket_52', 0.5), ('Socket_53', 0.5), ('Socket_54', 0.5), ('Socket_55', 0.5), ('Socket_56', 400), ('Socket_64', '70 mm Cinema'), ('Socket_65', 0.5), ('Socket_7', 0.8), ('Socket_70', 0.5), ('Socket_73', 0.5)):
            set_socket(node, _id, _value)

    # compositor node Group: location
    tree = compositor_tree(scene)
    node = tree.nodes.get('Group') if tree else None
    if node is not None and any(abs(a - b) > max(1e-6, abs(b) * 1e-6) for a, b in zip(node.location, (70.35431, 105.4958))):
        node.location = (70.35431, 105.4958)
        log('compositor Group.location -> [70.35431, 105.4958]')

    # compositor node Group Output: location
    tree = compositor_tree(scene)
    node = tree.nodes.get('Group Output') if tree else None
    if node is not None and any(abs(a - b) > max(1e-6, abs(b) * 1e-6) for a, b in zip(node.location, (841.95679, 151.70752))):
        node.location = (841.95679, 151.70752)
        log('compositor Group Output.location -> [841.95679, 151.70752]')

    # compositor node removed: Image
    tree = compositor_tree(scene)
    node = tree.nodes.get('Image') if tree else None
    if node is not None:
        tree.nodes.remove(node)
        log('compositor node Image removed -- not in the reworked scene')

    # compositor node Viewer: location
    tree = compositor_tree(scene)
    node = tree.nodes.get('Viewer') if tree else None
    if node is not None and any(abs(a - b) > max(1e-6, abs(b) * 1e-6) for a, b in zip(node.location, (842.70465, 40.07054))):
        node.location = (842.70465, 40.07054)
        log('compositor Viewer.location -> [842.70465, 40.07054]')

    print("\n-- 10. Compositor links")
    # compositor links (4)
    tree = compositor_tree(scene)
    if tree is None:
        log('!! no compositor node tree to wire up')
    else:
        made = relink(tree, ((('Render Layers', 'Image'), ('Group', 'Input_1')), (('Film Grain', 'Socket_0'), ('Group Output', 'Socket_1')), (('Group', 'Output_3'), ('Film Grain', 'Socket_1')), (('Film Grain', 'Socket_0'), ('Viewer', 'Image'))))
        if made is not None:
            log('compositor rewired: 4 link(s)')

    print("\n-- 11. Lookdev tool")
    install_tool()

    print("\n-- 12. Workspace")
    install_workspace()

    remove_self()


    print("\n" + "=" * 74)
    print("%s change(s) applied" % len(_changes))
    print("=" * 74)
    print("\nSave under a NEW name to keep your original download intact.")
    return _changes


if __name__ == "__main__":
    migrate()


# ========================================================================
# NOT HANDLED -- decide these by hand
# ========================================================================
#   skipped on purpose (project specific): scenes.Scene.cycles.denoising_use_gpu
#   added    scenes.Scene.view_layers.View Layer.children.FRAME
#   added    scenes.Scene.view_layers.View Layer.children.MODEL
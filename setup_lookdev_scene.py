# ============================================================================
#  GENERATED MIGRATION -- produced by make_migration.py
# ============================================================================
#  LOOKDEV_STUDIO_ORIGINAL.blend  ->  LOOKDEV_STUDIO_COPY.blend
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



# ============================================================================
#  EMBEDDED TOOL -- lookdev_switcher.py
# ============================================================================
#  Installed into the .blend as a text block with "Register" enabled, so it
#  comes back every time the file is opened. For that to work, the user needs
#  Edit > Preferences > Save & Load > Auto Run Python Scripts enabled -- once.
# ============================================================================

TOOL_NAME = 'lookdev_switcher.py'

TOOL_SOURCE = r'''# ============================================================================
#  LOOKDEV SWITCHER  v1.0
# ============================================================================
#  by Prof. Michael Klein
#     professor@virtualrepublic.org
#     2026/07/09
#
#  Copyright (C) 2026  Michael Klein
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
    "version": (1, 0, 0),
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

# All collections that switch each other off
ALL_COLLECTIONS = COLLECTIONS + [FRAME_COLLECTION]
# All cameras driven by the DOF / F-Stop settings
ALL_CAMERAS = [c[1] for c in CONFIGS] + [FRAME_CAMERA]

# --- Align & Link Model button ------------------------------------------------
MODEL_COLLECTION = "MODEL"            # collection holding the imported models
EMPTY_NAME       = "LINKED_ROTATION"  # name of the created empty
ROTATION_TARGET  = "ROTATION_LINK"    # target object for the Child Of constraint
GEO_TYPES = {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}


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
    """Return all world-space bounding box corners of the given geo objects.

    With a depsgraph the evaluated objects are used, so animation, constraints
    and modifiers are taken into account at the current frame.
    """
    coords = []
    for obj in objects:
        if obj.type not in GEO_TYPES:
            continue
        src = obj.evaluated_get(depsgraph) if depsgraph else obj
        for corner in src.bound_box:
            coords.append(src.matrix_world @ mathutils.Vector(corner))
    return coords


def visible_geo_objects(objects):
    """Return only the geo objects that are actually visible in the view layer.

    visible_get() covers the eye icon, the monitor icon, local hide (H) and
    excluded collections in one go.
    """
    return [o for o in objects if o.type in GEO_TYPES and o.visible_get()]


def compute_bbox_center_floor(objects):
    """Return (X center, Y center, Z floor) of the world bounding box of all geo objects."""
    coords = collect_bbox_corners(objects)
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


def fit_camera_to_points(cam_obj, points, scene):
    """Keep the camera rotation, move it so all points are centered and fill the frame.

    The limiting axis decides the distance, so the models are framed either to
    width or to height depending on the bounding box aspect ratio.
    """
    rot = cam_obj.matrix_world.to_3x3().normalized()
    rot_inv = rot.inverted()
    local = [rot_inv @ p for p in points]     # points in camera axes

    xs = [v.x for v in local]
    ys = [v.y for v in local]
    cx = (min(xs) + max(xs)) / 2.0            # centered horizontally
    cy = (min(ys) + max(ys)) / 2.0            # centered vertically

    tan_x, tan_y = camera_sensor_tangents(cam_obj.data, scene)

    # The camera looks along its local -Z. For every corner the camera must be at
    # least this far back so the corner still fits; the maximum wins.
    cam_z = max(v.z + max(abs(v.x - cx) / tan_x, abs(v.y - cy) / tan_y) for v in local)

    mw = cam_obj.matrix_world.copy()
    mw.translation = rot @ mathutils.Vector((cx, cy, cam_z))
    cam_obj.matrix_world = mw


def get_framing_objects(context, model_coll):
    """Pick the objects to frame and describe where they came from.

    Priority:
    1. selected geo objects that live inside MODEL  (most specific)
    2. any selected geo objects
    3. everything in MODEL                          (nothing selected)
    """
    selected = [o for o in context.selected_objects if o.type in GEO_TYPES]
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

        # Fit with a deterministic camera orientation (first check frame)
        scene.frame_set(FRAME_CHECK_FRAMES[0])
        fit_camera_to_points(cam_obj, corners, scene)
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
        center = compute_bbox_center_floor(visible_geo_objects(model_coll.all_objects))
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


class VIEW3D_PT_lookdev_switcher(bpy.types.Panel):
    bl_label = "Lookdev Switcher"
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
        layout.operator("scene.link_model", text="Align & Link Model",
                        icon=collection_icon(MODEL_COLLECTION))   # neutral, matching MODEL


classes = (SCENE_OT_set_config, SCENE_OT_frame_model, SCENE_OT_link_model,
           VIEW3D_PT_lookdev_switcher)


def register():
    for cls in classes:
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

    apply_color_tags()      # set outliner colors once on load
    # Apply the SAVED panel values to the cameras (do not force fixed defaults,
    # otherwise a reload would reset the f-stop you set earlier).
    scene = getattr(bpy.context, "scene", None)
    if scene is None and bpy.data.scenes:
        scene = bpy.data.scenes[0]
    if scene is not None:
        apply_dof_settings(scene)


def unregister():
    del bpy.types.Scene.lookdev_dof_depth
    del bpy.types.Scene.lookdev_fstop
    del bpy.types.Scene.lookdev_dof
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


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
            log("'%s' is now open in the text editor" % text.name)
    except Exception as exc:
        print("  ! could not show '%s' in the editor: %s" % (text.name, exc))


def install_tool():
    """Put the tool into this .blend and register it right away."""
    text = bpy.data.texts.get(TOOL_NAME)
    if text is None:
        text = bpy.data.texts.new(TOOL_NAME)
        log("text block '%s' created" % TOOL_NAME)
    text.clear()
    text.write(TOOL_SOURCE)

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
        log("tool registered -- see the N-panel in the 3D viewport")
    except Exception as exc:
        print("  ! could not register '%s' now: %s" % (TOOL_NAME, exc))
        print("    It will load by itself when the file is reopened with "
              "Auto Run Python Scripts enabled.")

    # Do this last: the editor must end up on the tool, not on the empty slot
    # left behind when this script removes itself.
    show_in_editor(text)



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

    # cycles.adaptive_min_samples
    try:
        if scene.cycles.adaptive_min_samples != 0:
            scene.cycles.adaptive_min_samples = 0
            log('cycles.adaptive_min_samples -> 0')
    except (AttributeError, TypeError) as exc:
        log('!! skipped cycles.adaptive_min_samples: ' + str(exc))

    # cycles.adaptive_threshold
    try:
        if scene.cycles.adaptive_threshold != 0.01:
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

    # render.image_settings.file_format
    try:
        if scene.render.image_settings.file_format != 'OPEN_EXR_MULTILAYER':
            scene.render.image_settings.file_format = 'OPEN_EXR_MULTILAYER'
            log('render.image_settings.file_format -> OPEN_EXR_MULTILAYER')
    except (AttributeError, TypeError) as exc:
        log('!! skipped render.image_settings.file_format: ' + str(exc))

    # render.image_settings.linear_colorspace_settings.name
    try:
        if scene.render.image_settings.linear_colorspace_settings.name != 'ACEScg':
            scene.render.image_settings.linear_colorspace_settings.name = 'ACEScg'
            log('render.image_settings.linear_colorspace_settings.name -> ACEScg')
    except (AttributeError, TypeError) as exc:
        log('!! skipped render.image_settings.linear_colorspace_settings.name: ' + str(exc))

    # render.image_settings.media_type
    try:
        if scene.render.image_settings.media_type != 'MULTI_LAYER_IMAGE':
            scene.render.image_settings.media_type = 'MULTI_LAYER_IMAGE'
            log('render.image_settings.media_type -> MULTI_LAYER_IMAGE')
    except (AttributeError, TypeError) as exc:
        log('!! skipped render.image_settings.media_type: ' + str(exc))

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
    if node is not None and tuple(node.location) != (70.35431, 105.4958):
        node.location = (70.35431, 105.4958)
        log('compositor Group.location -> [70.35431, 105.4958]')

    # compositor node Group Output: location
    tree = compositor_tree(scene)
    node = tree.nodes.get('Group Output') if tree else None
    if node is not None and tuple(node.location) != (841.95679, 151.70752):
        node.location = (841.95679, 151.70752)
        log('compositor Group Output.location -> [841.95679, 151.70752]')

    # compositor node Viewer: location
    tree = compositor_tree(scene)
    node = tree.nodes.get('Viewer') if tree else None
    if node is not None and tuple(node.location) != (842.70465, 40.07054):
        node.location = (842.70465, 40.07054)
        log('compositor Viewer.location -> [842.70465, 40.07054]')

    print("\n-- 10. Compositor links")
    # compositor links (4)
    tree = compositor_tree(scene)
    if tree is None:
        log('!! no compositor node tree to wire up')
    else:
        made = relink(tree, ((('Render Layers', 'Image'), ('Group', 'Input_1')), (('Film Grain', 'Socket_0'), ('Group Output', 'Socket_1')), (('Group', 'Output_3'), ('Film Grain', 'Socket_1')), (('Film Grain', 'Socket_0'), ('Viewer', 'Image'))))
        log('compositor rewired: 4 link(s)')

    print("\n-- 9. Lookdev tool")
    install_tool()

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
#   changed  actions
#            old: ["EmptyAction.001", "Shader NodetreeAction"]
#            new: ["EmptyAction.001", "Shader NodetreeAction", "SolidAction.001", "SolidAction.006", "SolidA
#   changed  images
#            old: ["HDRI_4K.exr", "LOOKDEV_STUDIO_1001_BaseColor.png", "LOOKDEV_STUDIO_1001_Metallic.png", "
#            new: ["HDRI_4K.exr", "LOOKDEV_STUDIO_1001_BaseColor.png", "LOOKDEV_STUDIO_1001_Metallic.png", "
#   added    materials.mb:nodes
#   skipped on purpose (project specific): scenes.Scene.cycles.denoising_use_gpu
#   added    scenes.Scene.view_layers.View Layer.children.FRAME
#   added    scenes.Scene.view_layers.View Layer.children.MODEL
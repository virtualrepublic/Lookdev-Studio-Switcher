# ============================================================================
#  LOOKDEV SWITCHER  v1.1
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
    "version": (1, 1, 0),
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

# --- Align & Link Model button ------------------------------------------------
MODEL_COLLECTION = "MODEL"            # collection holding the imported models
EMPTY_NAME       = "LINKED_ROTATION"  # name of the created empty
ROTATION_TARGET  = "ROTATION_LINK"    # target object for the Child Of constraint
GEO_TYPES = {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}

# --- Auto-collect imported objects into MODEL --------------------------------
# A lightweight timer watches for objects that appear (an import, or Add) and
# moves them into MODEL so a freshly imported model lands on the turntable
# without a manual drag. Only geometry and empties are moved; cameras, lights
# and the tool's own rotation empty are left where they are.
AUTO_MODEL_POLL   = 0.5               # seconds between checks for new objects
_seen_object_names = set()            # object names known at the previous check


def _current_object_names():
    return {o.name for o in bpy.data.objects}


def auto_collect_into_model():
    """Relink objects that appeared since the last check into MODEL.

    Returns the list of names that were moved. Objects already in MODEL, and
    non-geometry (cameras, lights) are ignored, as is the rotation empty.
    """
    global _seen_object_names
    model_coll = bpy.data.collections.get(MODEL_COLLECTION)
    current = _current_object_names()
    new_names = current - _seen_object_names
    moved = []
    if model_coll is not None and new_names:
        model_objs = set(model_coll.all_objects)
        for name in sorted(new_names):
            obj = bpy.data.objects.get(name)
            if obj is None or obj.name == EMPTY_NAME:
                continue
            if obj.type not in GEO_TYPES and obj.type != 'EMPTY':
                continue
            if obj in model_objs:
                continue
            for coll in list(obj.users_collection):
                coll.objects.unlink(obj)
            model_coll.objects.link(obj)
            moved.append(name)
    _seen_object_names = current
    return moved


def _auto_model_timer():
    """Timer callback: collect new objects when the panel toggle is on.

    Restricted to OBJECT mode so nothing is relinked mid edit. When the toggle
    is off the baseline is still refreshed, so switching it on later only
    affects objects imported from that point on, not everything already there.
    """
    global _seen_object_names
    scene = getattr(bpy.context, "scene", None)
    on = bool(getattr(scene, "lookdev_auto_model", False)) if scene else False
    if on and getattr(bpy.context, "mode", 'OBJECT') == 'OBJECT':
        auto_collect_into_model()
    else:
        _seen_object_names = _current_object_names()
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

        # Fit with a deterministic camera orientation (first check frame),
        # leaving a safe-action margin so the silhouette does not touch the edge.
        scene.frame_set(FRAME_CHECK_FRAMES[0])
        fit_camera_to_points(cam_obj, corners, scene, FRAME_FILL)
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
        layout.prop(context.scene, "lookdev_auto_model", toggle=True,
                    icon='IMPORT')   # auto-move imports into MODEL
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
    bpy.types.Scene.lookdev_auto_model = bpy.props.BoolProperty(
        name="Auto-collect to MODEL",
        description=("Automatically move newly imported or added geometry into "
                     "'%s' so it lands on the turntable" % MODEL_COLLECTION),
        default=True,
    )

    # Start watching for new objects (imports) to pull into MODEL.
    global _seen_object_names
    _seen_object_names = _current_object_names()
    if not bpy.app.timers.is_registered(_auto_model_timer):
        bpy.app.timers.register(_auto_model_timer, first_interval=AUTO_MODEL_POLL)

    apply_color_tags()      # set outliner colors once on load
    # Apply the SAVED panel values to the cameras (do not force fixed defaults,
    # otherwise a reload would reset the f-stop you set earlier).
    scene = getattr(bpy.context, "scene", None)
    if scene is None and bpy.data.scenes:
        scene = bpy.data.scenes[0]
    if scene is not None:
        apply_dof_settings(scene)


def unregister():
    if bpy.app.timers.is_registered(_auto_model_timer):
        bpy.app.timers.unregister(_auto_model_timer)
    del bpy.types.Scene.lookdev_auto_model
    del bpy.types.Scene.lookdev_dof_depth
    del bpy.types.Scene.lookdev_fstop
    del bpy.types.Scene.lookdev_dof
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()

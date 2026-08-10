# ============================================================================
#  EXPORT WORKSPACE  v1.0
# ============================================================================
#  by Prof. Michael Klein
#     professor@virtualrepublic.org
#
#  Copyright (C) 2026  Prof. Michael Klein
#  SPDX-License-Identifier: GPL-3.0-or-later
# ============================================================================
#  Writes ONE workspace to its own .blend, and reports what that costs if it
#  is to be embedded in the generated installer.
#
#  Blender stores the interface in the .blend, so a layout can be handed to
#  users -- but not through the diff. dump_scene.py records no interface data,
#  and the generator could not rebuild one anyway: the Python API has no way
#  to create areas, only bpy.ops.screen.area_split, which needs a real window.
#  The route that does work is to append a finished workspace from a .blend.
#
#  What travels: measured, not assumed. bpy.data.libraries.write() with a
#  single workspace pulls in its screens and nothing else -- no objects, no
#  meshes, no materials, no images, no scenes. The scene stays out of it, so
#  nothing of the original author's work is redistributed.
#
#  RUN IT FROM THE GUI, not in the background: a background Blender may hold
#  no workspaces at all, and then there is nothing to export. Open the .blend
#  that has the layout, go to Scripting, open this file, Run Script.
#  Settings are the two constants below; command-line use is supported too:
#
#     blender --background file.blend --python tools\export_workspace.py -- \
#             --workspace Lookdev -o _local\workspace_lookdev.blend
# ============================================================================

import bpy
import os
import sys
import zlib
import base64

# --- edit these two when running from the Text editor ------------------------
WORKSPACE = "Lookdev"          # name of the workspace to export
OUTPUT    = ""                 # empty = _local\workspace_<name>.blend
# -----------------------------------------------------------------------------

BAR = "=" * 74


def parse_args():
    global WORKSPACE, OUTPUT
    if "--" not in sys.argv:
        return
    argv = sys.argv[sys.argv.index("--") + 1:]
    import argparse
    parser = argparse.ArgumentParser(prog="export_workspace.py")
    parser.add_argument("--workspace", default=WORKSPACE)
    parser.add_argument("-o", "--out", default=OUTPUT)
    args = parser.parse_args(argv)
    WORKSPACE, OUTPUT = args.workspace, args.out


def local_folder():
    """_local\\ is the folder holding run.ps1; walk up from the open .blend."""
    folder = os.path.dirname(bpy.data.filepath) or os.getcwd()
    for _ in range(4):
        if os.path.isfile(os.path.join(folder, "run.ps1")):
            return folder
        parent = os.path.dirname(folder)
        if parent == folder:
            break
        folder = parent
    return os.path.dirname(bpy.data.filepath) or os.getcwd()


def main():
    parse_args()

    print("\n" + BAR)
    print("  EXPORT WORKSPACE")
    print(BAR)
    print("  background mode : %s" % bpy.app.background)
    print("  workspaces here : %d" % len(bpy.data.workspaces))

    if not bpy.data.workspaces:
        print("\n  Nothing to export -- this session holds no workspaces.")
        print("  Run it from the GUI, not with --background.")
        print(BAR + "\n")
        return

    ws = bpy.data.workspaces.get(WORKSPACE)
    if ws is None:
        print("\n  No workspace named '%s'. Available:" % WORKSPACE)
        for other in bpy.data.workspaces:
            print("      %s" % other.name)
        print("\n  Set WORKSPACE at the top of this file, or pass --workspace.")
        print("\n  Give the workspace its OWN name (e.g. 'Lookdev') rather than")
        print("  reusing 'Layout'. Appending a name the user already has makes")
        print("  Blender suffix it to 'Layout.001'. A separate tab is also the")
        print("  honest form: it adds a workspace instead of replacing theirs,")
        print("  and they can rebuild or delete it as they like.")
        print(BAR + "\n")
        return

    out = OUTPUT or os.path.join(local_folder(),
                                 "workspace_%s.blend" % WORKSPACE.lower().replace(" ", "_"))
    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)

    print("\n  workspace '%s'  --  %d screen(s)" % (ws.name, len(ws.screens)))
    for screen in ws.screens:
        print("      screen '%s': %s" % (
            screen.name, ", ".join(a.type for a in screen.areas)))

    bpy.data.libraries.write(out, {ws}, fake_user=True)

    # Prove that nothing but interface data went in. If anything shows up under
    # objects/meshes/materials/images/scenes, do NOT ship this file.
    print("\n  contents of the written file:")
    clean = True
    with bpy.data.libraries.load(out) as (src, _dst):
        for kind in ("workspaces", "screens", "objects", "meshes", "materials",
                     "images", "scenes", "worlds", "node_groups", "cameras",
                     "texts", "actions"):
            names = list(getattr(src, kind, []))
            if not names:
                continue
            print("      %-12s %2d  %s" % (kind, len(names), ", ".join(names[:5])))
            if kind not in ("workspaces", "screens"):
                clean = False

    raw = open(out, "rb").read()
    packed = base64.b64encode(zlib.compress(raw, 9))

    print("\n  %-28s %8.0f KB" % ("written", len(raw) / 1024.0))
    print("  %-28s %8.0f KB   <- this is what an embedded copy costs" % (
        "zlib + base64", len(packed) / 1024.0))
    installer = os.path.join(os.path.dirname(local_folder()), "setup_lookdev_scene.py")
    if os.path.isfile(installer):
        now = os.path.getsize(installer) / 1024.0
        print("  %-28s %8.0f KB  ->  %.0f KB" % (
            "setup_lookdev_scene.py", now, now + len(packed) / 1024.0))

    print("\n  " + ("interface data only -- safe to ship." if clean else
                   "!! SCENE DATA CAME ALONG -- do not ship this file."))
    print("  %s" % out)
    print(BAR + "\n")


main()

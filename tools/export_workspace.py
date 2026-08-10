# ============================================================================
#  EXPORT WORKSPACE  v1.1
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
#  meshes, no materials, no images, no scenes. Nothing of the original
#  author's work is redistributed.
#
#  HOW TO RUN -- from the GUI, not with --background. A background Blender may
#  hold no workspaces at all, and then there is nothing to export.
#
#    1. Open the .blend whose interface you want to ship.
#    2. Make sure a workspace TAB named exactly "Lookdev" exists. The quickest
#       way: right-click the tab you like -> Duplicate, then double-click the
#       copy and rename it to Lookdev. Shipping it under its own name matters:
#       appending a "Layout" onto a user who already has one makes Blender
#       call it "Layout.001".
#    3. Scripting workspace -> Open -> this file -> Run Script.
#
#  Everything printed also goes to a log file, so nothing is lost in the
#  hidden system console. The log tells you where it landed.
# ============================================================================

import bpy
import os
import sys
import zlib
import base64
import tempfile

# --- edit these when running from the Text editor -----------------------------
WORKSPACE = "Lookdev"          # name of the workspace tab to export
OUTPUT    = ""                 # empty = _local\workspace_<name>.blend
# ------------------------------------------------------------------------------

BAR = "=" * 74
_lines = []


def out(text=""):
    print(text)
    _lines.append(text)


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
    """_local\\ is the folder holding run.ps1; walk up from the open .blend.

    Returns (folder, how_it_was_found) so the log can say why it chose that
    place -- a file written somewhere unexpected is the same as no file.
    """
    blend = bpy.data.filepath
    if not blend:
        return tempfile.gettempdir(), "the .blend is unsaved, so the temp folder"
    folder = os.path.dirname(blend)
    for _ in range(5):
        if os.path.isfile(os.path.join(folder, "run.ps1")):
            return folder, "found by the run.ps1 marker"
        parent = os.path.dirname(folder)
        if parent == folder:
            break
        folder = parent
    return (os.path.dirname(blend),
            "no run.ps1 above the .blend -- falling back to its own folder")


def write_log():
    """Log next to the .blend and, when they differ, in _local\\ as well."""
    written = []
    targets = []
    folder, _why = local_folder()
    targets.append(os.path.join(folder, "export_workspace.log.txt"))
    blend_dir = os.path.dirname(bpy.data.filepath)
    if blend_dir and blend_dir != folder:
        targets.append(os.path.join(blend_dir, "export_workspace.log.txt"))
    for path in targets:
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("\n".join(_lines) + "\n")
            written.append(path)
        except Exception:
            pass
    for path in written:
        print("  log written: %s" % path)
    if not written:
        print("  (could not write a log file anywhere)")


def main():
    parse_args()

    out("\n" + BAR)
    out("  EXPORT WORKSPACE")
    out(BAR)
    out("  background mode : %s" % bpy.app.background)
    out("  open file       : %s" % (bpy.data.filepath or "<unsaved>"))
    out("  workspaces here : %d" % len(bpy.data.workspaces))
    out("  looking for     : '%s'" % WORKSPACE)

    folder, why = local_folder()
    target = OUTPUT or os.path.join(
        folder, "workspace_%s.blend" % WORKSPACE.lower().replace(" ", "_"))
    target = os.path.abspath(target)
    out("  would write to  : %s" % target)
    out("                    (%s)" % why)

    if not bpy.data.workspaces:
        out("\n  NOTHING TO EXPORT -- this session holds no workspaces.")
        out("  Run it from the GUI, not with --background.")
        out(BAR)
        return

    ws = bpy.data.workspaces.get(WORKSPACE)
    if ws is None:
        out("\n  NOTHING WRITTEN -- there is no workspace tab named '%s'." % WORKSPACE)
        out("\n  This file has:")
        for other in bpy.data.workspaces:
            out("      %s" % other.name)
        out("\n  Create it: right-click the tab you want to ship -> Duplicate,")
        out("  then double-click the copy and rename it to '%s'." % WORKSPACE)
        out("  Shipping it under its own name matters -- appending a 'Layout'")
        out("  onto a user who already has one makes Blender call it 'Layout.001'.")
        out("\n  Or export a different tab: set WORKSPACE at the top of this file.")
        out(BAR)
        return

    out("\n  workspace '%s'  --  %d screen(s)" % (ws.name, len(ws.screens)))
    for screen in ws.screens:
        out("      screen '%s': %s" % (
            screen.name, ", ".join(a.type for a in screen.areas)))

    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        bpy.data.libraries.write(target, {ws}, fake_user=True)
    except Exception as exc:
        out("\n  FAILED to write %s" % target)
        out("      %s" % exc)
        out(BAR)
        return

    # Prove that nothing but interface data went in. Anything under objects,
    # meshes, materials, images or scenes means the file must NOT be shipped.
    out("\n  contents of the written file:")
    clean = True
    with bpy.data.libraries.load(target) as (src, _dst):
        for kind in ("workspaces", "screens", "objects", "meshes", "materials",
                     "images", "scenes", "worlds", "node_groups", "cameras",
                     "texts", "actions"):
            names = list(getattr(src, kind, []))
            if not names:
                continue
            out("      %-12s %2d  %s" % (kind, len(names), ", ".join(names[:5])))
            if kind not in ("workspaces", "screens"):
                clean = False

    raw = open(target, "rb").read()
    packed = base64.b64encode(zlib.compress(raw, 9))
    out("\n  %-30s %8.0f KB" % ("written", len(raw) / 1024.0))
    out("  %-30s %8.0f KB   <- cost of embedding it" % (
        "zlib + base64", len(packed) / 1024.0))

    installer = os.path.join(os.path.dirname(folder), "setup_lookdev_scene.py")
    if os.path.isfile(installer):
        now = os.path.getsize(installer) / 1024.0
        out("  %-30s %8.0f KB  ->  %.0f KB" % (
            "setup_lookdev_scene.py", now, now + len(packed) / 1024.0))

    out("")
    if clean:
        out("  INTERFACE DATA ONLY -- safe to ship.")
        out("  Next: RUN.cmd -> 4. It picks the file up automatically.")
    else:
        out("  !! SCENE DATA CAME ALONG -- do not ship this file.")
    out("  %s" % target)
    out(BAR + "\n")


try:
    main()
finally:
    write_log()

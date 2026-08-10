# ============================================================================
#  EXPORT WORKSPACE  v2.0
# ============================================================================
#  by Prof. Michael Klein
#     professor@virtualrepublic.org
#
#  Copyright (C) 2026  Prof. Michael Klein
#  SPDX-License-Identifier: GPL-3.0-or-later
# ============================================================================
#  Writes the interface state of this .blend -- its workspaces -- to a .blend
#  of its own, for the generator to embed. Nothing has to be renamed or set up
#  first: what is exported is what you see.
#
#  Blender keeps the interface in the .blend, so a layout can be handed to
#  users -- but not through the diff. dump_scene.py records no interface data,
#  and the generator could not rebuild one anyway: the Python API has no way
#  to create areas, only bpy.ops.screen.area_split, which needs a real window.
#  The route that does work is to append finished workspaces from a .blend.
#
#  At the user's end the installer REPLACES a workspace of the same name
#  rather than adding a duplicate -- Blender would otherwise call the appended
#  one "Layout.001". So the converted file ends up with your interface.
#
#  What travels: measured, not assumed. bpy.data.libraries.write() with
#  workspaces pulls in their screens and nothing else -- no objects, meshes,
#  materials, images or scenes. Nothing of the original author's work is
#  redistributed. The report below lists exactly what went into the file, and
#  says plainly when something other than interface data appears.
#
#  HOW TO RUN -- from the GUI, not with --background. A background Blender
#  holds no workspaces, so there would be nothing to export.
#
#    1. Open the .blend whose interface you want to ship, arranged the way you
#       want your users to receive it.
#    2. Scripting workspace -> Open -> this file -> Run Script.
#
#  Everything printed also goes to export_workspace.log.txt, so nothing is
#  lost in the hidden system console.
# ============================================================================

import bpy
import os
import sys
import zlib
import base64
import hashlib
import tempfile

# --- edit these when running from the Text editor -----------------------------
# Empty list = every workspace in the file. Name them to ship only some, e.g.
#     WORKSPACES = ["Layout", "Shading"]
# Fewer workspaces means a smaller blob in the installer; the report shows what
# each one costs.
WORKSPACES = []
OUTPUT     = ""                # empty = _local\workspace_ui.blend
# ------------------------------------------------------------------------------

BAR = "=" * 74
_lines = []


def out(text=""):
    print(text)
    _lines.append(text)


def parse_args():
    global WORKSPACES, OUTPUT
    if "--" not in sys.argv:
        return
    argv = sys.argv[sys.argv.index("--") + 1:]
    import argparse
    parser = argparse.ArgumentParser(prog="export_workspace.py")
    parser.add_argument("--workspace", action="append", default=None,
                        help="repeatable; default is every workspace")
    parser.add_argument("-o", "--out", default=OUTPUT)
    args = parser.parse_args(argv)
    WORKSPACES = args.workspace or []
    OUTPUT = args.out


def local_folder():
    """_local\\ is the folder holding RUN.cmd; walk up from the open .blend.

    RUN.cmd, not run.ps1: run.ps1 moved to tools\\ so it would be versioned, and
    this marker silently stopped matching. The export then landed next to the
    scene, the generator kept using the previous one, and the stamp guard
    compared two old files and called it fine.

    Returns (folder, why) so the log can say how it chose -- a file written
    somewhere unexpected is as good as no file at all.
    """
    blend = bpy.data.filepath
    if not blend:
        return tempfile.gettempdir(), "the .blend is unsaved, so the temp folder"
    folder = os.path.dirname(blend)
    for _ in range(5):
        if os.path.isfile(os.path.join(folder, "RUN.cmd")):
            return folder, "found by the RUN.cmd marker"
        parent = os.path.dirname(folder)
        if parent == folder:
            break
        folder = parent
    return (os.path.dirname(blend),
            "!! no RUN.cmd above the .blend -- falling back to its own folder, "
            "so RUN.cmd -> 4 will NOT find this file")


def write_log():
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
    out("  EXPORT WORKSPACE -- the interface state of this file")
    out(BAR)
    out("  background mode : %s" % bpy.app.background)
    out("  open file       : %s" % (bpy.data.filepath or "<unsaved>"))
    out("  workspaces here : %d" % len(bpy.data.workspaces))

    folder, why = local_folder()
    target = os.path.abspath(OUTPUT or os.path.join(folder, "workspace_ui.blend"))
    out("  would write to  : %s" % target)
    out("                    (%s)" % why)

    if not bpy.data.workspaces:
        out("\n  NOTHING TO EXPORT -- this session holds no workspaces.")
        out("  Run it from the GUI, not with --background.")
        out(BAR)
        return

    if WORKSPACES:
        chosen, missing = [], []
        for name in WORKSPACES:
            ws = bpy.data.workspaces.get(name)
            (chosen if ws is not None else missing).append(ws if ws else name)
        if missing:
            out("\n  NOTHING WRITTEN -- no workspace named: %s" % ", ".join(missing))
            out("\n  This file has:")
            for other in bpy.data.workspaces:
                out("      %s" % other.name)
            out("\n  Fix the WORKSPACES list at the top of this file, or leave it")
            out("  empty to export every workspace.")
            out(BAR)
            return
    else:
        chosen = list(bpy.data.workspaces)
        out("  exporting       : all of them (WORKSPACES is empty)")

    out("")
    for ws in chosen:
        areas = []
        for screen in ws.screens:
            areas.extend(a.type for a in screen.areas)
        out("      %-16s %d screen(s): %s" % (ws.name, len(ws.screens),
                                              ", ".join(areas)))

    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        bpy.data.libraries.write(target, set(chosen), fake_user=True)
    except Exception as exc:
        out("\n  FAILED to write %s" % target)
        out("      %s" % exc)
        out(BAR)
        return

    # Anything beyond workspaces/screens means scene data followed the export.
    # That would be the original author's, and must not be redistributed.
    out("\n  contents of the written file:")
    clean = True
    with bpy.data.libraries.load(target) as (src, _dst):
        for kind in ("workspaces", "screens", "objects", "meshes", "materials",
                     "images", "scenes", "worlds", "node_groups", "cameras",
                     "texts", "actions"):
            names = list(getattr(src, kind, []))
            if not names:
                continue
            shown = ", ".join(names[:6])
            more = "" if len(names) <= 6 else " ... +%d" % (len(names) - 6)
            out("      %-12s %2d  %s%s" % (kind, len(names), shown, more))
            if kind not in ("workspaces", "screens"):
                clean = False

    raw = open(target, "rb").read()
    packed = base64.b64encode(zlib.compress(raw, 9))
    stamp = hashlib.sha256(raw).hexdigest()[:16]
    out("\n  %-30s %8.0f KB" % ("written", len(raw) / 1024.0))
    out("  %-30s %8.0f KB   <- cost of embedding it" % (
        "zlib + base64", len(packed) / 1024.0))
    installer = os.path.join(os.path.dirname(folder), "setup_lookdev_scene.py")
    if os.path.isfile(installer):
        now = os.path.getsize(installer) / 1024.0
        out("  %-30s %8.0f KB  ->  %.0f KB" % (
            "setup_lookdev_scene.py", now, now + len(packed) / 1024.0))
    out("  %-30s %s" % ("stamp", stamp))

    out("")
    if clean:
        out("  INTERFACE DATA ONLY -- safe to ship.")
        out("  Next: RUN.cmd -> 4. It picks the file up automatically.")
        if len(chosen) > 3:
            out("")
            out("  Shipping %d workspaces. If the blob is heavier than you want,"
                % len(chosen))
            out("  set WORKSPACES at the top of this file to just the ones you")
            out("  actually changed and run it again.")
    else:
        out("  !! SCENE DATA CAME ALONG -- do not ship this file.")
    out("  %s" % target)
    out(BAR + "\n")


try:
    main()
finally:
    write_log()

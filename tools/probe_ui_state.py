# ============================================================================
#  PROBE UI STATE  v1.0
# ============================================================================
#  by Prof. Michael Klein
#     professor@virtualrepublic.org
#
#  Copyright (C) 2026  Prof. Michael Klein
#  SPDX-License-Identifier: GPL-3.0-or-later
# ============================================================================
#  Appending a workspace carries the STRUCTURE of the interface -- which areas
#  exist, how they are split, which editor sits in each. It does not carry
#  everything you see. This probe reports, for the file that is open, which of
#  the remaining pieces bpy actually exposes, and whether they can be written.
#
#  The question it answers: after the workspace has been transferred, what is
#  left that a script could still set, and what is out of reach entirely?
#
#  Read-only. Every write test is done on a copy of the value and put back.
#
#  Run from the GUI: Scripting -> Open -> this file -> Run Script.
#  Writes probe_ui_state.log.txt next to the open .blend.
# ============================================================================

import bpy
import os
import tempfile

BAR = "=" * 74
_lines = []


def out(text=""):
    print(text)
    _lines.append(text)


def writable(owner, attr):
    """Can this be set? Try to write the value it already has."""
    try:
        value = getattr(owner, attr)
    except Exception as exc:
        return "unreadable (%s)" % exc
    try:
        setattr(owner, attr, value)
        return "READ/WRITE  = %r" % (value,)
    except Exception:
        return "read-only   = %r" % (value,)


head_done = set()


def section(title):
    out("\n" + BAR)
    out("  " + title)
    out(BAR)


section("CONTEXT")
out("  blender    : %s" % bpy.app.version_string)
out("  file       : %s" % (bpy.data.filepath or "<unsaved>"))
out("  workspaces : %d" % len(bpy.data.workspaces))

section("PER-AREA STATE IN THE ACTIVE WORKSPACE")
window = getattr(bpy.context, "window", None)
screen = getattr(window, "screen", None) if window else None
if screen is None:
    out("  no screen in context -- run this from the GUI.")
else:
    out("  workspace '%s', screen '%s'" % (
        getattr(getattr(window, "workspace", None), "name", "?"), screen.name))
    for area in screen.areas:
        out("\n  AREA %s  %dx%d" % (area.type, area.width, area.height))
        for region in area.regions:
            if region.type not in ('UI', 'TOOLS', 'WINDOW'):
                continue
            bits = ["    region %-8s %4dx%-4d" % (region.type, region.width, region.height)]
            # The N-panel tab. If this is writable the panel a user lands on
            # can be restored after the workspace is appended.
            if hasattr(region, "active_panel_category"):
                bits.append("active_panel_category %s"
                            % writable(region, "active_panel_category"))
            else:
                bits.append("no active_panel_category on Region")
            out("  ".join(bits))
        space = area.spaces.active
        if space is None:
            continue
        interesting = [a for a in dir(space)
                       if not a.startswith("_")
                       and any(k in a for k in ("show_", "use_", "display",
                                                "filter", "sort", "context"))]
        if interesting:
            out("    space %s exposes: %s" % (type(space).__name__,
                                              ", ".join(sorted(interesting)[:14])))

section("OUTLINER -- is the expanded/collapsed state reachable?")
found_outliner = False
if screen is not None:
    for area in screen.areas:
        if area.type != 'OUTLINER':
            continue
        found_outliner = True
        space = area.spaces.active
        out("  SpaceOutliner attributes that are not private:")
        names = sorted(a for a in dir(space) if not a.startswith("_"))
        for i in range(0, len(names), 4):
            out("      " + "  ".join("%-22s" % n for n in names[i:i + 4]))
        for candidate in ("treestore", "tree", "expanded", "open", "state"):
            out("  '%s' present: %s" % (candidate, hasattr(space, candidate)))
if not found_outliner:
    out("  no OUTLINER area in this workspace -- switch to one and run again.")

section("SCENE STATE THAT IS NOT INTERFACE")
scene = getattr(bpy.context, "scene", None)
if scene is not None:
    out("  frame_current : %s" % writable(scene, "frame_current"))
    out("  (this one is scene data, not interface -- the dumper normalises")
    out("   both files to frame 0 while diffing, which is why it does not")
    out("   travel today.)")

section("DONE")
out("  Nothing was changed: every write test put the value straight back.")
out(BAR + "\n")

folder = os.path.dirname(bpy.data.filepath) or tempfile.gettempdir()
path = os.path.join(folder, "probe_ui_state.log.txt")
try:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(_lines) + "\n")
    print("  log written: %s" % path)
except Exception as exc:
    print("  could not write %s: %s" % (path, exc))

# ============================================================================
#  PROBE WORKING SPACE  v1.0
# ============================================================================
#  by Prof. Michael Klein
#     professor@virtualrepublic.org
#
#  Copyright (C) 2026  Prof. Michael Klein
#  SPDX-License-Identifier: GPL-3.0-or-later
# ============================================================================
#  The dialog is titled "Set Blend File Working Color Space" -- blend file,
#  not scene. probe_property.py searches scene, world, view_layer and
#  preferences, so it cannot see this one, and dump_scene.py records scenes,
#  so the diff cannot either.
#
#  This probe looks in the two places that are left:
#
#    bpy.data          the blend file itself (BlendData). Every scalar
#                      property, with its value and whether it can be written.
#    bpy.ops           the operator behind the dialog, found by idname and
#                      then by its properties -- the checkbox in the dialog
#                      has to be one of them.
#
#  Setting the value is not the same as what the dialog does: the dialog also
#  converts colours in all data-blocks. So the operator matters more than the
#  property, and its argument names have to be measured, not guessed.
#
#  Read-only. Writes probe_working_space.log.txt next to the open .blend.
#
#    Scripting -> Open -> this file -> Run Script
# ============================================================================

import bpy
import os
import tempfile

VALUES = ("ACEScg", "Rec.709", "Rec709", "Linear Rec.709", "Linear")
BAR = "=" * 74
_lines = []


def out(text=""):
    print(text)
    _lines.append(text)


def dump_rna(owner, label, indent="    "):
    """Every scalar property of one RNA struct, one level into its pointers."""
    try:
        props = owner.bl_rna.properties
    except Exception as exc:
        out("%s%s: unreadable (%s)" % (indent, label, exc))
        return
    for prop in props:
        name = prop.identifier
        if name == "rna_type":
            continue
        try:
            value = getattr(owner, name)
        except Exception:
            continue
        if prop.type == 'COLLECTION':
            # Collections are the data-blocks themselves -- meshes, objects,
            # materials. Not what we are after, and enormous.
            continue
        if prop.type == 'POINTER':
            if value is None:
                continue
            try:
                subs = value.bl_rna.properties
            except Exception:
                continue
            for sub in subs:
                if sub.identifier == "rna_type":
                    continue
                try:
                    sub_value = getattr(value, sub.identifier)
                except Exception:
                    continue
                if sub.type in ('POINTER', 'COLLECTION'):
                    continue
                mark = mark_for(sub_value)
                out("%s%-44s %r%s%s" % (indent, "%s.%s" % (name, sub.identifier),
                                        sub_value,
                                        "" if sub.is_readonly else "  [writable]",
                                        mark))
            continue
        mark = mark_for(value)
        out("%s%-44s %r%s%s" % (indent, name, value,
                                "" if prop.is_readonly else "  [writable]", mark))


def mark_for(value):
    if not isinstance(value, str):
        return ""
    return "  <== VALUE MATCH" if any(v.lower() in value.lower()
                                      for v in VALUES) else ""


out("\n" + BAR)
out("  PROBE WORKING SPACE -- the blend file's colour space, and its operator")
out(BAR)
out("  blender : %s" % bpy.app.version_string)
out("  file    : %s" % (bpy.data.filepath or "<unsaved>"))

# --- 1. the blend file itself -------------------------------------------------
out("\n  bpy.data -- every scalar property of the blend file:")
dump_rna(bpy.data, "bpy.data")

# --- 2. the operator behind the dialog ----------------------------------------
# The dialog has a title, a checkbox and an enum. Whatever operator draws it
# must have properties matching. Find it by idname, then read its signature.
out("\n  operators whose name suggests colour space or working space:")
found = []
for module_name in dir(bpy.ops):
    if module_name.startswith("_"):
        continue
    module = getattr(bpy.ops, module_name)
    for op_name in dir(module):
        if op_name.startswith("_"):
            continue
        low = op_name.lower()
        if ("color_space" in low or "colorspace" in low or "working" in low
                or "color_management" in low):
            found.append("%s.%s" % (module_name, op_name))
if not found:
    out("    (none found by name -- widen the search)")
for idname in found:
    out("    bpy.ops.%s" % idname)
    try:
        # get_rna_type() is the route that works. Looking the operator up in
        # bpy.types as WM_OT_name only finds operators registered from Python;
        # the ones built into Blender are not all there, and set_working_color_space
        # is one of those -- which is why the first run of this probe reported
        # "RNA not found" for the one operator that mattered.
        module_name, op_name = idname.split(".")
        rna = getattr(bpy.ops, module_name)
        rna = getattr(rna, op_name).get_rna_type()
        out("      label: %r" % getattr(rna, "name", "?"))
        out("      description: %r" % getattr(rna, "description", "?"))
        for prop in rna.properties:
            if prop.identifier in ("rna_type",):
                continue
            line = "      arg %-28s %s" % (prop.identifier, prop.type)
            if prop.type == 'ENUM':
                try:
                    items = [item.identifier for item in prop.enum_items]
                    line += "  %s" % (items[:12],)
                except Exception:
                    pass
            try:
                line += "  default=%r" % prop.default
            except Exception:
                pass
            out(line)
    except Exception as exc:
        out("      unreadable: %s" % exc)

# --- 3. what the enum offers --------------------------------------------------
# The options are the list in the dialog, and they are the only strings the
# operator will accept. The working space sits on bpy.data.colorspace, one
# pointer down, so a scan of bpy.data's own properties finds nothing -- descend.
out("\n  enums on bpy.data and one level below, with their options:")
def dump_enums(owner, label):
    try:
        props = owner.bl_rna.properties
    except Exception:
        return
    for prop in props:
        if prop.identifier == "rna_type":
            continue
        if prop.type == 'POINTER':
            try:
                value = getattr(owner, prop.identifier)
            except Exception:
                continue
            if value is not None:
                dump_enums(value, "%s.%s" % (label, prop.identifier))
            continue
        if prop.type != 'ENUM':
            continue
        try:
            items = [item.identifier for item in prop.enum_items]
        except Exception:
            items = ["<unreadable>"]
        out("    %s.%s%s" % (label, prop.identifier,
                             "" if prop.is_readonly else "  [writable]"))
        out("      %s" % (items,))

dump_enums(bpy.data, "bpy.data")

out("\n" + BAR + "\n")

folder = os.path.dirname(bpy.data.filepath) or tempfile.gettempdir()
path = os.path.join(folder, "probe_working_space.log.txt")
try:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(_lines) + "\n")
    print("  log written: %s" % path)
except Exception as exc:
    print("  could not write %s: %s" % (path, exc))

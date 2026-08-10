# ============================================================================
#  PROBE PROPERTY  v1.0
# ============================================================================
#  by Prof. Michael Klein
#     professor@virtualrepublic.org
#
#  Copyright (C) 2026  Prof. Michael Klein
#  SPDX-License-Identifier: GPL-3.0-or-later
# ============================================================================
#  Finds where a setting actually lives in the scene's RNA.
#
#  The diff can only carry what dump_scene.py records, and it records named
#  sections. A setting that sits somewhere else is invisible: it never appears
#  in a report, it is never generated, and the converted scene keeps the
#  original value while everything else looks right. That has now happened with
#  the colour management working space.
#
#  Rather than guess at property names for a Blender past the model's
#  knowledge, this walks the scene's RNA and prints every property whose path
#  matches a search term, with its current value.
#
#  Run it in the master and again in a converted scene, then compare: the pair
#  tells you both the exact RNA path and the two values, which is what
#  dump_scene.py needs to record it.
#
#  Read-only. Writes probe_property.log.txt next to the open .blend.
#
#    Scripting -> Open -> this file -> Run Script
# ============================================================================

import bpy
import os
import tempfile

# --- edit this when looking for something else --------------------------------
TERMS = ("work", "space", "reference", "colorspace", "colour", "gamut", "primaries")
DEPTH = 3
# ------------------------------------------------------------------------------

BAR = "=" * 74
_lines = []
_seen = set()


def out(text=""):
    print(text)
    _lines.append(text)


def interesting(path):
    low = path.lower()
    return any(term in low for term in TERMS)


def walk(owner, path, depth):
    """Descend through RNA pointers, printing anything whose path matches."""
    if depth > DEPTH or id(owner) in _seen:
        return
    _seen.add(id(owner))
    try:
        props = owner.bl_rna.properties
    except Exception:
        return
    for prop in props:
        name = prop.identifier
        if name == "rna_type":
            continue
        full = "%s.%s" % (path, name)
        try:
            value = getattr(owner, name)
        except Exception:
            continue
        if prop.type == 'POINTER':
            if value is not None:
                walk(value, full, depth + 1)
            continue
        if prop.type in ('COLLECTION',):
            continue
        if interesting(full):
            writable = "" if prop.is_readonly else "  [writable]"
            out("  %-58s %r%s" % (full, value, writable))
            if prop.type == 'ENUM':
                try:
                    items = [i.identifier for i in prop.enum_items]
                    if items:
                        out("      options: %s" % ", ".join(items[:12]))
                except Exception:
                    pass


out("\n" + BAR)
out("  PROBE PROPERTY -- where does a setting live?")
out(BAR)
out("  blender : %s" % bpy.app.version_string)
out("  file    : %s" % (bpy.data.filepath or "<unsaved>"))
out("  terms   : %s" % ", ".join(TERMS))

scene = getattr(bpy.context, "scene", None) or (bpy.data.scenes[0] if bpy.data.scenes else None)
if scene is None:
    out("\n  no scene.")
else:
    out("\n  matches under scene:")
    walk(scene, "scene", 1)

out("\n  and under the render settings of every scene section the dumper knows:")
if scene is not None:
    for section in ("render", "view_settings", "display_settings",
                    "sequencer_colorspace_settings", "cycles", "eevee"):
        owner = getattr(scene, section, None)
        if owner is not None:
            _seen.discard(id(owner))
            walk(owner, "scene.%s" % section, 1)

out(BAR + "\n")

folder = os.path.dirname(bpy.data.filepath) or tempfile.gettempdir()
path = os.path.join(folder, "probe_property.log.txt")
try:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(_lines) + "\n")
    print("  log written: %s" % path)
except Exception as exc:
    print("  could not write %s: %s" % (path, exc))

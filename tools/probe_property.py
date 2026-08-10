# ============================================================================
#  PROBE PROPERTY  v2.0
# ============================================================================
#  by Prof. Michael Klein
#     professor@virtualrepublic.org
#
#  Copyright (C) 2026  Prof. Michael Klein
#  SPDX-License-Identifier: GPL-3.0-or-later
# ============================================================================
#  Finds where a setting actually lives in the RNA.
#
#  The diff can only carry what dump_scene.py records, and it records named
#  sections. A setting that sits somewhere else is invisible: it never appears
#  in a report, it is never generated, and the converted scene keeps the
#  original value while everything else looks right.
#
#  Two ways to search, and the second is the one that works:
#
#    by NAME   -- guessing at identifiers for a Blender past the model's
#                 knowledge. Cheap, and it misses anything named unexpectedly.
#    by VALUE  -- you know what the setting reads in one file and what it reads
#                 in the other. Search for those strings and the property
#                 announces itself, whatever it is called.
#
#  Run it in both files and compare. The pair gives the exact RNA path and both
#  values -- which is what dump_scene.py needs in order to record it.
#
#  Read-only. Writes probe_property.log.txt next to the open .blend.
#
#    Scripting -> Open -> this file -> Run Script
# ============================================================================

import bpy
import os
import tempfile

# --- edit these ---------------------------------------------------------------
# Values you can see in the interface and want to locate. This is the reliable
# half: put in what the setting actually reads.
VALUES = ("ACEScg", "Rec.709", "Rec709", "Linear Rec.709")
# Identifier fragments, as a second net.
TERMS = ("work", "space", "reference", "colorspace", "gamut", "primaries")
DEPTH = 4
# ------------------------------------------------------------------------------

BAR = "=" * 74
_lines = []


def out(text=""):
    print(text)
    _lines.append(text)


def walk(owner, path, depth, seen, names_too=True):
    """Descend through RNA pointers, reporting matches by value and by name.

    Visited paths are tracked by PATH, not by id(). RNA wrappers are created
    fresh on every attribute access and Python reuses the id of a collected
    one, so an id-based guard silently skips whole subtrees -- which is why an
    earlier run of this probe found image_settings in one file and not in the
    other.
    """
    if depth > DEPTH or path in seen:
        return
    seen.add(path)
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
                walk(value, full, depth + 1, seen, names_too)
            continue
        if prop.type == 'COLLECTION':
            continue

        text = value if isinstance(value, str) else None
        by_value = text is not None and any(v.lower() == text.lower()
                                            or v.lower() in text.lower()
                                            for v in VALUES)
        by_name = names_too and any(term in full.lower() for term in TERMS)
        if not (by_value or by_name):
            continue
        mark = "  <== VALUE MATCH" if by_value else ""
        writable = "" if prop.is_readonly else "  [writable]"
        out("  %-56s %r%s%s" % (full, value, writable, mark))


out("\n" + BAR)
out("  PROBE PROPERTY -- where does a setting live?")
out(BAR)
out("  blender : %s" % bpy.app.version_string)
out("  file    : %s" % (bpy.data.filepath or "<unsaved>"))
out("  values  : %s" % ", ".join(VALUES))
out("  terms   : %s" % ", ".join(TERMS))

scene = getattr(bpy.context, "scene", None) or (bpy.data.scenes[0] if bpy.data.scenes else None)

out("\n  under the scene:")
if scene is None:
    out("    no scene.")
else:
    walk(scene, "scene", 1, set())

# The working space may not belong to the scene at all. Look wider, each from
# its own root so one subtree cannot mask another.
out("\n  elsewhere:")
for label, root in (("world", getattr(scene, "world", None) if scene else None),
                    ("view_layer", getattr(bpy.context, "view_layer", None)),
                    ("preferences", getattr(bpy.context, "preferences", None))):
    if root is None:
        continue
    before = len(_lines)
    # Only value matches out here: the name net pulled in the entire
    # preferences tree and buried the one line that mattered.
    walk(root, label, 1, set(), names_too=False)
    if len(_lines) == before:
        out("  %-56s (nothing)" % label)

# Every image carries its own colour space, and images live in a collection --
# which the walk skips, because collections are where the geometry is. This is
# the one collection worth listing by hand: an HDRI or a texture read as the
# wrong space is exactly the kind of difference that shows up as a "working
# space" in the interface without being a scene property at all.
out("\n  colour space of every image datablock:")
if not bpy.data.images:
    out("    (no images)")
for image in bpy.data.images:
    try:
        space = image.colorspace_settings.name
    except Exception as exc:
        space = "unreadable (%s)" % exc
    mark = "  <== VALUE MATCH" if any(v.lower() in str(space).lower()
                                      for v in VALUES) else ""
    out("    %-44s %-24s %s%s" % (image.name, space,
                                  "%dx%d" % tuple(image.size) if image.size else "",
                                  mark))

out(BAR + "\n")

folder = os.path.dirname(bpy.data.filepath) or tempfile.gettempdir()
path = os.path.join(folder, "probe_property.log.txt")
try:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(_lines) + "\n")
    print("  log written: %s" % path)
except Exception as exc:
    print("  could not write %s: %s" % (path, exc))

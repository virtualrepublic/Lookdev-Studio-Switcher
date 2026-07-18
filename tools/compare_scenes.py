# ============================================================================
#  COMPARE SCENES  v1.1  --  diff two dump_scene.py snapshots
# ============================================================================
#  by Prof. Michael Klein
#     professor@virtualrepublic.org
#
#  Part of the Lookdev Switcher toolchain. Plain Python, no Blender needed.
#
#  USAGE:
#     python compare_scenes.py original.json modified.json
#     python compare_scenes.py original.json modified.json --summary
#     python compare_scenes.py original.json modified.json --json diff.json
#     python compare_scenes.py original.json modified.json --only objects.DOF
#
#  Reads the "before" and "after" snapshot and reports what a migration script
#  would have to do to turn the first into the second:
#     +  ADDED    exists only in the modified scene   -> the script must create it
#     -  REMOVED  exists only in the original         -> the script must delete it
#     ~  CHANGED  exists in both, different value     -> the script must set it
#
#  NOTE ON PATHS
#  Paths are kept as TUPLES internally, never as dotted strings. Blender names
#  contain dots ("Camera.001", "GPM.005"), so splitting a dotted path would cut
#  a datablock name in half and mis-attribute its properties. They are only
#  joined with "." for display.
# ============================================================================

import json
import argparse
import sys

# Noise that says nothing about how to rebuild the scene
IGNORE_KEYS = {
    "blend_file",
    "blender_version",
    # Derived: these tallies only restate what the real sections already show,
    # so they add entries without adding information.
    "counts",
}


def load(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def diff(a, b, path=()):
    """Recursively compare two json structures.

    Returns a list of (kind, path_tuple, old, new) with kind in
    added/removed/changed.
    """
    out = []

    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b), key=str):
            if not path and key in IGNORE_KEYS:
                continue
            sub = path + (str(key),)
            if key not in a:
                out.append(("added", sub, None, b[key]))
            elif key not in b:
                out.append(("removed", sub, a[key], None))
            else:
                out.extend(diff(a[key], b[key], sub))
        return out

    # Lists are compared as a whole: order matters in Blender
    # (constraint stack, modifier stack, node links).
    if a != b:
        out.append(("changed", path, a, b))
    return out


def fmt(path):
    """Path tuple -> readable string. Display only, never parsed back."""
    return ".".join(path)


def short(value, limit=120):
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= limit else text[:limit - 3] + "..."


def print_summary(changes):
    """Which datablocks appear, vanish or change -- the shape of the migration."""
    added, removed, changed = {}, {}, {}
    for kind, path, _old, _new in changes:
        if len(path) < 2:
            continue
        section, name = path[0], path[1]
        # A whole datablock appearing/vanishing sits at depth 2. Anything else --
        # deeper paths, or a changed value at depth 2 -- means it exists in both
        # and was edited.
        if len(path) == 2 and kind == "added":
            added.setdefault(section, set()).add(name)
        elif len(path) == 2 and kind == "removed":
            removed.setdefault(section, set()).add(name)
        else:
            changed.setdefault(section, set()).add(name)

    print("=" * 74)
    print("SUMMARY")
    print("=" * 74)
    for title, bucket in (("NEW (script must create)", added),
                          ("GONE (script must remove)", removed),
                          ("MODIFIED (script must adjust)", changed)):
        print("\n%s" % title)
        if not bucket:
            print("   -")
            continue
        for section in sorted(bucket):
            names = sorted(bucket[section])
            print("   %-14s %d: %s" % (section, len(names), ", ".join(names)))


def print_details(changes, only=None):
    marks = {"added": "+", "removed": "-", "changed": "~"}
    shown = 0
    print("\n" + "=" * 74)
    print("DETAILS")
    print("=" * 74)
    current_section = None
    for kind, path, old, new in changes:
        text = fmt(path)
        if only and not text.startswith(only):
            continue
        section = path[0] if path else ""
        if section != current_section:
            current_section = section
            print("\n--- %s " % section + "-" * max(0, 68 - len(section)))
        shown += 1
        mark = marks[kind]
        if kind == "changed":
            print("  %s %s" % (mark, text))
            print("      old: %s" % short(old))
            print("      new: %s" % short(new))
        else:
            print("  %s %s: %s" % (mark, text, short(new if kind == "added" else old)))
    if not shown:
        print("\n  (no differences)")


def main():
    parser = argparse.ArgumentParser(
        description="Diff two dump_scene.py snapshots")
    parser.add_argument("original", help="snapshot of the untouched scene")
    parser.add_argument("modified", help="snapshot of your reworked scene")
    parser.add_argument("--summary", action="store_true",
                        help="only the overview, no per-property detail")
    parser.add_argument("--only", default=None,
                        help="restrict output to a path prefix, e.g. objects.DOF")
    parser.add_argument("--json", dest="json_out", default=None,
                        help="also write the diff as json")
    args = parser.parse_args()

    a = load(args.original)
    b = load(args.modified)
    changes = diff(a, b)

    print_summary(changes)
    if not args.summary:
        print_details(changes, only=args.only)

    counts = {"added": 0, "removed": 0, "changed": 0}
    for kind, _p, _o, _n in changes:
        counts[kind] += 1
    print("\n" + "=" * 74)
    print("%d differences:  %d added, %d removed, %d changed"
          % (len(changes), counts["added"], counts["removed"], counts["changed"]))

    if args.json_out:
        payload = [{"kind": k, "path": list(p), "old": o, "new": n}
                   for k, p, o, n in changes]
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
        print("Wrote %s" % args.json_out)

    return 0


if __name__ == "__main__":
    sys.exit(main())

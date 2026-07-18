# ============================================================================
#  DIFF BLENDS  v1.0  --  compare two .blend files in one Blender session
# ============================================================================
#  by Prof. Michael Klein
#     professor@virtualrepublic.org
#
#  Part of the Lookdev Switcher toolchain. One command, no intermediate files,
#  no append, no name collisions.
#
#  USAGE:
#     blender --background --python diff_blends.py -- original.blend modified.blend
#     blender --background --python diff_blends.py -- a.blend b.blend --summary
#     blender --background --python diff_blends.py -- a.blend b.blend --json diff.json
#     blender --background --python diff_blends.py -- a.blend b.blend --only objects.DOF
#
#  Windows example (adjust the Blender path):
#     "C:\Program Files\Blender Foundation\Blender 4.2\blender.exe" ^
#         --background --python diff_blends.py -- original.blend modified.blend
#
#  WHY NOT APPEND BOTH SCENES INTO ONE FILE?
#  Blender keeps objects, meshes and materials in ONE global namespace: two
#  datablocks cannot share a name. Both files descend from the same original,
#  so nearly every name collides and Append resolves that the only way it can --
#  by adding ".001". A 1:1 copy is therefore impossible by construction.
#
#  This script sidesteps the whole problem: it opens both files one after the
#  other in a SINGLE session. Each file is read in its own pristine state with
#  its authentic names, and neither file is modified. The snapshot is plain
#  Python data, so it survives open_mainfile() -- which is what makes reading
#  two files in one run possible at all.
#
#  Requires dump_scene.py and compare_scenes.py next to this file.
# ============================================================================

import bpy
import sys
import os
import json
import argparse

# Make the sibling scripts importable, wherever Blender was started from
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# Fail with a readable message instead of a bare ModuleNotFoundError
_missing = [n for n in ("dump_scene.py", "compare_scenes.py")
            if not os.path.isfile(os.path.join(SCRIPT_DIR, n))]
if _missing:
    raise SystemExit(
        "\n%s\n"
        "  Missing next to diff_blends.py: %s\n"
        "  Folder: %s\n\n"
        "  All three scripts must sit in the SAME folder:\n"
        "     diff_blends.py, dump_scene.py, compare_scenes.py\n\n"
        "  Note: 'compare_scenes_in_file.py' is a DIFFERENT script and is not\n"
        "  a substitute for 'compare_scenes.py'.\n%s"
        % ("=" * 74, ", ".join(_missing), SCRIPT_DIR, "=" * 74))

import dump_scene          # noqa: E402  (sys.path must be set up first)
import compare_scenes      # noqa: E402


def snapshot_file(path, full, frame):
    """Open a .blend and return its structural snapshot as plain Python data.

    The file is only read, never written. The returned dict holds no references
    into bpy.data, so it stays valid after the next open_mainfile().
    """
    if not os.path.isfile(path):
        raise SystemExit("File not found: %s" % path)
    print("Reading %s ..." % path)
    bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)
    return dump_scene.snapshot(full, frame)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(
        prog="diff_blends.py",
        description="Diff two .blend files without appending or writing anything")
    parser.add_argument("original", help="the untouched scene from the author")
    parser.add_argument("modified", help="your reworked scene")
    parser.add_argument("--summary", action="store_true",
                        help="only the overview, no per-property detail")
    parser.add_argument("--only", default=None,
                        help="restrict output to a path prefix, e.g. objects.DOF")
    parser.add_argument("--json", dest="json_out", default=None,
                        help="also write the diff as json")
    parser.add_argument("--full", action="store_true",
                        help="also compare full material/world node trees")
    parser.add_argument("--frame", type=int, default=0,
                        help="set both files to this frame before snapshotting, so "
                             "a turntable standing at different frames is not "
                             "reported as a difference (default 0, -1 disables)")
    parser.add_argument("--keep-snapshots", default=None, metavar="PREFIX",
                        help="also write PREFIX_original.json / PREFIX_modified.json")
    args = parser.parse_args(argv)

    frame = None if args.frame < 0 else args.frame

    # Both snapshots come from one session: plain dicts survive open_mainfile()
    before = snapshot_file(os.path.abspath(args.original), args.full, frame)
    after = snapshot_file(os.path.abspath(args.modified), args.full, frame)

    if args.keep_snapshots:
        for label, data in (("original", before), ("modified", after)):
            path = "%s_%s.json" % (args.keep_snapshots, label)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True, ensure_ascii=False)
            print("Wrote %s" % path)

    changes = compare_scenes.diff(before, after)

    print("\n%s  ->  %s" % (before["blend_file"] or args.original,
                            after["blend_file"] or args.modified))
    compare_scenes.print_summary(changes)
    if not args.summary:
        compare_scenes.print_details(changes, only=args.only)

    counts = {"added": 0, "removed": 0, "changed": 0}
    for kind, _path, _old, _new in changes:
        counts[kind] += 1
    print("\n" + "=" * 74)
    print("%d differences:  %d added, %d removed, %d changed"
          % (len(changes), counts["added"], counts["removed"], counts["changed"]))

    if args.json_out:
        payload = [{"kind": k, "path": p, "old": o, "new": n}
                   for k, p, o, n in changes]
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
        print("Wrote %s" % args.json_out)


if __name__ == "__main__":
    main()

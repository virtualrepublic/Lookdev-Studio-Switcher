# Maintaining

**Not needed to use the Lookdev Switcher.** This describes how
`setup_generated.py` is produced — the workflow behind the release, not a step
for anyone downloading it.

Users need three things: the scene, the script, Save As. See the
[README](../README.md).

---

## The idea

`setup_generated.py` is not written by hand. It is **derived** from comparing
the untouched original against my reworked scene.

Two `.blend` files stay on my machine and are never published:

| File | What it is |
|---|---|
| `LOOKDEV_STUDIO_ORIGINAL.blend` | exactly as downloaded from CGTrader, never edited |
| `LOOKDEV_STUDIO_COPY.blend` | my reworked version, where development happens |

Everything I change in the copy shows up as a difference against the original,
and that difference becomes the script. Two benefits follow:

- **Nothing gets forgotten.** A tweak I made months ago and can't remember still
  shows up in the diff.
- **Nothing of the author's leaks out.** The script carries names and numbers,
  never geometry.

When the author publishes a new version of the scene, I replace the original,
re-run the diff and see immediately what moved.

---

## The toolchain

Four scripts in `tools/`.

| Script | Runs in | Purpose |
|---|---|---|
| `dump_scene.py` | Blender | Structural snapshot of a `.blend` → plain data |
| `compare_scenes.py` | plain Python | Diffs two snapshots |
| `diff_blends.py` | Blender | Both of the above, two files, one session |
| `make_migration.py` | either | Turns a diff into runnable Blender code |

`diff_blends.py`, `dump_scene.py` and `compare_scenes.py` must sit in the same
folder — the first imports the other two.

### What the snapshot records

Collection tree with colour tags and link order, view-layer checkboxes, objects
with constraints, modifiers, transforms and visibility, cameras including the
whole DOF section, lights, world, render and colour-management settings,
markers, compositor nodes, and animation with every keyframe and f-curve
modifier.

**Of meshes it records only vertex and face counts.** The snapshot describes
structure, never content.

---

## Regenerating

```bash
# 1. diff, keeping the snapshots
blender --background --python tools/diff_blends.py -- \
    LOOKDEV_STUDIO_ORIGINAL.blend LOOKDEV_STUDIO_COPY.blend \
    --keep-snapshots snap --summary

# 2. read the full report
blender --background --python tools/diff_blends.py -- \
    LOOKDEV_STUDIO_ORIGINAL.blend LOOKDEV_STUDIO_COPY.blend > report.txt 2>&1

# 3. generate, embedding the tool
blender --background --python tools/make_migration.py -- \
    snap_original.json snap_modified.json \
    --switcher lookdev_switcher.py -o setup_generated.py
```

Then read `setup_generated.py`, check the TODO block at the bottom, and test it
on a fresh copy of the original before releasing.

Flags for `diff_blends.py`:

| Flag | Effect |
|---|---|
| `--summary` | Overview only |
| `--only objects.DOF` | Restrict to a path prefix |
| `--json diff.json` | Write the diff with full values, nothing truncated |
| `--full` | Also compare material and world node trees |
| `--frame N` | Snapshot at frame N (`-1` leaves the frame alone) |

---

## Design notes

Things that cost time to work out, recorded so they don't have to be worked out
twice.

### Two files, not two scenes in one file

Blender keeps objects, meshes and materials in **one global namespace**: two
datablocks cannot share a name. Both files descend from the same original, so
nearly every name collides, and appending resolves that the only way it can — by
adding `.001`. A 1:1 comparison is impossible that way.

`diff_blends.py` sidesteps it: both files are opened one after the other in a
single session. The snapshot is plain Python data, so it survives
`open_mainfile()`. Each file is read pristine, with its real names, and neither
is written to.

### Normalisation

Files saved at different current frames would report every animated object as
changed — a turntable at frame 3 versus frame 140 is not a structural
difference. Both are set to frame 0 before snapshotting (`--frame`, default 0).

Derived tallies (`counts`), the filename and the Blender version are filtered as
noise.

### Paths are tuples, never dotted strings

Blender names contain dots. Splitting `"cameras.Camera.001"` on `.` cuts the
datablock name in half and attributes `001` as a property of `Camera`. Paths
stay tuples internally and are only joined for display.

### Modifiers are keyed by name

A list of modifiers compares as one opaque blob, so "Subdivision added,
levels=2" would only ever surface as two truncated dumps. Keyed by name — with
an `index` to keep stack order visible — the diff reports it property by
property, and the generator can emit code for it.

### Renames are not creations

A renamed camera data block looks like one removal plus one addition. The
generator builds a rename map from the `objects.X.data` changes and recognises
the pair — otherwise it would create four empty cameras and leave the real ones
untouched.

### Phases

Generated code is emitted in order, because order matters: a camera object needs
its data block first, and a `focus_object` needs the empty to exist.

`collections → order → camera data → objects → focus → renames → modifiers →
scene → tool → self-removal`

### Blender 5.x API drift

Two things moved and are probed for rather than assumed:

| | ≤ 4.x | 5.x |
|---|---|---|
| Compositor | `Scene.node_tree` | `Scene.compositing_node_group` |
| F-curves | `Action.fcurves` | `Action.layers[].strips[].channelbags[].fcurves` |

Each dump section is wrapped individually, so one further API change records an
`__error__` and the run continues instead of dying.

---

## What the generator will not do

It refuses to guess.

Only `EMPTY` and `CAMERA` objects are generated — neither carries geometry. A new
mesh would mean shipping the author's data, so it lands in the TODO block
instead. Anything else it cannot express as a reliable API call goes there too,
never silently dropped.

`render.filepath` is blocked by name in `BLOCKED` — my scene points at a private
project directory.

Expect these in the TODO block; all are benign:

- `mb:nodes`, `SolidAction.*`, extra images — orphaned datablocks from my own
  sessions, not part of the setup
- `view_layers.*.children.FRAME/MODEL` — appear by themselves once the
  collections are linked
- `render.filepath` — blocked on purpose

---

## Release checklist

1. Regenerate `setup_generated.py`.
2. Read it, especially the TODO block.
3. Test on a **fresh** copy of the original: run it, check the panel, run it a
   second time (it must change nothing).
4. Update the tested Blender version in the README if it moved.
5. Tag, and attach `setup_generated.py` to the release.

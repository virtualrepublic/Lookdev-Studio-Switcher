# Maintaining

**Not needed to use the Lookdev Switcher.** This describes how
`setup_lookdev_scene.py` is produced — the work behind a release, not a step for
anyone downloading it.

Users need three things: the scene, the script, Save As. See the
[README](../README.md).

This is the single maintainer document. Design decisions, the procedure and the
traps live here; `CLAUDE.md` at the repository root is the condensed version
that an assistant loads automatically and points back to this file.

---

## The idea

`setup_lookdev_scene.py` is not written by hand. It is **derived** from
comparing the untouched original against the reworked scene.

Three `.blend` files stay in `_local/` and are never published:

| File | What it is |
|---|---|
| `_local/scenes/LOOKDEV_STUDIO_ALBIN_293.blend` | exactly as downloaded from CGTrader, saved by Blender 2.93, never edited |
| `_local/scenes/COMPARE/LOOKDEV_STUDIO_ORIGINAL_520.blend` | the same file re-saved by 5.2, so the diff compares like with like |
| `_local/scenes/COMPARE/LOOKDEV_STUDIO_MODIFIED_520.blend` | the master, where development happens |

`_local/scenes/LOOKDEV_STUDIO_TEST_520.blend` is the last test conversion — a
result, not a source. Overwrite it freely.

Everything changed in the master shows up as a difference against the original,
and that difference becomes the script. Two benefits follow:

- **Nothing gets forgotten.** A tweak made months ago and long since forgotten
  still shows up in the diff.
- **Nothing of the author's leaks out.** The script carries names and numbers,
  never geometry.

When the author publishes a new version of the scene, replace the original,
re-run the diff, and see immediately what moved.

Why two originals: the diff must not report Blender's own 2.93 → 5.2 upgrade as
a change. `ORIGINAL_520` is that upgrade and nothing else. `ALBIN_293` stays as
the ground truth and as the file every test conversion starts from — the same
starting point a user has.

---

## The toolchain

`tools/run.ps1` is the entry point; `_local/RUN.cmd` starts it on a double-click
(a `.ps1` does not run on double-click, the execution policy blocks it). The
menu is the procedure:

```
  1  Diff + snapshots            (summary on screen)
  2  Full report                 -> report.txt        <- read this
  3  Report, restricted          -> report_<path>.txt
  4  Generate the installer      -> ..\setup_lookdev_scene.py
  5  Fresh test copy from ALBIN_293
  6  Cross-check against albin's 2.93 file
  P  Probe: what a background Blender sees of the workspaces
```

Behind it:

| Script | Runs in | Purpose |
|---|---|---|
| `dump_scene.py` | Blender | Structural snapshot of a `.blend` → plain data |
| `compare_scenes.py` | plain Python | Diffs two snapshots |
| `diff_blends.py` | Blender | Both of the above, two files, one session |
| `make_migration.py` | either | Turns a diff into runnable Blender code |
| `export_workspace.py` | Blender | Writes the file's workspaces to `_local/workspace_ui.blend` |
| `probe_property.py` | Blender | Finds where a setting lives in the RNA, by value |
| `probe_working_space.py` | Blender | The blend file's colour space, and its operator |
| `probe_ui_state.py` | Blender | What is readable and writable about editors |
| `new-release.ps1` | PowerShell | Commit, tag, ZIP, publish |

`diff_blends.py`, `dump_scene.py` and `compare_scenes.py` must sit in the same
folder — the first imports the other two.

The probes exist because Blender 5.2 is past the assistant's knowledge cutoff.
When an API question comes up, measure it; do not assume. Every probe writes a
log next to the open `.blend`, so the answer survives the session.

### What the snapshot records

Collection tree with colour tags and link order, view-layer checkboxes, objects
with constraints, modifiers, transforms and visibility, cameras including the
whole DOF section, lights, world, render and colour-management settings,
markers, compositor nodes, animation with every keyframe and f-curve modifier —
and, since 1.3.0, `blend_file_settings`: properties of the **file** rather than
of a scene.

**Of meshes it records only vertex and face counts.** The snapshot describes
structure, never content.

---

## Regenerating by hand

`run.ps1` is the normal route. The commands behind it, if you need them:

```bash
# 1. diff, keeping the snapshots
blender --background --python tools/diff_blends.py -- \
    _local/scenes/COMPARE/LOOKDEV_STUDIO_ORIGINAL_520.blend \
    _local/scenes/COMPARE/LOOKDEV_STUDIO_MODIFIED_520.blend \
    --keep-snapshots _local/snap --summary

# 2. the full report -- read it
blender --background --python tools/diff_blends.py -- \
    <original> <modified> > report.txt 2>&1

# 3. generate, embedding the add-on and the interface
python tools/make_migration.py \
    _local/snap_original.json _local/snap_modified.json \
    --switcher lookdev_switcher.py \
    --workspace _local/workspace_ui.blend \
    -o setup_lookdev_scene.py
```

`make_migration.py` needs no Blender — plain Python is enough.

Flags for `diff_blends.py`:

| Flag | Effect |
|---|---|
| `--summary` | Overview only |
| `--only objects.DOF` | Restrict to a path prefix |
| `--json diff.json` | Write the diff with full values, nothing truncated |
| `--full` | Also compare material and world node trees |
| `--frame N` | Snapshot at frame N (`-1` leaves the frame alone) |
| `--keep-snapshots PREFIX` | Write `PREFIX_original.json` / `PREFIX_modified.json` |

Then read `setup_lookdev_scene.py`, check the TODO block at the bottom, and test
it on a fresh copy of `ALBIN_293` before releasing.

---

## What the installer does, in order

Order is not cosmetic. A camera object needs its data block first; a
`focus_object` needs the empty to exist; a compositor link needs both ends.

```
1  collections            7  modifiers
2  collection order       8  scene settings
3  camera data            9  compositor nodes
4  objects               10  compositor links
5  focus objects         11  install the add-on
6  renames               12  install the interface
                         13  working colour space  (deferred, see below)
                             remove itself
```

Every step compares before it acts, so a second run reports
`0 change(s) applied`. That property is not tidiness — it is the check that
catches a step which assigns without comparing. Keep it.

---

## The interface transfer

Blender keeps the interface in the `.blend`, so a layout can be handed to users
— but not through the diff. `dump_scene.py` records no interface data, and the
API cannot build screen areas at all (`bpy.ops.screen.area_split` needs a real
window). What works is appending finished workspaces.

`export_workspace.py` writes the file's workspaces to `_local/workspace_ui.blend`;
`make_migration.py --workspace` embeds that zlib-compressed and base64-encoded;
the installer appends them at the user's end.

Measured limits — do not spend time re-investigating these:

- **A workspace of the same name is replaced, not duplicated.** Appending a
  `Layout` onto a file that already has one would otherwise leave the user with
  `Layout` and `Layout.001`. Workspaces the user has and the export does not are
  left alone.
- **Never delete a workspace from inside the running script.** Deleting one
  frees its screens and areas; the script runs inside `bpy.ops.text.run_script()`,
  and when that operator finishes Blender builds its redo panel for the area it
  ran in. If that area has been freed, Blender dies with an access violation in
  `ED_area_type_hud_clear`. Deletion waits for a one-shot timer.
- **`bpy.data.workspaces` has no `remove()`**, and `bpy.ops.workspace.delete()`
  returns `{'CANCELLED'}` silently. `batch_remove` is the route that works, and
  every removal is verified by looking the name up again.
- **The outliner's expansion state cannot be read or written.** `SpaceOutliner`
  exposes no treestore, tree, expanded or state. Collapsing everything is the
  nearest the API allows, and closer to a lookdev file's usual state than a tree
  opened down to every material.
- **A region's pan and zoom are rebuilt on load.** Framing the node tree is an
  approximation, not a copy.
- **`Region.active_panel_category` is read-only on a region that has never been
  drawn.** Setting the sidebar tab per workspace produced ten refusals and one
  success — the one actually on screen. It is set once, at the end, on the tab
  the walk returns to.

Each installed workspace carries a stamp of the payload, so a second run does
nothing and a later release with a changed layout replaces it. The blob is
interface data only: workspaces written with `bpy.data.libraries.write()` pull
in their screens and nothing else — no objects, meshes, materials or scenes — so
none of the original download travels in it.

Without `--workspace` the script carries no layout. That is a supported
configuration, not a degraded one.

---

## The working colour space

`bpy.data.colorspace.working_space` is a property of the **file**, not of a
scene, and it is read-only. The only way to change it:

```python
bpy.ops.wm.set_working_color_space(working_space='ACEScg', convert_colors=True)
```

Options measured on 5.2 LTS: `Linear Rec.709`, `Linear Rec.2020`, `ACEScg`.
`convert_colors` is the checkbox in Blender's own *Set Blend File Working Color
Space* dialog, and it is what makes the step meaningful — without it the label
changes while the numbers stay, which reinterprets every colour instead of
converting it.

Two traps, both of which cost a day each:

**It is not `render.image_settings.linear_colorspace_settings.**` That is the
saved EXR's linear space — a different setting with a near-identical name, and
one that had been transferring correctly all along. Chasing it explains nothing.

**It must not run inside the script.** Called as a phase it crashed Blender:

```
EXCEPTION_ACCESS_VIOLATION
blender::ED_workspace_change
blender::WM_window_set_active_workspace
blender::wm_event_do_notifiers        <- after the script, not inside it
```

The conversion rewrites the whole file, and the undo push for an operation that
large lands when the **outer** operator — `bpy.ops.text.run_script()` — finishes.
That push reallocates every data-block, workspaces included, while the workspace
switch queued by the interface transfer still holds the old address.

So it waits on a flag the workspace chain sets and converts in a timer of its
own. Deferring is safe **only because the migration writes no colour anywhere** —
every generated write is a bool, a string, a number or an enum. Check that again
before adding a colour-valued step.

One visible consequence: the result is reported after the
`n change(s) applied` line, so it is not counted there.

---

## The two stamps

Both replace a silence that had already cost a release.

| Stamp | Written by | Checked by | Catches |
|---|---|---|---|
| `dumper_stamp`, in each snapshot | `dump_scene.py`, a hash of itself | `make_migration.py`, before generating | snapshots from different dumper versions, or from a dumper that has since changed |
| `TOOLCHAIN STAMP`, in the installer header | `make_migration.py`, over generator + both snapshots + add-on + workspace blend | `new-release.ps1` | an installer not regenerated after the toolchain, snapshots, add-on or interface moved |

Hashes, not timestamps: git sets every file's mtime to the checkout time, so a
timestamp check greets a fresh clone with a false alarm.

The snapshot check is **fatal** and refuses before writing anything. The release
check is fatal too and names the input that moved; it degrades to a warning when
`_local/` is absent (a clone has no snapshots) or when the installer predates the
stamp.

`compare_scenes.py` ignores `dumper_stamp`, so it never shows up as a difference.

---

## Design notes

Things that cost time to work out, recorded so they do not have to be worked out
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

Derived tallies (`counts`), the filename, the Blender version and the dumper
stamp are filtered as noise.

### Floats are compared with a tolerance

Blender stores floats as float32; the snapshot carries the float64 that JSON
round-trips. `0.01` is `0.00999999977…` in the scene, so `!=` is true forever and
a value gets rewritten to what it already holds on every run. Generated
comparisons use `abs(a - b) > max(1e-6, abs(b) * 1e-6)`.

### Paths are tuples, never dotted strings

Blender names contain dots. Splitting `"cameras.Camera.001"` on `.` cuts the
datablock name in half and attributes `001` as a property of `Camera`. Paths stay
tuples internally and are only joined for display.

### Modifiers are keyed by name

A list of modifiers compares as one opaque blob, so "Subdivision added,
levels=2" would only ever surface as two truncated dumps. Keyed by name — with an
`index` to keep stack order visible — the diff reports it property by property,
and the generator can emit code for it.

### Renames are not creations

A renamed camera data block looks like one removal plus one addition. The
generator builds a rename map from the `objects.X.data` changes and recognises
the pair — otherwise it would create four empty cameras and leave the real ones
untouched.

### Scene properties are written in a defined order, not alphabetically

Colour management is order-sensitive: `display_device → view_transform → look`.
So is the output format: `media_type → file_format → color_depth → exr_codec →
linear_colorspace_settings`. Written alphabetically, `media_type` lands last and
silently undoes the two before it — Blender refuses `OPEN_EXR_MULTILAYER` while
the media type is still `IMAGE`, the generated `try/except` catches it, and the
run reports *"skipped"* while the scene keeps the wrong format.
`SCENE_PROP_ORDER` fixes the order explicitly.

### Generated code catches `(AttributeError, TypeError)` and logs skips

A skipped setting therefore looks like success. When something *should* land and
the log says "skipped", do not believe it — check. This nearly lost ACEScg twice.

### `bpy.ops` raises only when the poll fails

An operator that declines does it silently with `{'CANCELLED'}`, so "no
exception" is not evidence of anything. Read the value back and look. An earlier
version reported ten workspace removals that never happened.

### Blender 5.x API drift

Probed for, never assumed. Each dump section is individually wrapped, so one
further change records an `__error__` and the run continues instead of dying.

| | ≤ 4.x | 5.x |
|---|---|---|
| Compositor | `Scene.node_tree` | `Scene.compositing_node_group` (confirmed) |
| F-curves | `Action.fcurves` | `Action.layers[].strips[].channelbags[].fcurves` |

Read-only in 5.2 and skipped in the dumper: `render.file_extension`,
`image_settings.has_linear_colorspace` — both derive from `file_format`.

---

## What the generator will not do

It refuses to guess.

Only `EMPTY` and `CAMERA` objects are generated — neither carries geometry. A new
mesh would mean shipping the author's data, so it lands in the TODO block
instead. Anything else it cannot express as a reliable API call goes there too,
never silently dropped.

The one thing it removes is a compositor node that the reworked scene no longer
has, and only when the node was present in the **original** snapshot — so
anything a user built themselves is never a candidate.

`render.filepath` is blocked by name in `BLOCKED`: the master scene points at a
private project directory.

---

## Bugs found and fixed — do not reintroduce

Every one of these was caught by writing a fake `bpy` and **executing** the
generated code. Eyeballing would have missed all of them. That practice has
earned its keep repeatedly; keep using it.

| Bug | Symptom | Fix |
|---|---|---|
| Raw value interpolated into a generated `log("…")` | a `\` ended the string → generated file would not parse | `log_line()` puts the whole message through `repr()` |
| `except TypeError` only | a read-only property raised `AttributeError` and killed the whole run | catch `(AttributeError, TypeError)` |
| Pointer-with-`.name` written as a string | **ACEScg silently never set** — `TypeError` swallowed by the generator's own except | `NAME_POINTERS` → write `.name` |
| Dotted path splitting | `Camera` in GONE *and* MODIFIED; `GPM.005` truncated to `GPM` | tuple paths |
| Alphabetical scene properties | `look` before `view_transform`, `media_type` after `file_format` | `SCENE_PROP_ORDER` |
| `focus_object` set unconditionally | second run reported a change → not idempotent | compare before setting |
| Compositor links emitted before nodes | links would hang in the void | separate phases |
| float32 vs float64 comparison | four values rewritten on every run | tolerance in `compare_to()` |
| Workspaces deleted inline | Blender crash in `ED_area_type_hud_clear` | delete from a timer |
| Working colour space set inline | Blender crash in `wm_event_do_notifiers` | defer to a timer, after the interface |
| `image.view_all(fit_view=True)` | zoomed a 256×256 placeholder to fill the editor | set `space.image` to the Viewer node instead |
| Release notes cut at any `## ` | a version's own sub-heading truncated the published page | stop only at `## [x.y.z]` or end of file |

---

## Known noise in the diff — benign, expect it in the TODO block

- `materials.mb:nodes`, four `SolidAction.*`, extra images — orphaned datablocks
  that arrive with the appended Film Grain group.
- `view_layers.*.children.FRAME/MODEL` — appear by themselves once the
  collections are linked.
- `cycles.denoising_use_gpu` — blocked on purpose, machine dependent.
- RNA warning `ColorManagedInputColorspaceSettings … matches no enum` — present
  in **both** files, inherited from the original. Harmless.

---

## Releasing

```powershell
pwsh -File tools\new-release.ps1 -Version 1.3.1 -Message "one line"
```

Local only: commit, tag, ZIP into `_BACKUP_/`, and archive the master scene into
`_BACKUP_/scenes/` with a manifest line. Review, then repeat the same command
with `-Publish` to push the branch and tag, create the GitHub Release, and upload
`setup_lookdev_scene.py` as its asset. Re-running with `-Publish` resumes the
same release rather than refusing because the tag exists.

It refuses when:

- the tag exists and points at something other than `HEAD`;
- the installer does not contain this version's `bl_info` tuple;
- the add-on's header line and `bl_info` disagree with each other or with the
  version being released;
- the toolchain stamp says the installer was not regenerated.

**Update `CHANGELOG.md` first.** The release notes are taken from the matching
`## [X.Y.Z]` section, up to `<!-- release-notes-end -->`. Above that marker goes
what a user needs: what changed for them, whether they must reconvert, and what
to do. Below it goes the record — mechanism, RNA paths, reasoning. An entry
without the marker is published whole, with a warning.

Before all of that:

1. Regenerate the installer (`run.ps1`, step 4).
2. Read it, especially the TODO block.
3. Test on a **fresh** copy of `ALBIN_293`: run it, check the panel, run it a
   second time — it must report `0 change(s) applied`.
4. Update the tested Blender version in the README if it moved.

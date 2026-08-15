# CLAUDE.md

Entry point for Claude Code working in this repository. Read this first, then
`docs/MAINTAINING.md` — the maintainer document, which carries the measurement
behind every rule listed here. `_CLAUDE_/WORKFLOW.md` holds what is true only on
this machine: which scene sits on which drive, and the order to work in.

This file lives at the **repository root** (next to `README.md`) — Claude Code
reads it automatically from there. `_CLAUDE_/` is git-ignored: local notes,
never pushed. `HANDOFF.md` there is a retired stub; its content moved into
`docs/MAINTAINING.md` so that a clone carries it too.

---

## One folder — working data lives inside the repo, git-ignored

The repository root is `D:\_GitHub_\virtualrepublic\Lookdev-Studio-Switcher\`.
Everything belonging to the project is inside it; the scenes sit in `_local\`,
which `.gitignore` blocks. So the repo is the whole project — copy it, back it
up or delete it as one unit — while nothing from `_local\` can ever be pushed.

```
Lookdev-Studio-Switcher\               ← THE REPOSITORY (its own .git)
├── …tracked files, see below…
└── _local\                            ← working data, git-ignored
    ├── Textures\                      albin's textures, 45 files, 883 MB
    ├── scenes\
    │   ├── LOOKDEV_STUDIO_ALBIN_293.blend      albin's download, Blender 2.93  [read-only]
    │   ├── LOOKDEV_STUDIO_TEST_520.blend       throwaway test conversion
    │   └── COMPARE\
    │       ├── LOOKDEV_STUDIO_ORIGINAL_520.blend   left side of the diff   [read-only]
    │       └── LOOKDEV_STUDIO_MODIFIED_520.blend   right side — THE MASTER
    ├── snap_original.json / snap_modified.json   diff snapshots (regenerated)
    ├── workspace_ui.blend             the exported interface, an INPUT to the
    │                                  generator like the snapshots and the
    │                                  switcher — overwrite it when the layout
    │                                  changes, every generation re-reads it
    ├── Report\                        diff reports, history
    └── RUN.cmd                        double-click launcher for ..\tools\run.ps1
```

**Three inputs feed the installer, and each has gone stale unnoticed at least
once:** the snapshots (a saved scene or a changed `dump_scene.py` invalidates
them), `lookdev_switcher.py` (the version has to be bumped before generating),
and `workspace_ui.blend` (exporting *after* generating ships the previous
layout — that one has happened three times). `run.ps1` now refuses on the first
and the third; the release script refuses on the second.

**Three scenes, three roles — do not conflate them:**

| File | Role | Replaceable |
|---|---|---|
| `ALBIN_293` | albin's download, Blender 2.93. What users actually get. Never edit. | yes — download again |
| `ORIGINAL_520` | the same scene opened in 5.2 and saved. Only ever the **left side of the diff**, so both sides are read through the same Blender and version-upgrade noise cannot appear as an intentional change. | yes — reproducible |
| `MODIFIED_520` | the reworked scene, built by hand. **The source of truth**: everything in `setup_lookdev_scene.py` derives from the diff against it. | **no** |

`ORIGINAL_520` is *not* the untouched download — earlier notes said so and were
wrong. The `.blend` header proves it: `ALBIN_293` carries `BLENDER-v293`,
`ORIGINAL_520` carries `BLENDER17-01v0502`.

**Why the scenes sit in subfolders.** They store relative texture paths:
`ALBIN_293` says `//..\Textures\`, the `COMPARE\` pair says `//..\..\Textures\`.
Both resolve to `_local\Textures\` — but only at these depths. A scene moved to
another level loses its textures. Copies of `ALBIN_293` therefore stay in
`scenes\`, copies of the pair stay in `scenes\COMPARE\`.

Blender commands are run **from `_local\`**, so the snapshots and reports land
there; the toolchain is addressed one level up as `..\tools\`. Only the tracked
files are pushed to `virtualrepublic/Lookdev-Studio-Switcher`.

`_local\` is the one thing git cannot protect: `MODIFIED_520` exists once, on one
disk, and the repository alone is not enough to rebuild the project without it.

Earlier this was two sibling folders (`COMPARE\` holding the scenes, `GitHub\`
holding the repo). If you meet that layout in old notes, this is what replaced it.

---

## Repository layout

```
Lookdev-Studio-Switcher\
├── CLAUDE.md                   this file — Claude Code entry point (tracked)
├── README.md
├── CHANGELOG.md
├── LICENSE                     GPL-3.0
├── .gitignore                  blocks *.blend
├── .gitattributes
├── lookdev_switcher.py         the add-on (embedded into the installer)
├── setup_lookdev_scene.py      GENERATED installer — the one thing users run
├── docs\
│   ├── DOCUMENTATION.md        reference
│   ├── MANUAL.md               walkthrough with screenshots
│   ├── MAINTAINING.md          maintainer notes
│   └── images\                 13 screenshots, all present
├── tools\                      the toolchain
│   ├── dump_scene.py           snapshot one .blend
│   ├── compare_scenes.py       diff two snapshots
│   ├── diff_blends.py          drives both, writes the snapshots
│   ├── make_migration.py       snapshots + switcher + interface -> installer
│   ├── export_workspace.py     the interface of a .blend -> _local\workspace_ui.blend
│   │                           GUI only; a background Blender holds no workspaces
│   ├── probe_ui_state.py       what the interface API does and does not expose
│   ├── probe_property.py       where a setting actually lives in the scene RNA
│   ├── probe_working_space.py  the blend file's colour space, and its operator
│   │                           (all three diagnostic, not part of a release run)
│   ├── run.ps1                 THE ENTRY POINT -- the steps, one per run
│   └── new-release.ps1         release helper (PowerShell)
├── _CLAUDE_\                   WORKFLOW (local steps), VibeCoding .docx — git-ignored
├── _BACKUP_\                   V000, V100, _notes, v1.0.0 zip — git-ignored
└── _local\                     the .blend scenes and diff output — git-ignored
```

`setup_lookdev_scene.py` is **generated** by the toolchain, never hand-edited.
A change belongs in the source scene or in `tools\make_migration.py`.

---

## What this project is

A Blender add-on ("Lookdev Switcher") on top of a **free scene that is not ours
to redistribute**:

> albin. (2021, November 10). *Studio Lookdev* [3D model]. CGTrader.
> https://www.cgtrader.com/free-3d-models/architectural/other/studio-lookdev

Users download the original themselves; the generated script converts *their own
copy*. The repo ships no geometry, textures or materials — only names, numbers,
instructions. `*.blend` is git-ignored so the scene cannot leak in.

Author: Prof. Michael Klein <professor@virtualrepublic.org>.
Licence: GPL-3.0-or-later (`bpy` add-ons are derivative works of Blender).
Current release: `v1.3.0` (tag present, asset uploaded).

---

## The one thing that bites — now it warns

**The generator reads snapshots, not scenes.** Any change to
`tools\dump_scene.py` makes `snap_*.json` stale. It used to warn you about
none of that, and it crashed a release once.

Two SHA-256 stamps close it. Neither uses timestamps: git sets every file's
mtime to the checkout time, so a timestamp check greets a fresh clone with a
false alarm.

| Stamp | Written by | Checked by | Catches |
|---|---|---|---|
| `dumper_stamp` in each snapshot | `dump_scene.py` (hash of itself) | `make_migration.py`, before generating | snapshots from different dumpers, or from a dumper that has since changed |
| `TOOLCHAIN STAMP` in the installer header | `make_migration.py` (hash of generator + both snapshots + switcher + workspace) | `tools\new-release.ps1` | an installer not regenerated after the toolchain, snapshots, add-on or interface moved |

The snapshot check is **fatal** — it refuses before writing anything, and says
which of the three cases it is. The release check is fatal too, and names the
input that moved; it degrades to a warning when `_local\` is absent (a clone
has no snapshots) or when the installer predates the stamp.

`compare_scenes.py` ignores `dumper_stamp`, so it never shows up as a diff.

---

## The update procedure (short form)

Full version in `_CLAUDE_\WORKFLOW.md`. The user runs it on their machine —
Blender is not in this environment. Everything goes through one entry point:

```
_local\RUN.cmd          double-click; run.ps1 offers the steps one at a time

  1  diff + snapshots          4  generate the installer
  2  full report -> report.txt 5  fresh test copy from ALBIN_293
  3  report, restricted        6  cross-check against albin's 2.93 file
```

**No Blender path is written out anywhere.** `run.ps1` resolves `blender.exe`
itself, matching the 5.2 series — not "the newest", because ten versions sit
side by side in the Launcher. The folder name carries the build hash, so any
written-out path breaks at the next update, and silently: a wrong path just
fails.

**Step 4 refuses to run on stale snapshots** — when `MODIFIED_520.blend` or
`tools\dump_scene.py` is newer than the JSONs. That is "the one thing that
bites" above, now enforced instead of remembered.

There is deliberately no run-everything option: between the diff and the
generator sits the human reading of the report.

`diff_blends.py` imports `dump_scene.py` and `compare_scenes.py` from its **own**
folder, so all four must stay together in `tools\`.

Then: test the generated script on a **fresh copy** of the original, run it
**twice** (second run reports zero changes), bump the version, use
`tools\new-release.ps1`.

Panel-only change → no diff, just regenerate so the new panel is embedded.
Scene change → release notes must say **existing users have to reconvert**.

---

## Environment facts (user's machine, not this repo)

| | |
|---|---|
| Blender | `C:\Users\el profesor\Desktop\Blender_Launcher\stable\blender-5.2.0-lts.fbe6228777e7\blender.exe` |
| Version | 5.2.0 LTS — **past the model's knowledge cutoff; probe the API, don't assume** |
| OS | Windows, CMD/PowerShell. The user is not a command-line native — give complete, pasteable command lines. |

---

## Hard-won rules (full reasoning in `docs/MAINTAINING.md`)

Each of these is the short form. `docs/MAINTAINING.md` carries the measurement
behind it and travels with a clone; this list does not repeat it.


- **Paths are tuples, not dotted strings** — Blender names contain dots.
- **Modifiers/constraints keyed by name**, with an `index` for stack order.
- **Renames are not creations** — the generator maps `objects.X.data` changes.
- **Camera data addressed by object name**, never `Camera.001` (load-order suffix).
- **Renames run before anything that names a data block.** The camera and focus
  phases address the block by its *new* name, which does not exist until the
  rename has happened. With renames last, `bpy.data.cameras.get('Camera_large')`
  returned `None`, `if data:` skipped the whole block and logged nothing, and
  four of five cameras kept their original values on the first run. Fixed
  2026-08-15; the generated installer needs regenerating to carry the fix.
- **Phases** — collections → order → renames → camera data → objects → focus →
  modifiers → scene → compositor nodes → compositor links → install tool →
  install workspace → working space (deferred) → self-remove.
- **The working space is an operator, and it must not run inside the script.**
  `bpy.data.colorspace.working_space` belongs to the *file*, not to a scene, and
  it is read-only: only
  `bpy.ops.wm.set_working_color_space(working_space=…, convert_colors=True)`
  changes it, and that rewrites every colour in the file. Called inline it
  crashed Blender — `ED_workspace_change` ← `WM_window_set_active_workspace` ←
  `wm_event_do_notifiers`, i.e. *after* the script. The undo push for an
  operator that large lands when the outer `text.run_script()` finishes; it
  reallocates every data-block, and the workspace switch queued by
  `install_workspace()` is left pointing at freed memory. It now waits on a flag
  the workspace chain sets and converts in a timer of its own. Safe to defer
  only because the migration writes no colour anywhere — check that again before
  adding a colour-valued step. Not to be confused with
  `render.image_settings.linear_colorspace_settings`, the output EXR's linear
  space; the near-identical name cost a day.
- **Colour management is order-sensitive** — `display_device → view_transform → look`.
- **Full `rna_dump`, not hand-picked lists** — hand-picked lists silently hid
  sampling, denoising and the whole `cycles` block once.
- **Only EMPTY and CAMERA objects are generated** — a mesh would mean shipping data.
- **Generated code catches `(AttributeError, TypeError)`** and logs skips — so a
  skipped setting can look like success. When something *should* land and the log
  says "skipped", do not believe it, check. (This nearly lost ACEScg.)
- **Never delete a workspace from inside the running script.** Deleting one frees
  its screens and areas; the script runs inside `bpy.ops.text.run_script()`, and
  when that operator finishes Blender builds its redo panel for the area it ran
  in. If that area has been freed, Blender dies with an access violation in
  `ED_area_type_hud_clear`. Appending and renaming are safe; deletion waits for a
  one-shot timer, after the operator has finished.
- **`bpy.ops` raises only when the poll fails.** An operator that declines does
  it silently with `{'CANCELLED'}`, so "no exception" is not evidence. Check the
  result by looking — an earlier version reported ten workspace removals that
  never happened.
- **`bpy.data.libraries.load()` fills `data_to` in place.** Hand it the same list
  you keep the names in and that list turns into datablocks behind your back.
- **How much of the interface can travel — measured, not guessed:** the workspace
  structure does (areas, splits, editor types, sizes). These do **not**, and no
  amount of work will change that:
  - *Outliner expanded/collapsed state.* `SpaceOutliner` exposes no `treestore`,
    `tree`, `expanded`, `open` or `state` — nothing at all. It is stored as
    references to the datablocks of the file it was saved in, so appending a
    workspace alone cannot carry it.
  - *The N-panel tab.* `Region.active_panel_category` is read-only — but only
    on a region that has never been drawn. Measured across eleven workspaces in
    one run: ten refusals with *"attribute ... is read-only"* and one success,
    the one tab that was actually on screen. A workspace the tidy walk only
    passes through is never drawn, so the assignment is attempted once at the
    end, on the tab the run finishes on.
  `bpy.data.workspaces` also has no `remove()`; deletion goes through
  `bpy.data.batch_remove()` or the tab's delete operator.

---

## Filter lists (where "this must not travel" goes)

- `tools\dump_scene.py`: `RENDER_SKIP`, `IMAGE_SETTINGS_SKIP`, `VIEW_SKIP`,
  `MODIFIER_SKIP`, `CONSTRAINT_SKIP`
- `tools\compare_scenes.py`: `IGNORE_KEYS`
- `tools\make_migration.py`: `BLOCKED` (machine-specific / read-only),
  `NEUTRALISE` (reset to a default), `NAME_POINTERS` (structs written via `.name`)

---

## Verifying generator changes

No Blender here. Generator bugs were caught by **writing a fake `bpy` and
executing the generated code against it** — every bug in the table in
`docs/MAINTAINING.md`, not by reading. Keep doing that.

---

## Housekeeping noticed in the tree (decide and clean up)

- **Duplicate scripts — resolved.** The loose toolchain copies and
  `setup_lookdev_scene.py` in the old working folder were byte-identical to the
  repo versions and have been removed; `tools\` is the single source of truth.
  The old `setup_generated.py` was archived to
  `_BACKUP_\_superseded\setup_generated_260717.py` (git-ignored) rather than
  deleted. `tools\run.ps1` is the entry point; `_local\RUN.cmd` only launches it.
- **`tools\` and `docs\MAINTAINING.md` are now public.** Earlier the intent was
  to keep the toolchain private. Publishing it is a fine choice — it makes the
  copyright argument transparent — but confirm it was intentional, not accidental.
- **The maintainer documentation is consolidated** — `docs/MAINTAINING.md` is
  the one versioned document; `_CLAUDE_/WORKFLOW.md` keeps only what is local to
  this machine, and `HANDOFF.md` is a retired stub. Four copies of the same
  design note had already drifted apart. (Resolved 2026-08-11.)
- **`CHANGELOG.md` exists** — keep it in step with each release and the tags.

---

## Open items

- [x] Regenerate `setup_lookdev_scene.py` with the current `lookdev_switcher.py`
      so the GPL headers are embedded. — Done, re-verified 2026-08-15: the
      `TOOL_SOURCE` block and `lookdev_switcher.py` are **899 lines** and
      byte-identical as git stores them (SHA-256 `4df96c2f9cfe3ced…`). Compare
      them **after normalising line endings**: `make_migration.py` writes the
      installer in text mode, so the working copy carries CRLF inside the block
      while `lookdev_switcher.py` is LF — 899 bytes apart, one CR per line, no
      content difference. Re-verify that way rather than trusting this checkbox.
- [ ] The copyright line now reads `Prof. Michael Klein` (Amtstitel, part of the
      name — not an academic degree to be dropped in legal notices). It was
      changed in `lookdev_switcher.py` **and** in the embedded copy inside
      `setup_lookdev_scene.py`, so the two stay in sync without Blender. The next
      regeneration reproduces it; no action needed unless the two diverge.
- [ ] Test the compositor migration on a fresh copy — `find_node_group()`
      searching Blender's bundled assets is the only part never run for real.
- [x] A snapshot version stamp so stale snapshots fail loudly instead of a
      traceback. — Done, and a second stamp with it for the installer. See
      *The one thing that bites* above for both. The `snap_*.json` have since
      been written again and **are current** (checked 2026-08-15: their
      `dumper_stamp` is `fca630ad01dff1f8…`, which is what `dump_scene.py`
      hashes to now, and both are newer than `MODIFIED_520.blend`). An earlier
      note here said they were refused; that is no longer true.
- [ ] Regenerate `setup_lookdev_scene.py`. The shipped file predates two
      things: the `TOOLCHAIN STAMP` in the header, and the phase-order fix for
      the renamed camera data blocks. Every input is present and current, so
      this is `run.ps1` step 4 alone — **no Blender needed for the generation
      itself**, only for testing the result afterwards.

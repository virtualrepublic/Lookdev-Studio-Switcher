# CLAUDE.md

Entry point for Claude Code working in this repository. Read this first, then
the private notes in `_CLAUDE_/` — `HANDOFF.md` (design history) and
`WORKFLOW.md` (update procedure) — and `docs/` for the published reference.

This file lives at the **repository root** (next to `README.md`) — Claude Code
reads it automatically from there. `HANDOFF.md` and `WORKFLOW.md` stay in
`_CLAUDE_/`, which is git-ignored: private notes, never pushed.

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
    ├── LOOKDEV_STUDIO_ORIGINAL.blend  the untouched download (reference)
    ├── LOOKDEV_STUDIO_COPY.blend      the reworked scene — all edits happen here
    ├── LOOKDEV_STUDIO_SETUP.blend     a test conversion
    ├── snap_original.json / snap_modified.json   diff snapshots (regenerated)
    ├── Report\                        diff reports, history
    └── CMD.txt                        the two toolchain command lines, ready to paste
```

Blender commands are run **from `_local\`**, so the snapshots and reports land
there; the toolchain is addressed one level up as `..\tools\`. Only the tracked
files are pushed to `virtualrepublic/Lookdev-Studio-Switcher`.

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
│   ├── dump_scene.py
│   ├── compare_scenes.py
│   ├── diff_blends.py
│   ├── make_migration.py
│   └── new-release.ps1         release helper (PowerShell)
├── _CLAUDE_\                   HANDOFF, WORKFLOW, VibeCoding .docx — git-ignored
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
Current release: `v1.2.3` (tag present).

---

## The one thing that bites

**The generator reads snapshots, not scenes.** Any change to
`tools\dump_scene.py` makes `snap_*.json` stale, and nothing warns you. Every
dumper change forces a fresh diff run before regenerating. This has crashed once.

---

## The update procedure (short form)

Full version in `_CLAUDE_\WORKFLOW.md`. Two commands, in order, run by the user on
their machine (Blender is not in this environment). Both are run **from `_local\`**,
where the scenes are; the scripts sit one level up in `tools\`. Ready to paste in
`_local\CMD.txt`, with the full path to the Blender executable:

```
blender --background --python ..\tools\diff_blends.py -- LOOKDEV_STUDIO_ORIGINAL.blend LOOKDEV_STUDIO_COPY.blend --keep-snapshots snap --summary
blender --background --python ..\tools\make_migration.py -- snap_original.json snap_modified.json --switcher ..\lookdev_switcher.py -o ..\setup_lookdev_scene.py
```

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

## Hard-won rules (full reasoning in the HANDOFF notes)

- **Paths are tuples, not dotted strings** — Blender names contain dots.
- **Modifiers/constraints keyed by name**, with an `index` for stack order.
- **Renames are not creations** — the generator maps `objects.X.data` changes.
- **Camera data addressed by object name**, never `Camera.001` (load-order suffix).
- **Phases** — collections → order → camera data → objects → focus → renames →
  modifiers → scene → compositor nodes → compositor links → install → self-remove.
- **Colour management is order-sensitive** — `display_device → view_transform → look`.
- **Full `rna_dump`, not hand-picked lists** — hand-picked lists silently hid
  sampling, denoising and the whole `cycles` block once.
- **Only EMPTY and CAMERA objects are generated** — a mesh would mean shipping data.
- **Generated code catches `(AttributeError, TypeError)`** and logs skips — so a
  skipped setting can look like success. When something *should* land and the log
  says "skipped", do not believe it, check. (This nearly lost ACEScg.)

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
executing the generated code against it** — every bug in the HANDOFF table, not
by reading. Keep doing that.

---

## Housekeeping noticed in the tree (decide and clean up)

- **Duplicate scripts — resolved.** The loose toolchain copies and
  `setup_lookdev_scene.py` in the old working folder were byte-identical to the
  repo versions and have been removed; `tools\` is the single source of truth.
  The old `setup_generated.py` was archived to
  `_BACKUP_\_superseded\setup_generated_260717.py` (git-ignored) rather than
  deleted. `_local\CMD.txt` points at `..\tools\`.
- **`tools\` and `docs\MAINTAINING.md` are now public.** Earlier the intent was
  to keep the toolchain private. Publishing it is a fine choice — it makes the
  copyright argument transparent — but confirm it was intentional, not accidental.
- **Handoff notes now live in `_CLAUDE_\`** — `HANDOFF.md` and
  `WORKFLOW.md`, git-ignored (private). `CLAUDE.md` sits at the repo root and is
  tracked, so Claude Code loads it automatically. (Resolved.)
- **`CHANGELOG.md` exists** — keep it in step with each release and the tags.

---

## Open items

- [x] Regenerate `setup_lookdev_scene.py` with the current `lookdev_switcher.py`
      so the GPL headers are embedded. — Done: the `TOOL_SOURCE` block was
      verified line-by-line against `lookdev_switcher.py` and is identical (892
      lines). Re-verify that way rather than trusting this checkbox.
- [ ] The copyright line now reads `Prof. Michael Klein` (Amtstitel, part of the
      name — not an academic degree to be dropped in legal notices). It was
      changed in `lookdev_switcher.py` **and** in the embedded copy inside
      `setup_lookdev_scene.py`, so the two stay in sync without Blender. The next
      regeneration reproduces it; no action needed unless the two diverge.
- [ ] Test the compositor migration on a fresh copy — `find_node_group()`
      searching Blender's bundled assets is the only part never run for real.
- [ ] Consider a snapshot version stamp (dumper writes it, generator checks it)
      so stale snapshots fail loudly instead of a traceback.

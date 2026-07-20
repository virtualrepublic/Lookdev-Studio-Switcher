# Changelog

All notable changes to the Lookdev Studio Switcher are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html):
`MAJOR.MINOR.PATCH`.

- **MAJOR** — a change that breaks an existing scene or workflow.
- **MINOR** — a new feature, backwards compatible.
- **PATCH** — a bug fix or documentation correction.

Every released version is tagged in git (`vX.Y.Z`) and archived as a ZIP in
`_BACKUP_/` (local only, not pushed).

---

## [Unreleased]

_Work in progress lands here until the next tag._

---

## [1.2.1] — 2026-07-20

### Fixed
- **Auto-collect to MODEL** now handles an imported **collection** correctly.
  Previously it pulled the individual objects out into `MODEL` and left the
  imported collection behind, empty. It now re-parents the whole collection
  under `MODEL` — the collection and its contents move together. Loose objects
  imported without a collection are still linked into `MODEL` as before, and a
  collection nested inside another imported collection rides along with its
  parent rather than being flattened. Collections that are only instanced, and
  the rig's own collections, are left untouched.

Panel-only change — the scene is untouched, so **no reconversion is needed**.

---

## [1.2.0] — 2026-07-20

### Added
- **Set Render Path** — a panel button that points the output at
  `//Render/<blend name>/<blend name>_`, i.e. a per-project folder next to the
  saved `.blend`, with the file name as the image prefix (Blender appends the
  4-digit frame number and extension, e.g. `MyProject/MyProject_0001.exr`). The
  folder and prefix follow the **saved project file name**, not the scene name;
  if the file has never been saved the button reports that and changes nothing,
  since a `//` relative path needs a saved file anyway.

Panel-only change — the scene is untouched, so **no reconversion is needed**.
Existing users get the button by re-running the current `setup_lookdev_scene.py`
(or reloading the panel).

---

## [1.1.0] — 2026-07-19

### Added
- **Auto-collect to MODEL** — newly imported or added geometry is moved into the
  `MODEL` collection automatically, so an import lands on the turntable without a
  manual drag. Cameras, lights and the rotation empty are left alone; runs in
  Object Mode only, and a panel toggle (on by default) turns it off.

### Changed
- **FRAME** now leaves a safe-action margin (`FRAME_FILL`, default `0.9`): the
  model fills ~90 % of the frame instead of touching the edge, so the silhouette
  keeps a border as the turntable turns. Set `FRAME_FILL = 1.0` for the previous
  maximum-crop behaviour.
- Addon version bumped to 1.1.0.

---

## [1.0.2] — 2026-07-19

Render-settings update, regenerated from the reworked scene.

> **Existing users must reconvert:** run the new `setup_lookdev_scene.py` on a
> fresh copy of the original scene to pick these up. Re-running it on an
> already-converted file also applies the changed values.

### Changed
- Render sampling lowered from **1024 to 512** samples (documentation updated
  across README, MANUAL and DOCUMENTATION).
- Resolution is no longer forced to 200 % — it stays at the scene default
  (100 %); the "what the conversion changes" table drops that row.

### Added
- Viewport denoiser set to **OpenImageDenoise** (`cycles.preview_denoiser`).
- **GPU compositor** (`render.compositor_device = 'GPU'`).
- **Persistent data** enabled (`render.use_persistent_data = True`) — faster
  re-renders at the cost of memory.

---

## [1.0.1] — 2026-07-18

Housekeeping release — no functional change to the tool or the installer.

### Changed
- Documentation image links repaired: `turn-table-result.png` renamed to
  `turntable-result.png`; the not-yet-shot `config-*.png` cells now read
  _screenshot TODO_ instead of showing broken images.
- `CLAUDE.md` moved to the repository root so Claude Code loads it
  automatically; its internal paths updated for the new layout.

### Removed
- Six unreferenced screenshots pruned from `docs/images/`.
- Duplicate toolchain scripts in the working folder removed in favour of the
  canonical `tools/` copies (repo is now the single source of truth).

### Added
- `tools/new-release.ps1` — one-step versioned backup (commit + tag + ZIP).
- `_CLAUDE_/` handoff notes (`HANDOFF.md`, `WORKFLOW.md`) kept local via
  `.gitignore`.

---

## [1.0.0] — 2026-07-18

First public release.

### Added
- `setup_lookdev_scene.py` — one-shot converter that rebuilds the scene,
  installs the Lookdev Switcher, and removes itself.
- `lookdev_switcher.py` — the in-scene panel: five configuration buttons,
  depth-of-field control for all cameras at once, and one-press turntable
  rigging for imported models.
- Documentation: `README`, `docs/MANUAL.md`, `docs/DOCUMENTATION.md`,
  `docs/MAINTAINING.md`.
- Maintainer toolchain in `tools/` — `dump_scene.py`, `compare_scenes.py`,
  `diff_blends.py`, `make_migration.py` — used to derive the setup script by
  diffing the untouched original scene against the reworked copy.

### Notes
- The Studio Lookdev scene by albin is **not** included and never will be —
  the repository ships names and numbers only, no geometry.
- Conversion raises sampling to 1024 and switches render output to multi-layer
  EXR. Both are reversible; see the reference.
- Built and tested on Blender 5.2 (ACES 2.0 colour management, 5.x compositor).

[Unreleased]: https://github.com/virtualrepublic/Lookdev-Studio-Switcher/compare/v1.2.1...HEAD
[1.2.1]: https://github.com/virtualrepublic/Lookdev-Studio-Switcher/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/virtualrepublic/Lookdev-Studio-Switcher/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/virtualrepublic/Lookdev-Studio-Switcher/compare/v1.0.2...v1.1.0
[1.0.2]: https://github.com/virtualrepublic/Lookdev-Studio-Switcher/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/virtualrepublic/Lookdev-Studio-Switcher/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/virtualrepublic/Lookdev-Studio-Switcher/releases/tag/v1.0.0

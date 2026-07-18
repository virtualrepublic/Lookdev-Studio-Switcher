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

[Unreleased]: https://github.com/virtualrepublic/Lookdev-Studio-Switcher/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/virtualrepublic/Lookdev-Studio-Switcher/releases/tag/v1.0.0

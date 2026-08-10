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

### Added
- **The generated script can carry the interface.** Blender keeps the interface
  in the `.blend`, so a layout can be handed to users — but not through the
  diff: `dump_scene.py` records no interface data, and the API cannot build
  screen areas at all (only `bpy.ops.screen.area_split`, which needs a real
  window). What works is appending finished workspaces.
  `tools/export_workspace.py` writes the file's workspaces — all of them, or a
  named subset — to a `.blend` of its own; `make_migration.py --workspace`
  embeds that zlib-compressed and base64-encoded; and the installer puts them
  into the user's scene. A workspace of the same name is **replaced, not
  duplicated**: appending a `Layout` onto a file that already has one would
  otherwise leave the user with `Layout` and `Layout.001`. Workspaces the user
  has and the export does not are left alone. Each installed workspace carries
  a stamp of the payload, so a second run does nothing and a later release with
  a changed layout replaces it. The blob is interface data only — workspaces
  written with `bpy.data.libraries.write()` pull in their screens and nothing
  else, no objects, meshes, materials or scenes, so none of the original
  download travels in it, and the export reports what actually went in.
  Optional: without `--workspace` the script carries no layout.
- **The panel shows its version.** The N-panel header now reads
  *Lookdev Switcher 1.2.3* instead of *Lookdev Switcher*, taken from
  `bl_info["version"]` at registration. A converted scene previously gave no
  way at all to tell which build it carried — the only check was to open the
  text block and read it.

### Fixed
- **A compositor node deleted in the reworked scene is now deleted at the user''s
  end too.** The generator only ever added and changed; a `removed` entry went
  into the TODO block and the node stayed behind, so a converted scene kept a
  node the master had not had for months. It is the only step in the migration
  that takes something away, and it is deliberately narrow: only nodes present
  in the **original** snapshot are named, so anything a user built themselves is
  never a candidate. Already gone means nothing happens, which keeps the
  "run it twice, no changes" property intact.
- **The file no longer contradicts itself about its version.** The header said
  `LOOKDEV SWITCHER v1.2` while `bl_info` said `(1, 2, 3)`. Since the header is
  the first line anyone reads, an up-to-date file looked stale. Both now carry
  the full version, and `tools/new-release.ps1` refuses to release when the
  header, `bl_info` and the released version do not all agree. The stale date
  line in the header is gone — the changelog and git history carry that.

### Changed
- **Copyright notice** now reads `Prof. Michael Klein` instead of `Michael Klein`
  in `lookdev_switcher.py` and in the copy embedded in `setup_lookdev_scene.py`.
  "Prof." is an Amtstitel under Berlin state law and part of the name, so unlike
  an academic degree it belongs in the legal notice. No change in behaviour — the
  licence, the terms and the add-on itself are untouched.

---

## [1.2.3] — 2026-08-09

### Fixed
- **Align & Link Model** (and **FRAME**) now work on a **collection linked or
  instanced from another scene or file**. Such a collection enters the scene as an
  empty that *instances* it, with no meshes of its own in `MODEL`, so the
  measurement found nothing and reported *"No visible geometry found to measure"*.
  Measuring now expands collection instances through the depsgraph — which also
  covers nested and library-linked collections — so the model is measured, centred
  and rigged like any local geometry. FRAME can additionally frame a selected
  collection instance.

### Changed
- **FRAME** now grows the frame camera's **far clip (clip end)** to fit large
  models, so a big object is no longer cut off by the camera's clip plane. The
  clip end is only ever increased — to the distance of the farthest framed point
  with a safety margin — so smaller models keep the studio camera's original
  near/far range.

Panel-only change — the scene is untouched, so **no reconversion is needed**.
Existing users pick it up by re-running the current `setup_lookdev_scene.py` (or
reloading the panel).

---

## [1.2.2] — 2026-08-09

### Fixed
- **The Lookdev panel no longer follows the scene into `File → New`** (or into an
  unrelated file opened in the same session). Panel classes register per Blender
  *session*, not per `.blend`, so the panel used to linger in a fresh scene until
  Blender was restarted. A persistent `load_post` guard now removes the panel, its
  Scene properties and the background timer whenever the loaded file is not a
  Lookdev scene, and the tool re-installs itself when a Lookdev file is opened.
- Registration is now **idempotent**: re-running the script, or opening a second
  Lookdev file in the same session, no longer risks an "already registered" error.

Panel-only change — the scene is untouched, so **no reconversion is needed**.
Existing users pick it up by re-running the current `setup_lookdev_scene.py` (or
reloading the panel).

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

[Unreleased]: https://github.com/virtualrepublic/Lookdev-Studio-Switcher/compare/v1.2.3...HEAD
[1.2.3]: https://github.com/virtualrepublic/Lookdev-Studio-Switcher/compare/v1.2.2...v1.2.3
[1.2.2]: https://github.com/virtualrepublic/Lookdev-Studio-Switcher/compare/v1.2.1...v1.2.2
[1.2.1]: https://github.com/virtualrepublic/Lookdev-Studio-Switcher/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/virtualrepublic/Lookdev-Studio-Switcher/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/virtualrepublic/Lookdev-Studio-Switcher/compare/v1.0.2...v1.1.0
[1.0.2]: https://github.com/virtualrepublic/Lookdev-Studio-Switcher/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/virtualrepublic/Lookdev-Studio-Switcher/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/virtualrepublic/Lookdev-Studio-Switcher/releases/tag/v1.0.0

# Lookdev Switcher — Reference

Everything the panel does, and everything the conversion changes in your scene.
For the three-step setup, see the [README](../README.md). For a walkthrough with
screenshots, see the [Manual](MANUAL.md).

---

## Contents

- [Compatibility](#compatibility)
- [Panel reference](#panel-reference)
- [What the conversion changes](#what-the-conversion-changes)
- [Customising](#customising)
- [Troubleshooting](#troubleshooting)

---

## Compatibility

**Blender 5.2+ recommended** — built and tested there.

Nothing is blocked on an older Blender. Collections, cameras, objects, modifiers
and the Cycles settings apply regardless. ACES 2.0 colour management, the EXR
colour space and the compositor need 5.x; where they cannot be set, the script
says so by name and carries on.

---

## Panel reference

*3D viewport → `N` → **Lookdev** tab*

### Configuration buttons

Five buttons: `MACRO`, `SMALL`, `MEDIUM`, `LARGE`, `FRAME`.

Each one:

1. Un-excludes its collection and **everything under it** — nested collections
   and objects alike. The recursion matters: un-excluding a parent alone would
   leave a hidden sub-collection hidden.
2. Excludes the other four.
3. Sets the matching camera (`macro`, `small`, …) as the scene camera.

The pressed state follows the active scene camera, so the panel reflects reality
rather than remembering its own idea of it.

**Button colours** are read from each collection's `color_tag` when the panel
draws. Change a colour in the outliner and the panel follows. A collection
without a tag — like `MODEL` — draws neutral. Nothing is hard-coded.

### FRAME

Everything the other buttons do, plus framing:

| Step | Detail |
|---|---|
| Focal length | Set to 150 mm before measuring — the field of view depends on it |
| What to frame | Selected meshes inside `MODEL` → else the whole selection → else all of `MODEL` |
| When | Sampled at frames **0 and 75**, fitted to the union of both |
| How | Camera rotation kept; position solved so the box is centred and fills the frame |

**Why two frames.** The models sit on a turntable. At frame 0 a car faces the
camera and is narrow; at frame 75 it stands sideways and is wide. Fitting frame 0
alone clips the model badly as it rotates — measured at roughly 55 % overhang in
testing.

**Which axis wins.** For every bounding box corner the script works out how far
back the camera must sit for that corner to still fit, horizontally and
vertically, and takes the maximum across all of them. The limiting axis — width
*or* height, depending on the bounding box aspect against the render aspect —
touches the frame edge exactly. Nothing is cropped.

The maths accounts for render resolution, pixel aspect, and the camera's
`sensor_fit` (`AUTO`, `HORIZONTAL`, `VERTICAL`).

### Depth of Field

| Control | Property | Default | Applies to |
|---|---|---|---|
| Depth of Field | `dof.use_dof` | on | all five cameras |
| F-Stop | `dof.aperture_fstop` | 2.8 | all five cameras |
| FRAME DOF | Y position of the `DOF` empty | 0 | the `frame` camera focuses on it |

`FRAME DOF` runs from −200 cm to 200 cm. These are **soft** limits: drag inside
the range, or click into the field and type any value.

All three are scene properties (`lookdev_dof`, `lookdev_fstop`,
`lookdev_dof_depth`) saved with your file. On load they are pushed back onto the
cameras, so panel and cameras cannot drift apart.

### Align & Link Model

Prepares an imported model for the turntable. Put the model into `MODEL` and
press the button.

1. **Measure** — bounding box of every *visible* mesh in `MODEL`,
   sub-collections included. Hidden parts are ignored and can't pull the centre
   off.
2. **Place** — the `LINKED_ROTATION` empty at the horizontal centre and the floor
   (minimum Z) of that box.
3. **Group** — every parentless object across all sub-collections is parented to
   it, keeping its world transform. Their children come along.
4. **Move** — the empty goes onto `ROTATION_LINK`, and the whole group rides
   along rigidly, so the model's floor centre lands exactly on the rig's pivot.
5. **Bind** — a `Child Of` constraint to `ROTATION_LINK` with the inverse matrix
   set (the scripted equivalent of *Set Inverse*), so nothing jumps.

All of it runs at **frame 0**, the rest pose of `ROTATION_LINK` — the constraint
inverse is only meaningful there. Your current frame is restored afterwards.

**Run it once per model.** A second press would re-measure an already-grouped
model and shift it.

The grouping deliberately includes hidden objects even though the measuring does
not: a hidden part left out of the group would stand still while everything else
turns.

---

## What the conversion changes

### Camera data blocks

| Object | Before | After |
|---|---|---|
| `medium` | `Camera` | `Camera_medium` |
| `macro` | `Camera.001` | `Camera_macro` |
| `small` | `Camera.002` | `Camera_small` |
| `large` | `Camera.003` | `Camera_large` |

The camera *objects* already exist in the original — only their data blocks get
speaking names.

> They are addressed through the **object** names, never through `Camera.001`.
> Those suffixes are handed out in load order and could point at a different
> camera in your copy. `macro` is `macro` everywhere.

### Collections

Created: `FRAME` (colour 05, blue) and `MODEL` (no tag, neutral).

Colour tags corrected:

| Collection | Before | After |
|---|---|---|
| `SMALL` | none | 02 orange |
| `MEDIUM` | 02 | 03 yellow |
| `LARGE` | 06 | 04 green |
| `RENDER` | 01 | 06 violet |

Outliner order is restored exactly:

```
MACRO, SMALL, MEDIUM, LARGE, FRAME, RENDER, MODEL
```

Blender has no reorder API for collection children — the order *is* the link
order. So everything is unlinked and relinked in sequence, with anything
unplanned appended afterwards so it can't be lost.

> Relinking rebuilds the view layer and resets the outliner exclude checkboxes.
> Harmless: the conversion runs once, and the switcher sets those checkboxes on
> every click.

### Objects

- `DOF` — plain-axes empty at the origin, in `FRAME`
- `frame` — camera on the new `Camera_frame` data (150 mm, f/22, focused on
  `DOF`), in `FRAME`

### Modifiers

Subdivision Surface on `TTPM` (Turn_Wood_Plank_Cylinder.079) and `GPM.005`
(Carpet_Plane.024), appended after their existing *Auto Smooth* modifier.

### Render settings

Lookdev quality, not preview quality. Expect longer renders than the original
scene — that is the point.

| Setting | Before | After |
|---|---|---|
| Samples | 128 | 512 |
| Adaptive sampling | off | on, noise threshold 0.01 |
| Denoising | off | on (OpenImageDenoise, viewport too) |
| Max / diffuse / glossy / transmission / transparent bounces | 4 | 32 |
| Volume bounces | 0 | 32 |
| Light tree | off | on |
| Caustics, reflective and refractive | off | on |
| Transparent glass on transparent film | off | on |
| Compositor device | CPU | GPU |
| Persistent data | off | on |

**Not carried over:** GPU denoising. That is a statement about my machine, not
about the scene — switch it on yourself under *Render Properties → Sampling →
Denoise* if your card supports it.

### Output and colour

| Setting | Before | After |
|---|---|---|
| Format | PNG | Multi-Layer OpenEXR |
| Colour depth | 8 bit | Float (Half) |
| Codec | ZIP | DWAB |
| Working colour space | — | ACEScg |
| View transform | Filmic | ACES 2.0 |
| Look | None | ACES 2.0 - Reference Gamut Compression |
| Film | opaque | transparent |
| Units | metres | centimetres |
| Output path | — | `//` |

Your renders come out as multi-layer EXR, not PNG, in ACEScg. If you want PNG
back, change it in *Output Properties* — the switcher does not care either way.

`render.filepath` is set to `//` — the folder your `.blend` sits in, Blender's
own neutral default. Nothing of my project directory travels with the script.

### Compositor

A **Film Grain** node is added between the existing group and the output, and the
tree is rewired accordingly. It comes preset to 16 mm / Studio Broadcast,
ISO 400.

Film Grain is one of Blender's bundled Essentials node groups, not something this
repository ships. The script asks Blender where its own asset files live and
appends the group from there, so it works across installations without a
hard-coded path.

If your Blender has no such asset, the script reports:

> `!! node group 'Film Grain' not found -- add it by hand from Add > Group, then rerun`

Nothing else is affected; the rest of the conversion still applies.

---

## Customising

Everything sits at the top of `lookdev_switcher.py` — in your file, open the
Text Editor and edit it there:

```python
CONFIGS = [
    ("MACRO",  "macro",  "01"),   # collection, camera, colour
    ...
]
FRAME_LENS         = 150.0        # mm
FRAME_CHECK_FRAMES = (0, 75)      # frames sampled for the framing
DOF_DEPTH_MIN      = -2.0         # metres
DOF_DEPTH_MAX      = 2.0
```

Colour numbers only *seed* a collection that has no tag yet — they never
override a colour you picked by hand.

Want more certainty across the whole rotation? Widen the sample:
`FRAME_CHECK_FRAMES = (0, 25, 50, 75)`.

---

## Troubleshooting

**The panel disappears when the file is reopened.**
*Auto Run Python Scripts* is off. Enable it in Preferences → Save & Load, once.
Or run `lookdev_switcher.py` from the Text Editor by hand.

**"This does not look like the Studio Lookdev scene."**
The objects or collections it expects are missing, and nothing was changed. Make
sure you opened the scene from CGTrader.

**"view transform 'ACES 2.0' not available in this colour config."**
Your Blender build ships a different OCIO config. The script says so and carries
on; only colour management is skipped.

**"node group 'Film Grain' not found"**
The Film Grain node group ships with Blender as an Essentials asset, and the
script could not find it in your installation. Add it once by hand in the
Compositor via *Add → Group → Film Grain*, then run the script again. Everything
else was applied regardless.

**Renders are slow now.**
Sampling is at 512 with 32 bounces — lookdev quality. Lower *Render Properties →
Sampling → Render → Max Samples* if you only need a preview.

**My renders are EXR, not PNG.**
By design: multi-layer EXR in ACEScg, next to your `.blend`. Change it in *Output
Properties* if you prefer PNG.

**The model is cropped as the turntable spins.**
The framing sampled too few positions. Widen `FRAME_CHECK_FRAMES`.

**A modifier property is rejected.**
Modifier settings are wrapped individually in `try`. If Blender renames a
property in a future version, that one line is skipped and the rest still
applies.

# projector_camera

Project an image sequence onto an object in Blender and capture the result with a
camera, headless. One command, one run, image files out.

The projection is not reimplemented here. It comes from a bundled copy of the
[Projectors](https://github.com/Ocupe/Projectors) add-on, which builds a spot light whose
shader samples an image in place of Blender's missing projector object.

## Requirements

- Blender 5.2 (tested with 5.2.2 LTS); the add-on declares `blender_version_min = 4.2.0`
- Cycles; the script selects it, since light-node projection does not work elsewhere

## Quick start

```bash
blender -b scene.blend -P projector_camera.py -- --config config.json
```

`scene.blend` is any scene with the object you want to project onto. It is opened, used and
left untouched on disk; the script adds a `Projector` and a `SimCamera` object in memory and
reuses them on later runs instead of duplicating them.

Output goes to `output/<view_name>/<pattern_name>.png`.

## Configuration

All paths are relative to the configuration file unless absolute.

| Key | Meaning |
|---|---|
| `patterns` | Image file or directory. Sorted by filename when a directory |
| `output_dir` | Root of the output tree |
| `pattern_colorspace` | `sRGB` for photographs, `Non-Color` when the pattern encodes intensity (fringes, Gray code) |
| `render.samples` | Cycles samples per pixel |
| `render.denoise` | Keep `false` for measurement work; denoising biases the result |
| `render.device` | `CPU` or `GPU` |
| `lighting.disable_existing_lights` | Sets `hide_render` on every light except the projector. Structured light needs the projector to be the only light |
| `lighting.world_strength` | World background strength. `0.0` removes the constant offset from the image |
| `camera.width`, `camera.height` | Render resolution in pixels |
| `camera.lens`, `camera.sensor_width` | Millimetres. Pixel focal length is `width * lens / sensor_width` |
| `camera.shift_x`, `camera.shift_y` | Lens shift. `shift_y` is in units of image **width**, not height |
| `projector.throw_ratio` | Projector throw ratio, handled by the add-on |
| `projector.power` | Light power in watts; affects brightness only, not geometry |
| `projector.resolution` | Name from the add-on's resolution list, e.g. `1920x1080` |
| `projector.h_shift`, `projector.v_shift` | Lens shift in percent |
| `views[].name` | Output subdirectory |
| `views[].camera.location`, `.look_at` | Metres; `look_at` sets the orientation |
| `views[].projector.location`, `.look_at` | Same, for the projector |
| `views[].camera.intrinsics` | Optional per-view override of the `camera` block |

A view that omits `camera.intrinsics` uses the top-level `camera` block.

## What this models

Cycles ray tracing is used, so these are physical, not faked:

- occlusion and projected shadows, including the shadow regions structured light produces
- diffuse and glossy reflection, with interreflection
- inverse-square falloff of illuminance with distance
- exact perspective projection through the projector, matching a pinhole model

## What this does not model

An ideal pinhole projector is not a real projector. Absent here:

| Missing | Effect |
|---|---|
| Lens distortion | Straight lines stay straight; real projectors bend them |
| Defocus / depth of field | Fringes stay sharp at every distance |
| Sensor noise | Images are cleaner than any camera |
| Vignetting, brightness uniformity | Edge brightness differs from a real device |
| Projector gamma | Grey values do not map linearly to light |
| Camera `fx != fy` | Blender perspective cameras always have square pixels |
| Polarisation, spectral response | Not represented |

Consequence: results are systematically better than hardware. Weston et al.
(arXiv:2605.18545v1, section 3.2, figure 10) measured a 13 micrometre mean difference between
a physical rig and its Blender twin, with the simulation performing about 19 percent better,
attributed to perfect focus, infinite depth of field and no noise. Use this tool to validate
algorithms and generate data, not to claim hardware accuracy.

## Layout

```
projector_camera.py   entry point
config.json           example configuration
scene.blend           test scene (sphere, block, floor, one sun light, one user camera)
patterns/             orientation test pattern and a checkerboard
vendor/Projectors/    bundled add-on, GPL-3.0-or-later, see its LICENSE
```

## Verifying orientation

`patterns/p00_left_red_right_blue.png` is red on the left and blue on the right. If a render
shows red on the left, the projection is not mirrored. This is the cheapest check that the
add-on's mapping is behaving as expected on the Blender version in use.

## Licence

`vendor/Projectors` is GPL-3.0-or-later and keeps its own LICENSE file. Distributing this
directory distributes that code, so the combined work falls under GPL-3.

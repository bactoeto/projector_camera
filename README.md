# projector_camera

Project an image sequence onto an object in Blender and capture the result with a camera,
headless. One command, one run, image files out.

The projection is not reimplemented here. It comes from a bundled copy of the
[Projectors](https://github.com/Ocupe/Projectors) add-on, which builds a spot light whose
shader samples an image in place of Blender's missing projector object.

## Requirements

- Blender 4.2 or newer. `run.sh` refuses to start on anything older
- Cycles; the script selects it, since light-node projection does not work elsewhere

`scene.blend` was saved with Blender 5.2, so it cannot be opened by 4.2. The script itself
works on 4.2 and up; only the bundled scene is version-bound.

## Quick start

```bash
git clone <this repository>
cd projector_camera
./run.sh
```

That renders every pattern in `patterns/` from every view in `config.json`, writes the
results to `output/`, and writes the camera and projector poses for each view to
`output/calibration.json`.

Explicit files and a different Blender:

```bash
./run.sh my_scene.blend my_config.json
BLENDER=/opt/blender/blender ./run.sh
```

Without `run.sh`:

```bash
blender -b scene.blend -P projector_camera.py -- --config config.json
```

## Workflow

1. Open `scene.blend`, edit or replace the objects, save.
2. Copy `config.example.json` to `config.json` and adjust the marked fields.
3. Run `./run.sh`.
4. Results land in `output/<view_name>/<pattern_name>.png`.

The input `.blend` is never written to. A `Projector` and a `SimCamera` object are created in
memory and reused on later runs instead of piling up duplicates.

## Inputs and outputs

### Inputs

| Input | Required | Notes |
|---|---|---|
| `scene.blend` | yes | The object, materials and layout. Read only, never written back |
| `config.json` | yes | Paths, camera and projector parameters, view list |
| patterns | yes | One image file, or a directory of images |

### Outputs

```
output/
├── view_00/
│   ├── p00_left_red_right_blue.png
│   └── p01_checker.png
├── view_01/
│   └── ...
└── calibration.json
```

One PNG per view and pattern, named after the pattern file. Plus a single
`calibration.json` describing every view.

### calibration.json

```jsonc
{
  "convention": { "space": "opencv", "units": "metres" },
  "models": { "camera": "ideal pinhole, no distortion", ... },
  "warnings": [],
  "views": [
    {
      "name": "view_00",
      "camera": {
        "width": 1280, "height": 720,
        "K": [[1244.4, 0, 640], [0, 1244.4, 360], [0, 0, 1]],
        "R": [[...], [...], [...]],
        "t": [0.0, -1.32, 1.77],
        "reprojection_rms_px": 0.000018
      },
      "projector": { "width": 512, "height": 512, "K": [...], "R": [...], "t": [...],
                     "reprojection_rms_px": 0.000016 }
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `K` | 3x3 intrinsics in pixels |
| `R`, `t` | World to camera: `p_camera = R @ p_world + t` |
| `width`, `height` | Pixel grid the intrinsics refer to |
| `reprojection_rms_px` | Agreement between this model and Blender's own projection |

The convention is OpenCV's camera convention: x right, y down, z forward, metres.
That is what `cv2.projectPoints`, `cv2.triangulatePoints` and `cv2.solvePnP` expect,
so no axis juggling is needed.

The projector's `width` and `height` are its pixel grid, not the render resolution:
either the pattern's own size (while `use_custom_texture_res` is true) or the `resolution`
preset.

**What `reprojection_rms_px` does and does not mean.** It compares the exported numbers
against Blender's own projection of the same camera, so it shows that the numbers agree with
Blender. It says nothing about agreement with a physical device, and for the projector it
does not independently confirm that the add-on's light shader uses the same mapping as its
helper camera. That second question is answered separately, by measurement: see
[Verifying the projector mapping](#verifying-the-projector-mapping).

## Parameters

Every value below is passed straight to Blender or to the add-on. The script does not convert
anything; where Blender's own interface differs from a calibration matrix, the conversion is
in [Camera intrinsics](#camera-intrinsics).

### Paths

| Key | Default | Meaning |
|---|---|---|
| `patterns` | `./patterns` | One image file or a directory. A directory is sorted by filename |
| `output_dir` | `./output` | Output root |
| `pattern_colorspace` | `sRGB` | Use `Non-Color` when the image encodes intensity (fringes, Gray code) |

Paths are resolved relative to the configuration file.

### Render

| Key | Default | Meaning |
|---|---|---|
| `render.samples` | 64 | Cycles samples per pixel |
| `render.denoise` | `false` | Leave off for measurement work; denoising biases results |
| `render.device` | `CPU` | `CPU` or `GPU` |
| `render.exposure` | 0.0 | Exposure in stops, applied to the whole render |

### Lighting

| Key | Default | Meaning |
|---|---|---|
| `lighting.disable_existing_lights` | `true` | Hides every light except the projector. Structured light needs the projector to be the only source |
| `lighting.world_strength` | 0.0 | World background strength; a non-zero value adds a constant offset to every pixel |

### Camera

| Key | Default | Meaning |
|---|---|---|
| `camera.width`, `height` | 1280, 720 | Output resolution in pixels |
| `camera.lens` | 35.0 | Focal length, mm |
| `camera.sensor_width` | 36.0 | Sensor width, mm |
| `camera.shift_x`, `shift_y` | 0.0 | Lens shift, in fractions of the image **width** (see below) |
| `camera.clip_start`, `clip_end` | 0.1, 100.0 | Clipping distances, metres |
| `camera.dof.enable` | `false` | Depth of field |
| `camera.dof.fstop` | 2.8 | Aperture; lower means more blur |
| `camera.dof.focus_distance` | 2.2 | Focus distance, metres |

A view may override any of these with `views[].camera.intrinsics`.

### Projector

| Key | Default | Meaning |
|---|---|---|
| `projector.use_custom_texture_res` | `true` | `true`: the pattern file sets the pixel grid. `false`: the `resolution` entry does |
| `projector.resolution` | `1920x1080` | Pixel grid, taken from the add-on's preset list. Ignored while the flag above is `true` |
| `projector.throw_ratio` | 1.5 | Throw ratio; smaller projects a bigger image |
| `projector.power` | 1000.0 | Light power in watts; brightness only, not geometry |
| `projector.h_shift`, `v_shift` | 0.0 | Lens shift, percent |
| `projector.show_pixel_grid` | `false` | Overlays the projector's pixel grid |

`use_custom_texture_res` and `resolution` interact: with the flag on, `resolution` does
nothing and the pattern keeps its own aspect ratio. With the flag off, the pattern is fitted
to the chosen grid, which stretches it to that aspect ratio.

### Views

| Key | Meaning |
|---|---|
| `views[].name` | Output subdirectory |
| `views[].camera.location`, `.look_at` | Metres; `look_at` sets the orientation |
| `views[].projector.location`, `.look_at` | Same, for the projector |

## Camera intrinsics

Calibration gives a matrix $K$ and distortion coefficients. Blender's camera takes neither
directly, so the numbers have to be converted. All conversions below were measured on
Blender 5.2.2.

### Focal length

```
fx = width * lens / sensor_width
lens = fx * sensor_width / width
```

Example: $f_x = 1600$ px, width 1280 px, sensor 36 mm gives `lens = 45.0`.

### Vertical focal length

Blender perspective cameras always have square pixels: $f_y$ is forced equal to $f_x$.
Measured with `sensor_fit` set to `HORIZONTAL`, `VERTICAL` and `AUTO`, the frame aspect always
matched the render aspect.

If the calibrated $f_x$ and $f_y$ differ by less than about one percent, use their mean and
move on. Above that, the difference cannot be reproduced by the camera and has to be applied
afterwards as an anisotropic resize, which changes the pixel grid.

### Principal point

```
cx = width * (0.5 - shift_x)        ->  shift_x = 0.5 - cx / width
cy = height * 0.5 + shift_y * width ->  shift_y = (cy - height / 2) / width
```

Note the asymmetry: `shift_y` is measured in units of image **width**, not height. Using the
height here introduces an error equal to the aspect ratio.

Example: 1280x720 with $c_x = 512$, $c_y = 488$ gives `shift_x = 0.1`, `shift_y = 0.1`.

### Skew

$s$ cannot be represented. Modern cameras effectively have $s = 0$, so nothing is lost in
practice.

### Distortion

$k_1, k_2, k_3, p_1, p_2$ have no effect here. Neither Blender's camera nor the projector
add-on models lens distortion; the projected image is a perfect pinhole projection. Adding it
means preprocessing the projected image and post-processing the captured one, which is
planned as a later step and is not implemented.

### Projector intrinsics

The projector's pixel grid is the pattern image, so its focal length in pixels follows from
the throw ratio:

```
fx_projector = pattern_width * throw_ratio
```

This follows from the add-on source, which sets the helper camera's horizontal field of view
to $2\arctan(0.5 / \text{throw\_ratio})$. It has not been verified by measurement, unlike the
camera formulas above.

The projector's principal point is adjusted with `h_shift` / `v_shift` in percent, not with
pixel coordinates; there is no direct $c_x, c_y$ input.

### Summary

| Calibrated | Field | Conversion |
|---|---|---|
| $f_x$ | `camera.lens` | `lens = fx * sensor_width / width` |
| $f_y$ | — | equals $f_x$; below 1% difference is acceptable |
| $c_x$ | `camera.shift_x` | `shift_x = 0.5 - cx / width` |
| $c_y$ | `camera.shift_y` | `shift_y = (cy - height/2) / width` |
| $s$ | — | not representable |
| $k_n, p_n$ | — | not implemented yet |
| projector $f_x$ | `projector.throw_ratio` | approximately `fx / pattern_width` |
| projector $c_x, c_y$ | `h_shift`, `v_shift` | percent, no direct pixel input |

## What this models

Cycles ray tracing is used, so these are physical, not faked:

- occlusion and projected shadows, including the shadow regions structured light produces
- diffuse and glossy reflection, with interreflection
- inverse-square falloff of illuminance with distance
- exact perspective projection through the projector, matching a pinhole model
- camera depth of field, when `camera.dof.enable` is set

## What this does not model

An ideal pinhole projector is not a real projector. Absent here:

| Missing | Effect |
|---|---|
| Lens distortion, either device | Straight lines stay straight; real optics bend them |
| Projector defocus | Its pinhole has no aperture, so fringes stay sharp at every distance |
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

## Troubleshooting

| Symptom | Cause |
|---|---|
| `error: Blender was not found` | Install Blender, or set `BLENDER=/path/to/blender` |
| `error: Blender 4.1 is too old` | Needs 4.2 or newer |
| `configuration not found` | Wrong path, or `run.sh` was started from another directory |
| `no images found in ...` | `patterns` points at an empty directory |
| Image is black | Check `projector.power`, and that no other light replaced the projector |
| Image is washed out | `lighting.world_strength` is not zero, or `disable_existing_lights` is off |
| Projection looks stretched | `use_custom_texture_res` is off and `resolution` has another aspect ratio |
| Still black after all that | Cycles is required; other engines cannot render light nodes |

## Verifying the projector mapping

The exported projector pose comes from the helper camera that the add-on creates, not from
the light shader that actually projects the image. Nothing in the export proves the two agree,
so the mapping is measured separately.

```bash
blender -b --python verify_dots.py -- --make-pattern verify/config.json
blender -b scene.blend -P projector_camera.py -- --config verify/config.json
blender -b --python verify_dots.py -- --measure verify/config.json
```

The last command exits non-zero when the check fails and writes `verify/out/measurement.json`.

What it does:

1. projects a nine-dot pattern onto the floor, whose height is known exactly
2. locates each dot in the rendered camera image, sub-pixel
3. turns each pattern pixel into a ray, intersects the floor, and projects that 3D point
   through the exported camera model
4. compares predicted and measured pixel positions

Two residuals are reported. The absolute residual includes any constant offset. The centred
residual subtracts the mean offset first, so it isolates errors of scale and shape, which are
the ones that break triangulation.

Measured on Blender 5.2.2 with nine dots, 256 samples:

| Residual | Max | RMS | Limit |
|---|---|---|---|
| Absolute | 0.672 px | 0.567 px | 1.0 px |
| Centred | 0.137 px | 0.080 px | 0.2 px |

Result: **pass**. The shape of the mapping agrees to about 0.14 px, so the projector model is
usable for triangulation.

A mean offset of about (-0.50, -0.25) px remains. Its source is not isolated: it is either a
half-pixel convention difference between centroid indexing and the projection model, or a
small offset of the projector's principal point. It is below the tolerance either way, and
because it is constant it does not distort the shape agreement above.

Two implementation details in the measurement are worth knowing:

- centroids are computed on a flat-fielded image (divided by its own blur), otherwise the
  falloff of the projector across each dot pulls the centroid towards the bright side
- pixels outside the lit region are excluded, because dividing near-black background by itself
  turns render noise into fake peaks

## Verifying orientation

`patterns/p00_left_red_right_blue.png` is red on the left and blue on the right. If a render
shows red on the left, the projection is not mirrored. This is the cheapest check that the
add-on's mapping behaves as expected on the Blender version in use.

## Layout

```
projector_camera.py   entry point
run.sh                wrapper: version check, then Blender
config.json           example with two views
config.example.json   minimal single-view configuration
scene.blend           test scene (sphere, block, floor, one sun light, one user camera)
patterns/             orientation test pattern and a checkerboard
vendor/Projectors/    bundled add-on, GPL-3.0-or-later
docs/                 API notes and reference material
verify/               projector mapping check (pattern, config, dots.png)
```

## Licence

This repository is GPL-3.0 (see `LICENSE`) because it bundles
`vendor/Projectors`, which is GPL-3.0-or-later and keeps its own LICENSE file.
Redistributing this repository redistributes that code, so the combined work falls under
GPL-3.

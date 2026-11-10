# projector_camera

Project an image or an image sequence onto objects in an existing Blender scene, render the
result from a camera at a list of poses, and write the camera and projector calibration next
to the images. Headless, one command, no interaction.

The projection comes from a bundled copy of the
[Projectors](https://github.com/Ocupe/Projectors) add-on: a spot light whose shader samples an
image. This repository is a thin driver around it.

## Invocation

```bash
blender -b <scene.blend> -P projector_camera.py -- --config <config.json>
```

- Run from the repository root. `scene.blend` and `projector_camera.py` are resolved against
  the working directory.
- `--config` is optional and defaults to `config.json` in the working directory.
- The command is identical in bash, cmd.exe and PowerShell.
- Nothing is installed into Blender and no Python outside Blender is used.

Requirements: Blender 4.2 or newer with `blender` on `PATH`. The script selects Cycles, which
is required for light-node projection. It exits with a message if the version is older.
If `blender` is not on `PATH`, call it by its full path instead.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Every view rendered and `calibration.json` was written |
| 1 | Only from `verify/` scripts: a check failed |
| 2 | Setup problem: missing file, bad configuration, add-on failure, old Blender |

Stdout ends with two lines that are safe to parse:

```
done: <n> images written to <output_dir>
poses written to <output_dir>/calibration.json
```

## Configuration

A complete minimal configuration. Only `patterns` and the two poses per view are required;
everything else has a default.

```json
{
  "patterns": "./patterns",
  "views": [
    {
      "name": "view_00",
      "camera": {
        "location": [0.0, -2.2, 0.15],
        "look_at": [0.0, 0.0, -0.1]
      },
      "projector": {
        "location": [0.45, -2.4, 0.15],
        "look_at": [0.0, 0.0, -0.1]
      }
    }
  ]
}
```

All paths are resolved relative to the configuration file, not the working directory.

### Top level

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `patterns` | string | yes¹ | — | One image file or a directory. A directory is sorted by filename |
| `output_dir` | string | no | `./output` | Output root |
| `pattern_colorspace` | string | no | `sRGB` | Use `Non-Color` when the image encodes intensity (fringes, Gray code) |
| `projector_addon_path` | string | no | `<repo>/vendor/Projectors` | Override to use another copy of the add-on |

¹ Required unless every view sets `views[].patterns`.

### `render`

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `samples` | int | no | 64 | Cycles samples per pixel |
| `denoise` | bool | no | `false` | Leave off for measurement work; denoising biases results |
| `device` | string | no | `CPU` | `CPU` or `GPU` |
| `exposure` | float | no | 0.0 | Exposure in stops, applied to the whole render |

### `lighting`

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `disable_existing_lights` | bool | no | `true` | Hides every light object except the projector's |
| `world_strength` | float | no | 0.0 | World background strength; a non-zero value adds a constant offset to every pixel. Ignored when the scene has no World |

### `camera`

| Key | Type | Unit | Default | Notes |
|---|---|---|---|---|
| `width`, `height` | int | px | 1280, 720 | Output resolution |
| `lens` | float | mm | 35.0 | Focal length |
| `sensor_width` | float | mm | 36.0 | Sensor width |
| `shift_x`, `shift_y` | float | fraction of image width | 0.0 | Lens shift; `shift_y` is in units of width, not height |
| `clip_start`, `clip_end` | float | m | 0.1, 100.0 | Clipping distances |
| `dof.enable` | bool | — | `false` | Depth of field |
| `dof.fstop` | float | — | 2.8 | Aperture; lower means more blur |
| `dof.focus_distance` | float | m | 2.2 | Focus distance |

A view may override any of these with `views[].camera.intrinsics`, a flat object using the
same key names, e.g. `{"lens": 50.0, "shift_x": 0.02}`.

### `projector`

| Key | Type | Unit | Default | Notes |
|---|---|---|---|---|
| `use_custom_texture_res` | bool | — | `true` | `true`: the pattern file sets the pixel grid. `false`: `resolution` does |
| `resolution` | string | — | `1920x1080` | Preset from the add-on's list. Ignored while the flag above is `true` |
| `throw_ratio` | float | — | 1.5 | Throw ratio; smaller projects a bigger image |
| `power` | float | W | 1000.0 | Light power; brightness only, not geometry |
| `h_shift`, `v_shift` | float | percent | 0.0 | Lens shift |
| `show_pixel_grid` | bool | — | `false` | Overlays the projector's pixel grid; keep off for measurement |

With `use_custom_texture_res` on, the pattern keeps its own aspect ratio and `resolution` does
nothing. With it off, the pattern is stretched to the chosen grid.

### `views`

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `name` | string | no | `view_<index>` | Output file prefix |
| `patterns` | string | no | top-level `patterns` | Overrides the global list for this view |
| `camera.location` | `[x, y, z]` | yes | — | Metres |
| `camera.look_at` | `[x, y, z]` | yes | — | Sets the orientation |
| `camera.intrinsics` | object | no | — | Per-view overrides, see above |
| `projector.location` | `[x, y, z]` | yes | — | Metres |
| `projector.look_at` | `[x, y, z]` | yes | — | Sets the orientation |

## Outputs

```
<output_dir>/
├── <view_name>__<pattern_stem>.png
├── ...
└── calibration.json
```

One PNG per view and pattern in a single directory. The double underscore separates the two
names because both contain single underscores. Files are written with Blender's `PNG`
settings: 8-bit RGB, no alpha.

`calibration.json` describes every view:

```jsonc
{
  "convention": { "space": "opencv", "units": "metres" },
  "models": { "camera": "ideal pinhole, no distortion", "projector": "..." },
  "warnings": [],
  "views": [
    {
      "name": "view_00",
      "camera": {
        "width": 1280, "height": 720,
        "K": [[1244.4, 0, 640], [0, 1244.4, 360], [0, 0, 1]],
        "R": [[...], [...], [...]],
        "t": [0.0, -1.32, 1.77]
      },
      "projector": { "width": 512, "height": 512, "K": [...], "R": [...], "t": [...] }
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `K` | 3x3 intrinsics, pixels |
| `R`, `t` | World to camera: `p_camera = R @ p_world + t` |
| `width`, `height` | Pixel grid the intrinsics refer to |
| `warnings` | Non-fatal notes, e.g. non-zero projector lens shift |

The convention is OpenCV's: x right, y down, z forward, metres. It is directly usable with
`cv2.projectPoints`, `cv2.triangulatePoints` and `cv2.solvePnP`.

The projector's `width` and `height` are its pixel grid, not the render resolution: the
pattern's own size when `use_custom_texture_res` is true, otherwise the `resolution` preset.

## Guarantees

| Statement | Detail |
|---|---|
| The input `.blend` is never written | The script has no save call; opening and rendering do not modify the file |
| Nothing is added permanently | `SimCamera` and `Projector` are created in memory only |
| Existing objects are reused, not duplicated | A camera named `SimCamera` and a projector named `Projector` are reused when they already exist |
| Stale projectors are removed | Before creating one, objects whose name starts with `Projector` are deleted from the in-memory scene |
| Existing lights are hidden from rendering | `hide_render = true` on every light except the projector's, when `disable_existing_lights` is true |
| The active render camera is replaced | `scene.camera` points at `SimCamera` for the run |
| Render settings are overridden | Engine, resolution, samples, device, exposure, view transform and output path follow the configuration |

## Failure modes

| Message | Cause | Fix |
|---|---|---|
| `error: Blender 4.1.0 is too old; this tool needs 4.2 or newer` | Version below 4.2 | Use a newer Blender |
| `error: configuration not found: <path>` | Wrong `--config` path | Check the path |
| `error: configuration has no views` | Empty `views` list | Add at least one view |
| `error: view 'x' needs 'camera.location' and 'camera.look_at'` | Missing pose | Fill both fields |
| `error: view 'x' has no 'patterns' and the configuration has no default 'patterns'` | No pattern for this view | Add `views[].patterns` or a top-level `patterns` |
| `error: patterns path is neither a file nor a directory` | Bad `patterns` value | Point it at an image or a directory |
| `error: no images found in <dir>` | Empty pattern directory | Add images |
| `error: unsupported image format: <file>` | Extension outside png/jpg/jpeg/bmp/tif/tiff/exr | Convert the file |
| `error: unknown projector resolution 'X'` | Preset not in the add-on's list, while `use_custom_texture_res` is false | Use a valid preset or turn the flag on |
| `error: look_at is identical to the location of <object>` | Degenerate pose | Move one of the points |
| `error: could not register the Projectors add-on: ...` | Add-on failed to load | Check `projector_addon_path` |
| `blender: command not found` | Blender not on `PATH` | Add it, or invoke Blender by full path |

## Limits

| Missing | Effect |
|---|---|
| Lens distortion, either device | Straight lines stay straight; real optics bend them |
| Projector defocus | Its pinhole has no aperture, so fringes stay sharp at any distance |
| Sensor noise | Images are cleaner than any camera |
| Vignetting, brightness uniformity | Edge brightness differs from a real device |
| Projector gamma | Grey values do not map linearly to light |
| Camera `fx != fy` | Blender perspective cameras always have square pixels |
| Skew | Not representable |
| Polarisation, spectral response | Not represented |

An ideal pinhole projector is not a real projector. Use this tool to validate algorithms and
generate data, not to claim hardware accuracy. Weston et al. (arXiv:2605.18545v1, section 3.2,
figure 10) measured a 13 micrometre mean difference between a physical rig and its Blender
twin, with the simulation performing about 19 percent better, attributed to perfect focus,
infinite depth of field and no noise.

## Converting from a calibration

Calibration gives a matrix `K` and distortion coefficients; Blender's camera takes neither
directly. Measured on Blender 5.2.2:

```
fx = width * lens / sensor_width        lens = fx * sensor_width / width
cx = width * (0.5 - shift_x)            shift_x = 0.5 - cx / width
cy = height * 0.5 + shift_y * width     shift_y = (cy - height / 2) / width
```

`fy` is forced equal to `fx`; a difference below about one percent is acceptable. Skew and
distortion (`k1, k2, k3, p1, p2`) cannot be represented and are not applied.

For the projector, `fx_projector = pattern_width * throw_ratio`, derived from the add-on's
source, which sets the helper camera's horizontal field of view to
`2 * atan(0.5 / throw_ratio)`. The principal point is set with `h_shift` / `v_shift` in
percent; there is no pixel-coordinate input.

## Demo

```bash
blender -b demo/cube.blend -P projector_camera.py -- --config demo/config.json
```

Six views of a 2 m cube with the word `test` projected on it; camera and projector are 30
degrees apart on a 6 m hexagon. Writes `demo/output/v<index>_<angle>__test.png` and
`demo/output/calibration.json`. The demo scene carries a weak sun so the cube is visible
outside the projection; capture configurations normally leave every other light off.

## Checks

Both live outside the capture path and are run by hand.

```bash
# exported poses against Blender's own projection; run after a capture
# with the same configuration, since it reads <output_dir>/calibration.json
blender -b verify/scene.blend -P verify/check_pose.py -- --config config.example.json

# projector light shader against the exported projector model
blender -b --python verify/verify_dots.py -- --make-pattern verify/config.json
blender -b verify/scene.blend -P projector_camera.py -- --config verify/config.json
blender -b --python verify/verify_dots.py -- --measure verify/config.json
```

`check_pose.py` exits 1 on disagreement and writes nothing. `verify_dots.py --measure` writes
`verify/out/measurement.json` and exits 1 when the residual exceeds the tolerance.

## Licence

GPL-3.0: this repository bundles `vendor/Projectors`, which is GPL-3.0-or-later and keeps its
own LICENSE file.

# projector_camera

Projects an image or an image sequence onto objects in an existing Blender scene, renders the
result from a camera at a list of poses, and writes the images plus the camera and projector
calibration.

## Invocation

```
blender -b <scene.blend> -P projector_camera.py -- --config <config.json>
```

| Item | Value |
|---|---|
| Working directory | Repository root; `<scene.blend>` and `projector_camera.py` resolve against it |
| `--config` | Optional. Default `config.json`, relative to the working directory |
| Other arguments | Rejected: `error: unknown argument: <arg>` |
| `--config` without a value | `error: --config needs a path` |
| Interpreter | Blender's own Python. No system Python, no packages |
| Render engine | Cycles, selected by the script |
| Minimum Blender | 4.2.0, checked at start |

### Exit codes

| Code | Condition |
|---|---|
| 0 | Every requested image was written and `calibration.json` exists |
| 1 | Only from `verify/` scripts: a check failed |
| 2 | Any error detected by the script: bad configuration, missing file, add-on failure, old Blender |

### stdout

One line per rendered image, then two summary lines:

```
[<n>] <pattern file name> -> <absolute output path>
done: <n> images written to <output dir>
poses written to <calibration.json path>
```

Diagnostics starting with `error: ` go to stderr. Warnings starting with `warning: ` go to
stdout.

## Configuration

One JSON example; every key is defined by the tables below.

```json
{
  "projector_settings": {
    "patterns": "./patterns"
  },
  "shots": [
    {
      "name": "shot_00",
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

Three blocks, each with one meaning: `camera_settings` describes the camera, `projector_settings`
describes the projector, and `shots` lists where the two are placed for each capture.

Path values are resolved relative to the configuration file, not the working directory.
`projector_addon_path` is the exception: it is used exactly as given.

### Top level

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `camera_settings` | object | No | see below | Camera parameters |
| `projector_settings` | object | No | see below | Projector parameters, including which images it projects |
| `shots` | array | Yes | — | At least one capture |
| `output_dir` | string | No | `./output` | Created if missing |
| `pattern_colorspace` | string | No | `sRGB` | Colorspace assigned to each loaded pattern |
| `projector_addon_path` | string | No | `<repo>/vendor/Projectors` | Directory containing the add-on; not resolved against the configuration |

### `camera_settings`

| Key | Type | Required | Default | Unit |
|---|---|---|---|---|
| `width` | int | No | 1280 | px |
| `height` | int | No | 720 | px |
| `lens` | float | No | 35.0 | mm |
| `sensor_width` | float | No | 36.0 | mm |
| `shift_x` | float | No | 0.0 | Fraction of image width |
| `shift_y` | float | No | 0.0 | Fraction of image **width** |
| `clip_start` | float | No | 0.1 | m |
| `clip_end` | float | No | 100.0 | m |
| `dof.enable` | bool | No | `false` | |
| `dof.fstop` | float | No | 2.8 | |
| `dof.focus_distance` | float | No | 2.2 | m |

### `projector_settings`

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `patterns` | string | Conditional¹ | — | One image file or one directory |
| `use_custom_texture_res` | bool | No | `true` | `true`: the pattern file defines the pixel grid. `false`: `resolution` does |
| `resolution` | string | No | `1920x1080` | Preset name; used only when the flag above is `false` |
| `throw_ratio` | float | No | 1.5 | |
| `power` | float | No | 1000.0 | W |
| `h_shift` | float | No | 0.0 | percent |
| `v_shift` | float | No | 0.0 | percent |
| `show_pixel_grid` | bool | No | `false` | |

¹ Required unless every shot sets `shots[].projector.patterns`.

### `shots[]`

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `name` | string | No | `shot_<index>` | Prefix of every output file for this shot |
| `camera.location` | [float ×3] | Yes | — | m |
| `camera.look_at` | [float ×3] | Yes | — | m |
| `camera.settings` | object | No | — | Overrides any `camera_settings` key for this shot; a `dof` object replaces the whole `dof` block |
| `projector.location` | [float ×3] | Yes | — | m |
| `projector.look_at` | [float ×3] | Yes | — | m |
| `projector.patterns` | string | No | `projector_settings.patterns` | One file or one directory |

`patterns` is resolved per shot: a shot that sets `shots[].projector.patterns` uses only its own
list; a shot that does not uses `projector_settings.patterns`. The two are never merged, and at
least one must exist.

### `render`

| Key | Type | Required | Default | Values |
|---|---|---|---|---|
| `samples` | int | No | 64 | Cycles samples per pixel |
| `denoise` | bool | No | `false` | |
| `device` | string | No | `CPU` | `CPU`, `GPU` |
| `gpu_backend` | string | No | first available | `OPTIX`, `CUDA`, `HIP`, `ONEAPI`, `METAL` |
| `exposure` | float | No | 0.0 | Stops |

Both values are case-insensitive. `gpu_backend` is ignored when `device` is `CPU`. With
`device: "GPU"` and no `gpu_backend`, the first backend the running Blender supports is used, in
the order `OPTIX`, `CUDA`, `HIP`, `ONEAPI`, `METAL`. A GPU that cannot be enabled is an error,
never a silent fallback to the CPU.

### `lighting`

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `disable_existing_lights` | bool | No | `true` | Every light except the projector's gets `hide_render = true` |
| `world_strength` | float | No | 0.0 | Applied to the World background when the scene has one with a Background node |

## Inputs

| Input | Requirement |
|---|---|
| Scene | Any `.blend`. Needs objects to project onto; a camera and a light are not required |
| Patterns | Extensions `.png`, `.jpg`, `.jpeg`, `.bmp`, `.tif`, `.tiff`, `.exr` |
| Pattern directory | Sorted by file name; non-image files are ignored |
| Pattern sizes | May differ between shots. Within one shot, the first pattern defines the projector pixel grid and a warning is printed if others differ |

## Outputs

```
<output_dir>/
├── <shot name>__<pattern stem>.png
└── calibration.json
```

One PNG per shot and pattern, 8-bit RGB without alpha, extension forced to `.png`. The double
underscore separates shot name from pattern stem; both may contain single underscores.

### `calibration.json`

| Field | Type | Meaning |
|---|---|---|
| `convention.space` | string | `opencv` |
| `convention.description` | string | `world to camera; x right, y down, z forward` |
| `convention.units` | string | `metres` |
| `models.camera` | string | `ideal pinhole, no distortion` |
| `models.projector` | string | `ideal pinhole, no distortion, no defocus` |
| `warnings` | string[] | Non-fatal notes |
| `shots` | object[] | One entry per shot, in configuration order |
| `shots[].name` | string | Matches the output file prefix |
| `shots[].camera.width`, `.height` | int | Pixel grid the intrinsics refer to |
| `shots[].camera.K` | float[3][3] | Intrinsics, pixels |
| `shots[].camera.R` | float[3][3] | World to camera rotation |
| `shots[].camera.t` | float[3] | World to camera translation |
| `shots[].projector.*` | same | Projector model |

`p_camera = R @ p_world + t`, in metres, with x right, y down and z forward: the convention
used by `cv2.projectPoints`, `cv2.triangulatePoints` and `cv2.solvePnP`.

The projector's `width` and `height` are its pixel grid, not the render resolution. They equal
the pattern size when `use_custom_texture_res` is true, otherwise the `resolution` preset.

`warnings` currently reports a non-zero projector `h_shift` or `v_shift`, because the mapping
from lens-shift percentage to principal point has not been measured.

## Behaviour

| Effect | Detail |
|---|---|
| Input `.blend` | Never written: the script contains no save call |
| `SimCamera` | Camera object created if absent, reused if present |
| `Projector` | Created by the add-on if absent; an object of that name that is not a projector camera is deleted first, as is every object whose name starts with `Projector` |
| Lights | Every light except the projector's gets `hide_render = true` when `disable_existing_lights` is true |
| `scene.camera` | Points at `SimCamera` for the run |
| Render settings | Engine, resolution, samples, device, exposure, view transform, look and output path are overwritten |
| Cycles device | `render.device` and `render.gpu_backend` are applied to the running process only; no user preference is saved |
| World | Background strength is set when the scene has a World with a Background node |
| Objects, materials | Not modified |

## Errors

| Message | Condition | Exit |
|---|---|---|
| `error: configuration not found: <path>` | `--config` points at no file | 2 |
| `error: configuration has no shots` | `shots` missing or empty | 2 |
| `error: shot '<name>' needs '<role>.location' and '<role>.look_at'` | Incomplete pose | 2 |
| `error: shot '<name>' has no 'patterns' and the configuration has no default 'patterns'` | No pattern source for this shot | 2 |
| `error: patterns path is neither a file nor a directory: <path>` | Bad `patterns` value | 2 |
| `error: no images found in <dir>` | Directory has no supported image | 2 |
| `error: unsupported image format: <path>` | `patterns` is a file with another extension | 2 |
| `error: unknown projector resolution '<value>'; set use_custom_texture_res to true to follow the pattern file instead` | Preset not in the add-on's list | 2 |
| `error: projector resolution must look like 1920x1080` | Preset is not `<width>x<height>` | 2 |
| `error: look_at is identical to the location of <object>` | Degenerate pose | 2 |
| `error: Projectors add-on not found at <path>` | `projector_addon_path` wrong | 2 |
| `error: could not register the Projectors add-on: <detail>` | Add-on import failed | 2 |
| `error: the projector node tree has no Image Texture node` | Add-on version mismatch | 2 |
| `error: Blender <x.y.z> is too old; this tool needs 4.2 or newer` | Version gate | 2 |
| `error: render.device must be CPU or GPU, got '<value>'` | `render.device` is neither | 2 |
| `error: render.gpu_backend '<value>' is not supported by this Blender; available: <list>` | Backend not compiled into this Blender | 2 |
| `error: no GPU backend available; set render.device to CPU` | This Blender has no GPU support | 2 |
| `error: no <backend> device found; set render.device to CPU` | Backend present, no usable device | 2 |

## Limits

| Not modelled | Consequence |
|---|---|
| Lens distortion, camera or projector | Straight lines stay straight |
| Projector defocus | Fringes stay sharp at every distance |
| Sensor noise | Images are cleaner than any camera |
| Vignetting, brightness non-uniformity | Edge brightness differs from a real device |
| Projector gamma | Grey values do not map linearly to light |
| `fx != fy` | Blender perspective cameras have square pixels |
| Skew | Not representable |
| Polarisation, spectral response | Not represented |

Results are systematically better than hardware: a physical rig versus its Blender twin showed
a 13 micrometre mean difference, with the simulation about 19 percent better, attributed to
perfect focus, infinite depth of field and no noise (Weston et al., arXiv:2605.18545v1,
section 3.2, figure 10).

## Environment

| Requirement | Detail |
|---|---|
| Repository | `https://github.com/bactoeto/projector_camera` |
| Blender | 4.2 or newer, executable named `blender` on `PATH` |
| Bundled scenes | Saved with Blender 5.2; they cannot be opened by 4.2 |
| Python packages | None. numpy is used only by `verify/`, and ships with Blender |
| Platform | Any platform Blender runs on. No shell scripts are used |

## Checks

Run by hand, outside the capture path.

| Command | Effect |
|---|---|
| `blender -b verify/scene.blend -P verify/check_pose.py -- --config <config>` | Compares each exported pose with Blender's own projection. Exit 1 on disagreement |
| `blender -b --python verify/verify_dots.py -- --make-pattern verify/config.json` | Writes the nine-dot pattern |
| `blender -b verify/scene.blend -P projector_camera.py -- --config verify/config.json` | Captures it |
| `blender -b --python verify/verify_dots.py -- --measure verify/config.json` | Compares detected dots with the projector model; writes `verify/out/measurement.json`; exit 1 on disagreement |

`check_pose.py` reads `<output_dir>/calibration.json`, so the capture must have run with the
same configuration first.

## Licence

GPL-3.0. The repository bundles `vendor/Projectors`, which is GPL-3.0-or-later and keeps its
own LICENSE file.

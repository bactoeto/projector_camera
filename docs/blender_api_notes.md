# Blender Python API notes

Everything below was verified against the local **Blender 5.2.2 LTS** by RNA introspection,
by reading local source files, or against the 5.2 manual. Values that could not be verified
are marked as such. This file exists so the simulation script does not rely on remembered
API behaviour from older Blender versions.

## Object and data-block creation

Use the low-level API rather than `bpy.ops`, so the same code works headless (`blender -b`)
and from the Text Editor.

| Call | Purpose |
|---|---|
| `bpy.data.lights.new(name, type='SPOT')` | Projector data block. `type` enum: `POINT`, `SUN`, `SPOT`, `AREA` |
| `bpy.data.cameras.new(name)` | Camera data block |
| `bpy.data.objects.new(name, data)` | Object |
| `bpy.context.scene.collection.objects.link(ob)` | Link into the scene |
| `bpy.data.objects.remove(ob, do_unlink=True)` | Remove an object |
| `bpy.data.images.load(path, check_existing=False)` | Load an external image |

Prefer `scene.collection`, not `bpy.context.collection`; the latter is not guaranteed to be
populated in background mode.

## Projector: spot light properties

| Property | Value used | RNA description |
|---|---|---|
| `energy` | configurable, watts | "radiant power (W), ... if it wasn't limited by the spot angle" |
| `spot_size` | `math.pi - 0.001` | "Angular diameter of the spotlight beam", hard range 0.0175..pi |
| `spot_blend` | `0.0` | "The softness of the spotlight edge", range 0..1 |
| `shadow_soft_size` | `0.0` | "Light size for ray shadow sampling (Raytraced shadows)" |
| `use_square` | `True` | "Cast a square spot light shape" (available in 5.x) |
| `use_soft_falloff` | `False` | "Apply falloff to avoid sharp edges when the light geometry intersects with other objects" |
| `use_shadow` | `True` | Required: structured light needs occlusion |
| `data.node_tree` | exists by default | Contains `Emission` and `Light Output` already |

`SpotLight.use_nodes` emits a `DeprecationWarning` in 5.2 ("expected to be removed in
Blender 6.0"). It does not need to be set: the node tree is present on a fresh light.

`light.cycles` in 5.2 exposes only four writable properties: `max_bounces`,
`use_multiple_importance_sampling`, `is_portal`, `is_caustics_light`. There is **no**
`samples` property, contrary to older tutorials. Sampling is controlled solely through
`scene.cycles`.

## Projector: shader node sockets

Socket names as reported by `node.inputs` / `node.outputs` in 5.2.2:

| Node | Inputs | Outputs |
|---|---|---|
| `ShaderNodeTexCoord` | - | `Generated, Normal, UV, Object, Camera, Window, Reflection` |
| `ShaderNodeNewGeometry` | - | `Position, Normal, Tangent, True Normal, Incoming, Parametric, Backfacing, Pointiness, Random Per Island` |
| `ShaderNodeVectorTransform` | `Vector` | `Vector` |
| `ShaderNodeSeparateXYZ` | `Vector` | `X, Y, Z` |
| `ShaderNodeCombineXYZ` | `X, Y, Z` | `Vector` |
| `ShaderNodeVectorMath` | `Vector, Vector, Vector, Scale` | `Vector, Value` |
| `ShaderNodeMapping` | `Vector, Location, Rotation, Scale` | `Vector` |
| `ShaderNodeTexImage` | `Vector` | `Color, Alpha` |
| `ShaderNodeEmission` | `Color, Strength, Weight` | `Emission` |
| `ShaderNodeOutputLight` | `Surface` | - |
| `ShaderNodeMix` | `Factor, Factor, A..., B...` (repeated per type) | `Result` repeated per type |
| `ShaderNodeMath` | `Value, Value, Value` | `Value` |

`ShaderNodeEmission` gained a third input `Weight` in 5.x. Leave it at default.

Enum values in use:

- `ShaderNodeVectorMath.operation`: `'DIVIDE'` (full list includes `MULTIPLY_ADD`,
  `WRAP`, `SNAP`, `POWER`, ...).
- `ShaderNodeMapping.vector_type`: `'POINT'` (also `TEXTURE`, `VECTOR`, `NORMAL`).
- `ShaderNodeTexImage.extension`: `'CLIP'` (also `REPEAT`, `EXTEND`, `MIRROR`).
- `ShaderNodeTexImage.interpolation`: `'Closest'` or `'Linear'` (also `Cubic`, `Smart`).

`ShaderNodeMix` and `ShaderNodeVectorMath` expose several inputs with identical names
(`A`/`B` repeat once per socket type). Name lookup returns the first match, so access these
by index. For `ShaderNodeMix` with RGBA sockets, `Factor` is index 0 and the RGBA `A`/`B`
are indices 6 and 7.

### Two candidate projection chains

1. `TexCoord.Normal` -> `SeparateXYZ` -> divide X and Y by Z -> `Mapping` -> `Image Texture`.
   Used by dragly.org (2020) and by older versions of the `Ocupe/Projectors` add-on.
2. `Geometry.Incoming` -> `Vector Transform` -> divide X and Y by Z -> `Mapping` ->
   `Image Texture`. Used by `Ocupe/Projectors` from Blender 4.0 onwards.

Both divide the direction vector by its Z component, which converts the unit-sphere normal
into the equivalent image-plane coordinate. The sign and axis conventions of each chain are
**not documented**; the verification script must decide which chain reproduces the pinhole
model, using the reprojection criterion below rather than visual inspection.

## Camera intrinsics

Verified relations with `sensor_fit = 'HORIZONTAL'` (measured through
`camera.view_frame(scene=scene)` at 1280x720):

```
fx = W * lens / sensor_width          # 1280 * 50 / 36 = 1777.78 -> observed 1777.8
cx = W * (0.5 - shift_x)              # shift_x = +0.1 -> cx = 512
cy = H * 0.5 + shift_y * W            # shift_y = +0.1 -> cy = 488
```

`shift_y` is expressed in units of the **image width**, not the height. Computing it from
the height introduces an error equal to the aspect ratio.

### Hard limitation: square pixels

`view_frame` was sampled with `sensor_fit` in `HORIZONTAL`, `VERTICAL`, `AUTO` and with
mismatched `sensor_width` / `sensor_height`. In every case the returned frame aspect equals
the render resolution aspect (0.5625 for 1280x720), and the horizontal and vertical field of
view stay consistent with a single focal length. A Blender perspective camera therefore
always has `fx == fy` in pixel units.

Consequence: the camera side cannot represent a calibration matrix with `fx != fy`. For most
real cameras the difference is below one percent and can be ignored; larger differences
require anisotropic resampling after rendering, which changes the pixel grid. This is a
documented limitation, not an implementation gap.

The projector is not affected, because its intrinsics are defined entirely by the shader
math, so arbitrary `fx`, `fy`, `cx`, `cy` can be encoded there.

`sensor_fit` enum: `AUTO`, `HORIZONTAL`, `VERTICAL`. `lens_unit`: `MILLIMETERS`, `FOV`.
`Camera.type`: `PERSP`, `ORTHO`, `PANO`, `CUSTOM`.

### Authoritative projection function

`bpy_extras.object_utils.world_to_camera_view(scene, obj, coord)` returns normalised device
coordinates where (0, 0) is the bottom-left and (1, 1) the top-right of the frame, with the
third component holding depth along the view axis. Its implementation (read from
`scripts/modules/bpy_extras/object_utils.py` in the local install) uses
`obj.matrix_world.normalized().inverted()` on the point and `camera.view_frame(scene)` for the
frame bounds, so lens shift and sensor size are already included. Use it as the ground truth
when validating the camera side.

## Render and colour management

| Setting | Value | Reason |
|---|---|---|
| `scene.render.engine` | `'CYCLES'` | Only Cycles supports light-node projection |
| `scene.cycles.samples` | configurable, default 4096 | Fringe patterns need many samples |
| `scene.cycles.use_denoising` | configurable, default `True` | Must be disabled for calibration work |
| `scene.cycles.device` | `'CPU'` or `'GPU'` | |
| `scene.view_settings.view_transform` | `'Standard'` | Default is **AgX**, which rolls off highlights and breaks fringe linearity |
| `scene.view_settings.look` | `'None'` | |
| `scene.render.image_settings.file_format` | `'PNG'` | Enum also offers `OPEN_EXR`, `TIFF`, `BMP`, ... |
| `scene.render.film_transparent` | configurable | |
| `image.colorspace_settings.name` | `'Non-Color'` for patterns | Prevents a second sRGB transfer |

Enumeration caveats, both observed in `--factory-startup`:

- `RenderSettings.engine` enumerated only `['BLENDER_EEVEE']`, yet assigning `'CYCLES'`
  succeeds and Cycles renders. Do not validate engine availability by reading the enum.
- `view_transform` and `display_device` enumerated only `['NONE']`, yet the live value is
  `'AgX'` and assigning `'Standard'` succeeds. Same conclusion.

In background mode `bpy.data.images['Render Result'].pixels` is not reliable. Render with
`write_still=True`, then `bpy.data.images.load()` the written file to read pixels back.

## Image pixels

`image.pixels` is a flat RGBA buffer with **bottom-up row order**, while any coordinate
system you reason in (and what you see on screen) is top-down. Writing an array built
top-down straight into `image.pixels` produces a vertically flipped file. Either flip rows
before assigning, or read back with the same flip.

Observed consequence: a dot pattern written without the flip rendered upside down and made a
measurement disagree by hundreds of pixels until the flip was added.

Also note that reading a rendered PNG back with `bpy.data.images.load()` returns the same
bottom-up order, and index space matches image coordinates directly: no half-pixel offset was
needed when centroid indices were compared against `world_to_camera_view` output. Adding half
a pixel moved the residual by $0.5\sqrt{2}$, so it was removed.

## Maths and CLI

| API | Use |
|---|---|
| `Vector.to_track_quat('-Z', 'Y')` | Turn a direction into a rotation; only valid for a `look_at` direction, not for an up vector |
| `Matrix.Translation(t) @ quat.to_matrix().to_4x4()` | Build `matrix_world` |
| `matrix_world.inverted()` | World to local |
| `obj.matrix_world.normalized().inverted()` | Matches the internal convention of `world_to_camera_view` |
| `sys.argv[sys.argv.index("--") + 1:]` | Arguments after `--` |
| `json`, `pathlib`, `glob` | Config loading, image enumeration |

## Constraints carried into the implementation

1. Camera cannot express `fx != fy`; document it.
2. `shift_y` is in width units; use `W`, not `H`.
3. The default view transform is AgX; set `'Standard'` explicitly.
4. `light.cycles` has no `samples`; sampling is set on the scene.
5. Nodes with repeated socket names must be accessed by index.
6. Node-chain sign conventions are established by the reprojection test, not by inspection.
7. Acceptance for the geometry test: reprojection RMS below 0.1 px against the analytic
   pinhole model, using `world_to_camera_view` on the camera side.

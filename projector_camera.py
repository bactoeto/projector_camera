#!/usr/bin/env python3
"""Project an image sequence onto an object and capture it with a camera.

Headless usage:

    blender -b your_scene.blend -P projector_camera.py -- --config config.json

The projection itself is provided by the bundled copy of the ``Projectors``
add-on (https://github.com/Ocupe/Projectors, GPL-3.0-or-later).  This script
only moves numbers from the configuration into that add-on and Blender's
camera, then loops over views and patterns.
"""

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".exr"}

PROJECTOR_NAME = "Projector"
CAMERA_NAME = "SimCamera"

# Blender cameras look down -Z with +Y up; OpenCV looks down +Z with +Y down.
FLIP_TO_OPENCV = Matrix.Diagonal((1.0, -1.0, -1.0))


def fail(message):
    print("error: " + message, file=sys.stderr)
    sys.exit(2)


def parse_args():
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    config = "config.json"
    i = 0
    while i < len(args):
        if args[i] in ("--config", "-c"):
            if i + 1 >= len(args):
                fail("--config needs a path")
            config = args[i + 1]
            i += 2
        else:
            fail("unknown argument: " + args[i])
    return Path(config)


def load_config(path):
    if not path.is_file():
        fail("configuration not found: %s" % path)
    with open(path, "r", encoding="utf-8") as handle:
        config = json.load(handle)

    base = path.resolve().parent

    def resolve(value):
        return value if Path(value).is_absolute() else str((base / value).resolve())

    if "output_dir" not in config:
        config["output_dir"] = "./output"
    config["output_dir"] = resolve(config["output_dir"])

    # A top-level patterns entry is the default; a view may override it, so it
    # is only required when no view supplies its own.
    if config.get("patterns") is not None:
        config["patterns"] = resolve(config["patterns"])
    for view in config.get("views") or []:
        if view.get("patterns") is not None:
            view["patterns"] = resolve(view["patterns"])
    return config


def addon_is_registered():
    """True when the Projectors add-on has registered its property group.

    ``hasattr(bpy.ops, "projector")`` is not usable here: accessing an
    operator namespace never raises, so it reports True even when the add-on
    is absent.
    """
    return hasattr(bpy.types, "ProjectorSettings")


def ensure_addon(config, script_dir):
    """Register the bundled Projectors add-on unless it is already installed."""
    if addon_is_registered():
        return
    path = Path(config.get("projector_addon_path") or (script_dir / "vendor" / "Projectors"))
    if not path.is_dir():
        fail("Projectors add-on not found at %s" % path)

    sys.path.insert(0, str(path.parent))
    try:
        module = __import__(path.name)
        module.register()
    except Exception as error:  # noqa: BLE001 - surfaced to the user instead
        fail("could not register the Projectors add-on: %s" % error)


def aim(obj, location, look_at):
    obj.location = Vector(location)
    direction = Vector(look_at) - Vector(location)
    if direction.length < 1e-6:
        fail("look_at is identical to the location of %s" % obj.name)
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = direction.to_track_quat("-Z", "Y")


def ensure_camera(name):
    obj = bpy.data.objects.get(name)
    if obj is not None and obj.type == "CAMERA":
        return obj
    data = bpy.data.cameras.new(name)
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def ensure_projector():
    obj = bpy.data.objects.get(PROJECTOR_NAME)
    if obj is not None and obj.type == "CAMERA" and obj.children:
        return obj

    for stale in [item for item in bpy.data.objects if item.name.startswith(PROJECTOR_NAME)]:
        bpy.data.objects.remove(stale, do_unlink=True)

    bpy.ops.projector.create()
    obj = bpy.context.object
    obj.name = PROJECTOR_NAME
    return obj


def select_only(obj):
    for other in bpy.context.view_layer.objects:
        other.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def apply_projector_settings(projector, settings):
    """Pass configuration straight into the add-on's own properties.

    Order matters. ``projected_texture`` decides whether the resolution setting
    is honoured at all, and ``use_custom_texture_res`` decides whether the
    resolution comes from the dropdown or from the pattern file. Both are set
    before the resolution and the throw ratio, because the add-on recomputes the
    projection mapping from whatever the current state is.
    """
    select_only(projector)
    props = projector.proj_settings
    props.projected_texture = "custom_texture"

    # Order matters. ``projected_texture`` decides whether the resolution setting
    # is honoured at all, and ``use_custom_texture_res`` decides whether the
    # resolution comes from the dropdown or from the pattern file. Both are set
    # before the resolution and the throw ratio, because the add-on recomputes the
    # projection mapping from whatever the current state is.
    props.use_custom_texture_res = bool(settings.get("use_custom_texture_res", True))

    if not props.use_custom_texture_res:
        resolution = settings.get("resolution", "1920x1080")
        try:
            props.resolution = resolution
        except TypeError:
            fail(
                "unknown projector resolution %r; set use_custom_texture_res to true "
                "to follow the pattern file instead" % (resolution,)
            )

    props.throw_ratio = float(settings.get("throw_ratio", 1.5))
    props.power = float(settings.get("power", 1000.0))
    props.h_shift = float(settings.get("h_shift", 0.0))
    props.v_shift = float(settings.get("v_shift", 0.0))
    props.show_pixel_grid = bool(settings.get("show_pixel_grid", False))


def projector_texture_node(projector):
    tree = projector.children[0].data.node_tree
    for node in tree.nodes:
        if node.bl_idname == "ShaderNodeTexImage":
            return node
    fail("the projector node tree has no Image Texture node")


def apply_camera_settings(camera, settings, scene):
    data = camera.data
    data.type = "PERSP"
    data.sensor_fit = "HORIZONTAL"
    data.lens_unit = "MILLIMETERS"
    data.sensor_width = float(settings.get("sensor_width", 36.0))
    data.lens = float(settings.get("lens", 35.0))
    data.shift_x = float(settings.get("shift_x", 0.0))
    data.shift_y = float(settings.get("shift_y", 0.0))
    data.clip_start = float(settings.get("clip_start", 0.1))
    data.clip_end = float(settings.get("clip_end", 100.0))

    dof = settings.get("dof", {})
    data.dof.use_dof = bool(dof.get("enable", False))
    data.dof.aperture_fstop = float(dof.get("fstop", 2.8))
    data.dof.focus_distance = float(dof.get("focus_distance", 2.2))

    scene.render.resolution_x = int(settings.get("width", 1280))
    scene.render.resolution_y = int(settings.get("height", 720))
    scene.render.resolution_percentage = 100
    scene.camera = camera


def prepare_scene(config, projector):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"

    render = config.get("render", {})
    scene.cycles.samples = int(render.get("samples", 64))
    scene.cycles.use_denoising = bool(render.get("denoise", False))
    scene.cycles.device = render.get("device", "CPU")
    scene.view_settings.exposure = float(render.get("exposure", 0.0))

    lighting = config.get("lighting", {})
    if lighting.get("disable_existing_lights", True):
        keep = {child.name for child in projector.children}
        for obj in bpy.data.objects:
            if obj.type == "LIGHT" and obj.name not in keep:
                obj.hide_render = True

    if scene.world is not None:
        background = next(
            (node for node in scene.world.node_tree.nodes
             if node.bl_idname == "ShaderNodeBackground"),
            None,
        )
        if background is not None:
            background.inputs["Strength"].default_value = float(
                lighting.get("world_strength", 0.0)
            )
    return scene


def intrinsics_of(camera, width, height):
    """Pinhole intrinsics of a Blender camera, in pixels.

    ``angle_x`` is used rather than lens and sensor width because the add-on
    configures the projector's helper camera through the field of view.
    """
    data = camera.data
    fx = (width * 0.5) / math.tan(data.angle_x * 0.5)
    cx = width * (0.5 - data.shift_x)
    cy = height * 0.5 + data.shift_y * width
    return {
        "width": int(width),
        "height": int(height),
        "K": [[fx, 0.0, cx], [0.0, fx, cy], [0.0, 0.0, 1.0]],
    }


def extrinsics_of(obj):
    """World-to-camera rotation and translation in the OpenCV convention."""
    matrix = obj.matrix_world
    rotation = matrix.to_3x3()
    translation = matrix.translation
    rotation = FLIP_TO_OPENCV @ rotation.transposed()
    translation = -(rotation @ translation)
    return (
        [[rotation[i][j] for j in range(3)] for i in range(3)],
        [translation.x, translation.y, translation.z],
    )


def projector_grid(props, patterns):
    """Pixel grid of the projector: either its preset or the pattern's own size."""
    if not props.use_custom_texture_res:
        try:
            width, height = props.resolution.split("x")
        except ValueError:
            fail("projector resolution must look like 1920x1080")
        return int(width), int(height)

    sizes = set()
    for pattern in patterns:
        image = bpy.data.images.load(str(pattern), check_existing=True)
        sizes.add(tuple(image.size))
    if len(sizes) > 1:
        print(
            "warning: patterns differ in size %s; the projector pixel grid follows "
            "the first one. Set use_custom_texture_res to false for a fixed grid."
            % sorted(sizes)
        )
    first = bpy.data.images.load(str(patterns[0]), check_existing=True)
    return int(first.size[0]), int(first.size[1])


def collect_patterns(path):
    target = Path(path)
    if target.is_file():
        if target.suffix.lower() not in IMAGE_EXTENSIONS:
            fail("unsupported image format: %s" % target)
        return [target]
    if not target.is_dir():
        fail("patterns path is neither a file nor a directory: %s" % target)
    patterns = sorted(
        item for item in target.iterdir()
        if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not patterns:
        fail("no images found in %s" % target)
    return patterns


def load_pattern(path, colorspace):
    image = bpy.data.images.load(str(path), check_existing=False)
    image.colorspace_settings.name = colorspace
    return image


def check_version(version=None):
    """Refuse to run on a Blender older than the add-on supports."""
    if version is None:
        version = bpy.app.version
    if version < (4, 2, 0):
        fail(
            "Blender %d.%d.%d is too old; this tool needs 4.2 or newer"
            % version[:3]
        )


def main():
    check_version()
    config_path = parse_args()
    config = load_config(config_path)
    ensure_addon(config, Path(__file__).resolve().parent)

    colorspace = config.get("pattern_colorspace", "sRGB")
    default_patterns = None
    if config.get("patterns") is not None:
        default_patterns = collect_patterns(config["patterns"])
    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    views = config.get("views") or []
    if not views:
        fail("configuration has no views")

    camera = ensure_camera(CAMERA_NAME)
    projector = ensure_projector()
    texture_node = projector_texture_node(projector)
    scene = prepare_scene(config, projector)

    warnings = []
    projector_settings = config.get("projector", {})
    if float(projector_settings.get("h_shift", 0.0)) or float(projector_settings.get("v_shift", 0.0)):
        warnings.append(
            "projector h_shift/v_shift is non-zero; the mapping from lens shift "
            "percentage to principal point has not been measured"
        )

    total = 0
    poses = []
    for index, view in enumerate(views):
        name = view.get("name") or "view_%02d" % index
        if view.get("patterns") is not None:
            view_patterns = collect_patterns(view["patterns"])
        elif default_patterns is not None:
            view_patterns = default_patterns
        else:
            fail(
                "view %r has no 'patterns' and the configuration has no default "
                "'patterns'" % name
            )

        for role in ("camera", "projector"):
            pose = view.get(role)
            if (not isinstance(pose, dict)
                    or "location" not in pose
                    or "look_at" not in pose):
                fail(
                    "view %r needs '%s.location' and '%s.look_at'"
                    % (name, role, role)
                )

        aim(camera, view["camera"]["location"], view["camera"]["look_at"])
        aim(projector, view["projector"]["location"], view["projector"]["look_at"])

        intrinsics = dict(config.get("camera", {}))
        intrinsics.update(view.get("camera", {}).get("intrinsics", {}))
        apply_camera_settings(camera, intrinsics, scene)

        for pattern in view_patterns:
            texture_node.image = load_pattern(pattern, colorspace)
            texture_node.extension = "CLIP"
            # Re-apply so the projection mapping follows this image's aspect ratio.
            apply_projector_settings(projector, projector_settings)

            # Flat layout: the view name is part of the file name, so every
            # image sits in one directory and sorts by view.
            target = output_dir / ("%s__%s.png" % (name, pattern.stem))
            scene.render.filepath = str(target)
            bpy.ops.render.render(write_still=True)
            total += 1
            print("[%d] %s -> %s" % (total, pattern.name, target))

        camera_entry = intrinsics_of(
            camera, scene.render.resolution_x, scene.render.resolution_y
        )
        camera_entry["R"], camera_entry["t"] = extrinsics_of(camera)

        projector_width, projector_height = projector_grid(
            projector.proj_settings, view_patterns
        )
        projector_entry = intrinsics_of(projector, projector_width, projector_height)
        projector_entry["R"], projector_entry["t"] = extrinsics_of(projector)

        poses.append(
            {"name": name, "camera": camera_entry, "projector": projector_entry}
        )

    calibration = {
        "convention": {
            "space": "opencv",
            "description": "world to camera; x right, y down, z forward",
            "units": "metres",
        },
        "models": {
            "camera": "ideal pinhole, no distortion",
            "projector": "ideal pinhole, no distortion, no defocus",
        },
        "warnings": warnings,
        "views": poses,
    }
    calibration_path = output_dir / "calibration.json"
    calibration_path.write_text(json.dumps(calibration, indent=2) + "\n", encoding="utf-8")

    print("done: %d images written to %s" % (total, output_dir))
    print("poses written to %s" % calibration_path)



if __name__ == "__main__":
    main()

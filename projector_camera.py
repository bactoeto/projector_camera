#!/usr/bin/env python3
"""Project an image sequence onto an object and capture it with a camera.

Headless usage:

    blender -b scene.blend -P projector_camera.py -- --config config.json

The projection itself is provided by the bundled copy of the ``Projectors``
add-on (https://github.com/Ocupe/Projectors, GPL-3.0-or-later).  This script
only moves numbers from the configuration into that add-on and Blender's
camera, then loops over views and patterns.
"""

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".exr"}

PROJECTOR_NAME = "Projector"
CAMERA_NAME = "SimCamera"


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
    for key in ("patterns", "output_dir"):
        value = config.get(key)
        if value is None:
            fail("configuration is missing '%s'" % key)
        if not Path(value).is_absolute():
            config[key] = str((base / value).resolve())
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

    if "use_custom_texture_res" in settings:
        props.use_custom_texture_res = bool(settings["use_custom_texture_res"])

    if "resolution" in settings and not props.use_custom_texture_res:
        try:
            props.resolution = settings["resolution"]
        except TypeError:
            fail(
                "unknown projector resolution %r; set use_custom_texture_res to true "
                "to follow the pattern file instead" % settings["resolution"]
            )

    if "throw_ratio" in settings:
        props.throw_ratio = float(settings["throw_ratio"])
    if "power" in settings:
        props.power = float(settings["power"])
    if "h_shift" in settings:
        props.h_shift = float(settings["h_shift"])
    if "v_shift" in settings:
        props.v_shift = float(settings["v_shift"])
    if "show_pixel_grid" in settings:
        props.show_pixel_grid = bool(settings["show_pixel_grid"])


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
    if "sensor_width" in settings:
        data.sensor_width = float(settings["sensor_width"])
    if "lens" in settings:
        data.lens = float(settings["lens"])
    data.shift_x = float(settings.get("shift_x", 0.0))
    data.shift_y = float(settings.get("shift_y", 0.0))
    data.clip_start = float(settings.get("clip_start", 0.1))
    data.clip_end = float(settings.get("clip_end", 100.0))

    dof = settings.get("dof", {})
    data.dof.use_dof = bool(dof.get("enable", False))
    if "fstop" in dof:
        data.dof.aperture_fstop = float(dof["fstop"])
    if "focus_distance" in dof:
        data.dof.focus_distance = float(dof["focus_distance"])

    scene.render.resolution_x = int(settings["width"])
    scene.render.resolution_y = int(settings["height"])
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
    if "device" in render:
        scene.cycles.device = render["device"]
    scene.view_settings.exposure = float(render.get("exposure", 0.0))

    lighting = config.get("lighting", {})
    if lighting.get("disable_existing_lights", True):
        keep = {child.name for child in projector.children}
        for obj in bpy.data.objects:
            if obj.type == "LIGHT" and obj.name not in keep:
                obj.hide_render = True

    if "world_strength" in lighting and scene.world is not None:
        background = next(
            (node for node in scene.world.node_tree.nodes
             if node.bl_idname == "ShaderNodeBackground"),
            None,
        )
        if background is not None:
            background.inputs["Strength"].default_value = float(lighting["world_strength"])
    return scene


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


def main():
    config_path = parse_args()
    config = load_config(config_path)
    ensure_addon(config, Path(__file__).resolve().parent)

    colorspace = config.get("pattern_colorspace", "sRGB")
    patterns = collect_patterns(config["patterns"])
    output_dir = Path(config["output_dir"])
    views = config.get("views") or []
    if not views:
        fail("configuration has no views")

    camera = ensure_camera(CAMERA_NAME)
    projector = ensure_projector()
    texture_node = projector_texture_node(projector)
    scene = prepare_scene(config, projector)

    total = 0
    for index, view in enumerate(views):
        name = view.get("name") or "view_%02d" % index
        aim(camera, view["camera"]["location"], view["camera"]["look_at"])
        aim(projector, view["projector"]["location"], view["projector"]["look_at"])

        intrinsics = dict(config.get("camera", {}))
        intrinsics.update(view.get("camera", {}).get("intrinsics", {}))
        apply_camera_settings(camera, intrinsics, scene)

        view_dir = output_dir / name
        view_dir.mkdir(parents=True, exist_ok=True)

        for pattern in patterns:
            texture_node.image = load_pattern(pattern, colorspace)
            texture_node.extension = "CLIP"
            # Re-apply so the projection mapping follows this image's aspect ratio.
            apply_projector_settings(projector, config.get("projector", {}))

            target = view_dir / (pattern.stem + ".png")
            scene.render.filepath = str(target)
            bpy.ops.render.render(write_still=True)
            total += 1
            print("[%d] %s -> %s" % (total, pattern.name, target))

    print("done: %d images written to %s" % (total, output_dir))


if __name__ == "__main__":
    main()

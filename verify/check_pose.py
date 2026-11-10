#!/usr/bin/env python3
"""Check calibration.json against Blender's own projection.

Run this outside the capture path, after a capture has produced a
calibration.json:

    blender -b scene.blend -P verify/check_pose.py -- --config config.json

For every view it rebuilds the camera and projector poses, projects nine
points with the K, R and t written in calibration.json, and compares the
result with Blender's own world_to_camera_view().  A disagreement larger
than TOLERANCE_PX means the exported numbers do not describe the scene,
so nothing downstream can trust them.

Exits 1 on disagreement, 2 on bad setup.
"""

import json
import math
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import projector_camera as pc  # noqa: E402 - needs the path set first

TOLERANCE_PX = 0.5
POINTS = [
    (local_x, local_y)
    for local_x in (-0.35, 0.0, 0.35)
    for local_y in (-0.2, 0.0, 0.2)
]


def fail(message):
    print("error: " + message, file=sys.stderr)
    sys.exit(2)


def parse_args():
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    if len(args) != 2 or args[0] != "--config":
        fail("usage: --config <config.json>")
    return Path(args[1])


def model_pixel(entry, point):
    """Where the exported model puts a world point."""
    k, r, t = entry["K"], entry["R"], entry["t"]
    camera = [sum(r[i][j] * point[j] for j in range(3)) + t[i] for i in range(3)]
    if camera[2] <= 1e-9:
        return None
    return (
        k[0][0] * camera[0] / camera[2] + k[0][2],
        k[1][1] * camera[1] / camera[2] + k[1][2],
    )


def reference_pixel(scene, obj, point, width, height):
    """Where Blender puts the same point, in pixels from the top left."""
    co = world_to_camera_view(scene, obj, point)
    return co.x * width, (1.0 - co.y) * height


def check_role(scene, obj, role, view, entry, config):
    pose = view[role]
    pc.aim(obj, pose["location"], pose["look_at"])

    if role == "camera":
        intrinsics = dict(config.get("camera", {}))
        intrinsics.update(pose.get("intrinsics", {}))
        pc.apply_camera_settings(obj, intrinsics, scene)
    else:
        pc.apply_projector_settings(obj, config.get("projector", {}))

    # Transforms set above only reach matrix_world after a dependency update;
    # without one, world_to_camera_view would use the previous pose.
    bpy.context.view_layer.update()

    # world_to_camera_view takes the frame aspect from the render resolution,
    # not from the camera, so match the pixel grid this entry describes.
    width, height = entry["width"], entry["height"]
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100

    squared = []
    for local_x, local_y in POINTS:
        world = obj.matrix_world @ Vector((local_x, local_y, -2.0))
        predicted = model_pixel(entry, world)
        if predicted is None:
            fail("%s point falls behind the camera" % role)
        measured = reference_pixel(scene, obj, world, width, height)
        squared.append(
            (predicted[0] - measured[0]) ** 2 + (predicted[1] - measured[1]) ** 2
        )
    return math.sqrt(sum(squared) / len(squared))


def main():
    config_path = parse_args()
    config = pc.load_config(config_path)

    calibration_path = Path(config["output_dir"]) / "calibration.json"
    if not calibration_path.is_file():
        fail("%s not found; run the capture first" % calibration_path)
    with open(calibration_path, "r", encoding="utf-8") as handle:
        calibration = json.load(handle)

    pc.check_version()
    pc.ensure_addon(config, REPO)

    camera = pc.ensure_camera(pc.CAMERA_NAME)
    projector = pc.ensure_projector()
    scene = bpy.context.scene

    views = config.get("views") or []
    saved_views = calibration.get("views") or []
    if len(views) != len(saved_views):
        fail(
            "configuration has %d views but calibration.json has %d"
            % (len(views), len(saved_views))
        )

    worst = 0.0
    for view, saved in zip(views, saved_views):
        for role, obj in (("camera", camera), ("projector", projector)):
            if role not in view:
                fail("view %r has no '%s' section" % (saved.get("name"), role))
            rms = check_role(scene, obj, role, view, saved[role], config)
            worst = max(worst, rms)
            print("%-10s %-9s rms %.6f px" % (saved["name"], role, rms))

    verdict = "PASS" if worst <= TOLERANCE_PX else "FAIL"
    print("worst %.6f px, tolerance %.1f px -> %s" % (worst, TOLERANCE_PX, verdict))
    if worst > TOLERANCE_PX:
        sys.exit(1)


if __name__ == "__main__":
    main()

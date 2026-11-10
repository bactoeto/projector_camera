#!/usr/bin/env python3
"""Check that the projector's light shader matches the pose exported for it.

The export in projector_camera.py derives the projector's intrinsics and
extrinsics from the add-on's helper camera.  Nothing proves the spot light's
shader places the pattern where that camera says it should.  This script
measures it:

  1. project a dot pattern onto a plane whose position is known
  2. find the dots in the rendered image, sub-pixel
  3. for each dot, turn its pattern pixel into a ray, hit the plane, project
     that 3D point through the exported camera model
  4. compare predicted and measured pixel positions

Usage:

    blender -b --python verify_dots.py -- --make-pattern verify/config.json
    blender -b scene.blend -P projector_camera.py -- --config verify/config.json
    blender -b --python verify_dots.py -- --measure verify/config.json

Exits non-zero when the maximum deviation exceeds the tolerance.
"""

import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np

TOLERANCE_PX = 1.0
CENTERED_TOLERANCE_PX = 0.2


def fail(message):
    print("error: " + message, file=sys.stderr)
    sys.exit(2)


def parse_args():
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    if not args:
        fail("usage: --make-pattern <config> | --measure <config>")
    mode = args[0]
    if mode not in ("--make-pattern", "--measure") or len(args) < 2:
        fail("usage: --make-pattern <config> | --measure <config>")
    return mode, Path(args[1])


def load_config(path):
    with open(path, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    base = path.resolve().parent
    for key in ("patterns", "output_dir"):
        value = config.get(key)
        if value and not Path(value).is_absolute():
            config[key] = str((base / value).resolve())
    return config


def check_settings(config):
    settings = config.get("verify") or {}
    dots = settings.get("dots")
    if not dots:
        fail("verify.dots is missing: a list of [u, v] pattern pixels")
    if "plane_z" not in settings:
        fail("verify.plane_z is missing: the z of the plane the dots land on")
    return settings


def make_pattern(config, settings):
    pattern_path = Path(config["patterns"])
    pattern_path.parent.mkdir(parents=True, exist_ok=True)

    width = int(config.get("verify", {}).get("pattern_width", 512))
    height = int(config.get("verify", {}).get("pattern_height", 512))
    radius = int(settings.get("dot_radius", 6))

    rgba = np.zeros((height, width, 4), dtype=np.float32)
    rgba[:, :, 3] = 1.0

    yy, xx = np.ogrid[:height, :width]
    for u, v in settings["dots"]:
        mask = (xx - u) ** 2 + (yy - v) ** 2 <= radius ** 2
        rgba[mask, :3] = 1.0

    image = bpy.data.images.new("verify_dots", width, height, alpha=False)
    # Blender's pixel buffer is bottom-up while the coordinates above are
    # top-down, so the array has to be flipped before it is handed over.
    image.pixels = rgba[::-1].ravel()
    image.filepath_raw = str(pattern_path)
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)
    print("pattern written to %s (%dx%d, %d dots)" % (
        pattern_path, width, height, len(settings["dots"])))


def load_luminance(path):
    image = bpy.data.images.load(str(path), check_existing=False)
    width, height = image.size
    pixels = np.array(image.pixels[:], dtype=np.float32).reshape(height, width, 4)
    # Blender stores rows bottom-up; flip so row 0 is the top of the image.
    return pixels[::-1, :, :3].mean(axis=2)


def box_blur(image, radius):
    """Mean filter with an integral image; no scipy available inside Blender."""
    k = 2 * radius + 1
    padded = np.pad(image.astype(np.float64), radius, mode="edge")
    integral = np.zeros((padded.shape[0] + 1, padded.shape[1] + 1), dtype=np.float64)
    integral[1:, 1:] = padded.cumsum(axis=0).cumsum(axis=1)
    height, width = image.shape
    total = (integral[k:k + height, k:k + width]
             - integral[0:height, k:k + width]
             - integral[k:k + height, 0:width]
             + integral[0:height, 0:width])
    return total / float(k * k)


def flat_field(luminance, radius=24):
    """Divide by a blurred copy so the illumination gradient stops biasing centroids."""
    background = box_blur(luminance, radius)
    return luminance / np.maximum(background, 1e-4)


def find_dots(luminance, count):
    """Locate bright blobs by repeated peak picking plus a weighted centroid."""
    background = box_blur(luminance, 24)
    normalized = luminance / np.maximum(background, 1e-4)
    # Outside the lit area the background is almost black, so the division blows
    # up noise into fake peaks. Ignore those pixels.
    valid = background > 0.1 * float(background.max())
    work = np.where(valid, normalized, 0.0)

    height, width = work.shape
    margin = 24
    work[:margin, :] = 0.0
    work[-margin:, :] = 0.0
    work[:, :margin] = 0.0
    work[:, -margin:] = 0.0

    threshold = max(1.25, 1.0 + 0.4 * (float(work.max()) - 1.0))
    found = []
    radius = 48
    for _ in range(count):
        peak = np.unravel_index(int(np.argmax(work)), work.shape)
        if work[peak] < threshold:
            break
        y0, x0 = int(peak[0]), int(peak[1])
        top, bottom = max(0, y0 - radius), min(height, y0 + radius + 1)
        left, right = max(0, x0 - radius), min(width, x0 + radius + 1)
        if top == 0 or left == 0 or bottom == height or right == width:
            fail("a dot near pixel (%.0f, %.0f) is too close to the image border to "
                 "measure reliably. Move the framing so every dot is well inside."
                 % (x0, y0))
        window = work[top:bottom, left:right]
        mask = window >= max(threshold, float(window.max()) * 0.6)
        weights = np.where(mask, np.clip(window - 1.0, 0.0, None), 0.0)
        total = float(weights.sum())
        if total <= 0.0:
            break
        ys, xs = np.mgrid[top:bottom, left:right]
        found.append((float((xs * weights).sum() / total),
                      float((ys * weights).sum() / total)))
        work[top:bottom, left:right] = 0.0
    return found


def rotate(rotation, vector):
    return [sum(rotation[i][j] * vector[j] for j in range(3)) for i in range(3)]


def intersect_plane(entry, u, v, plane_z, bounds=None):
    """Ray through a projector pixel, met with the plane z = plane_z."""
    k = entry["K"]
    fx, cx = k[0][0], k[0][2]
    fy, cy = k[1][1], k[1][2]
    direction_camera = [(u - cx) / fx, (v - cy) / fy, 1.0]

    rotation, translation = entry["R"], entry["t"]
    direction_world = rotate([[rotation[j][i] for j in range(3)] for i in range(3)],
                             direction_camera)
    origin = rotate([[rotation[j][i] for j in range(3)] for i in range(3)],
                    [-value for value in translation])

    if abs(direction_world[2]) < 1e-9:
        return None
    scale = (plane_z - origin[2]) / direction_world[2]
    if scale <= 0.0:
        return None
    point = [origin[i] + scale * direction_world[i] for i in range(3)]

    if bounds is not None:
        min_x, max_x, min_y, max_y = bounds
        if not (min_x <= point[0] <= max_x and min_y <= point[1] <= max_y):
            return None
    return point


def project(entry, point):
    k = entry["K"]
    fx, cx = k[0][0], k[0][2]
    fy, cy = k[1][1], k[1][2]
    rotation, translation = entry["R"], entry["t"]
    camera_point = [rotate(rotation, point)[i] + translation[i] for i in range(3)]
    if camera_point[2] <= 1e-9:
        return None
    return (fx * camera_point[0] / camera_point[2] + cx,
            fy * camera_point[1] / camera_point[2] + cy)


def match(predicted, measured):
    """Pair predicted positions with measured blobs by nearest neighbour.

    ``find_dots`` returns blobs in brightness order, which has nothing to do
    with the order of the dots in the pattern, so the pairing has to be
    recovered.  The dot layout is deliberately asymmetric, so a mirrored or
    rotated mapping cannot quietly pair up with a small residual.
    """
    candidates = []
    for i, first in enumerate(predicted):
        for j, second in enumerate(measured):
            distance = math.hypot(first[0] - second[0], first[1] - second[1])
            candidates.append((distance, i, j))
    candidates.sort()

    used_predicted, used_measured, pairs = set(), set(), []
    for distance, i, j in candidates:
        if i in used_predicted or j in used_measured:
            continue
        used_predicted.add(i)
        used_measured.add(j)
        pairs.append((i, j))
        if len(pairs) == len(predicted):
            break
    pairs.sort()
    return pairs


def measure(config, settings):
    calibration_path = Path(config["output_dir"]) / "calibration.json"
    if not calibration_path.is_file():
        fail("calibration.json not found at %s; run projector_camera.py first"
             % calibration_path)
    with open(calibration_path, "r", encoding="utf-8") as handle:
        calibration = json.load(handle)

    view = calibration["views"][0]
    view_name = view["name"]
    images = sorted(Path(config["output_dir"]).glob(view_name + "__*.png"))
    if not images:
        fail("no rendered image matching %s__*.png in %s"
             % (view_name, config["output_dir"]))

    luminance = load_luminance(images[0])
    dots = settings["dots"]
    centroids = find_dots(luminance, len(dots))
    if len(centroids) != len(dots):
        fail("found %d dots in %s, expected %d"
             % (len(centroids), images[0].name, len(dots)))

    projector = view["projector"]
    camera = view["camera"]
    plane_z = float(settings["plane_z"])
    bounds = settings.get("plane_bounds")
    if bounds is not None:
        bounds = [float(value) for value in bounds]

    records = []
    predicted_positions = []
    for u, v in dots:
        point = intersect_plane(projector, u, v, plane_z, bounds)
        if point is None:
            fail("dot at pattern (%s, %s) misses the plane or lands outside its "
                 "bounds; the framing projects past the surface" % (u, v))
        predicted = project(camera, point)
        if predicted is None:
            fail("dot at pattern (%s, %s) lands behind the camera" % (u, v))
        predicted_positions.append(predicted)

    for index, (u, v) in enumerate(dots):
        point = intersect_plane(projector, u, v, plane_z)
        predicted = predicted_positions[index]
        records.append({
            "pattern_px": [float(u), float(v)],
            "world": [round(value, 6) for value in point],
            "predicted_px": [round(predicted[0], 3), round(predicted[1], 3)],
        })

    for index, blob in match(predicted_positions, centroids):
        measured_u, measured_v = centroids[blob]
        predicted = predicted_positions[index]
        records[index]["measured_px"] = [round(measured_u, 3), round(measured_v, 3)]
        records[index]["offset_px"] = [
            round(predicted[0] - measured_u, 3),
            round(predicted[1] - measured_v, 3),
        ]

    missing = [record for record in records if "offset_px" not in record]
    if missing:
        fail("%d dot(s) had no matching blob in the render" % len(missing))

    mean_x = sum(record["offset_px"][0] for record in records) / len(records)
    mean_y = sum(record["offset_px"][1] for record in records) / len(records)

    for record in records:
        dx = record["offset_px"][0]
        dy = record["offset_px"][1]
        record["error_px"] = round(math.hypot(dx, dy), 3)
        record["centered_error_px"] = round(math.hypot(dx - mean_x, dy - mean_y), 3)

    worst = max(record["error_px"] for record in records)
    centered_worst = max(record["centered_error_px"] for record in records)
    rms = math.sqrt(sum(record["error_px"] ** 2 for record in records) / len(records))
    centered_rms = math.sqrt(
        sum(record["centered_error_px"] ** 2 for record in records) / len(records))
    passed = worst <= TOLERANCE_PX and centered_worst <= CENTERED_TOLERANCE_PX

    report = {
        "image": str(images[0]),
        "plane_z": plane_z,
        "dot_count": len(records),
        "tolerance_px": TOLERANCE_PX,
        "centered_tolerance_px": CENTERED_TOLERANCE_PX,
        "mean_offset_px": [round(mean_x, 3), round(mean_y, 3)],
        "max_error_px": round(worst, 3),
        "rms_error_px": round(rms, 3),
        "max_centered_error_px": round(centered_worst, 3),
        "rms_centered_error_px": round(centered_rms, 3),
        "passed": passed,
        "dots": records,
    }
    output = Path(config["output_dir"]) / "measurement.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    for record in records:
        print("dot %-14s offset %-20s error %.3f px  centered %.3f px" % (
            record["pattern_px"], record["offset_px"],
            record["error_px"], record["centered_error_px"]))
    print("mean offset (%.3f, %.3f) px" % (mean_x, mean_y))
    print("absolute: max %.3f px, rms %.3f px (limit %.1f)" % (worst, rms, TOLERANCE_PX))
    print("centered: max %.3f px, rms %.3f px (limit %.1f)" % (
        centered_worst, centered_rms, CENTERED_TOLERANCE_PX))
    print("-> %s" % ("PASS" if passed else "FAIL"))
    print("report written to %s" % output)

    if not passed:
        sys.exit(1)


def main():
    mode, path = parse_args()
    config = load_config(path)
    settings = check_settings(config)
    if mode == "--make-pattern":
        make_pattern(config, settings)
    else:
        measure(config, settings)


if __name__ == "__main__":
    main()

#!/usr/bin/env bash
# Run the projector-camera capture headless.
#
#   ./run.sh                        # scene.blend + config.json
#   ./run.sh scene.blend my.json    # explicit scene and configuration
#
# Set BLENDER=/path/to/blender to override the executable.

set -euo pipefail
cd "$(dirname "$0")"

BLENDER="${BLENDER:-blender}"
MIN_VERSION="4.2"

if ! command -v "$BLENDER" >/dev/null 2>&1; then
    cat >&2 <<'EOF'
error: Blender was not found.

Install Blender 4.2 or newer and make sure the "blender" command is on PATH,
or point BLENDER at the executable:

    BLENDER=/opt/blender/blender ./run.sh
EOF
    exit 2
fi

version="$("$BLENDER" --version | head -n1 | sed -E 's/[^0-9]*([0-9]+(\.[0-9]+)*).*/\1/')"
if [ -z "$version" ]; then
    echo "error: could not read the Blender version from 'blender --version'" >&2
    exit 2
fi

if [ "$(printf '%s\n%s\n' "$MIN_VERSION" "$version" | sort -V | head -n1)" != "$MIN_VERSION" ]; then
    cat >&2 <<EOF
error: Blender $version is too old.

This tool needs Blender $MIN_VERSION or newer; scene.blend was saved with 5.2
and cannot be opened by older releases. Projection is done through a light
shader, which only Cycles renders.
EOF
    exit 2
fi

scene="${1:-scene.blend}"
config="${2:-config.json}"

for required in "$scene" "$config"; do
    if [ ! -f "$required" ]; then
        echo "error: $required not found in $(pwd)" >&2
        exit 2
    fi
done

echo "Blender $version, scene=$scene, config=$config"
exec "$BLENDER" -b "$scene" -P projector_camera.py -- --config "$config"

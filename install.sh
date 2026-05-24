#!/bin/bash
set -euo pipefail

echo "Building Upside2 for $(uname -m) architecture..."

# Set up common environment variables
export UPSIDE_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MY_PYTHON="/opt/conda"
export PATH="$MY_PYTHON/bin:$PATH"
export PATH="$UPSIDE_HOME/obj:$PATH"
export PYTHONPATH="$UPSIDE_HOME/py:${PYTHONPATH:-}"
export EIGEN_HOME="/usr/include/eigen3"

# obj/ is gitignored and often absent on fresh checkouts (e.g. rsync excludes it).
mkdir -p "$UPSIDE_HOME/obj"
rm -rf "$UPSIDE_HOME/obj"/*
cd "$UPSIDE_HOME/obj"

# CMake will detect architecture and use appropriate configuration
cmake ../src/ -DEIGEN3_INCLUDE_DIR="$EIGEN_HOME"
make -j"$(nproc 2>/dev/null || echo 2)"

if [[ ! -x "$UPSIDE_HOME/obj/upside" ]]; then
    echo "ERROR: build finished but $UPSIDE_HOME/obj/upside is missing." >&2
    exit 1
fi

echo "Build complete!"

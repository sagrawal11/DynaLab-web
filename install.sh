#!/bin/bash
set -euo pipefail

# UPSIDE_BUILD_TYPE: "release" (default) -> -O3 --fast-math, no -pg
#                   "debug"              -> -Og -g -pg (for profiling only; ~5-10x slower)
UPSIDE_BUILD_TYPE="${UPSIDE_BUILD_TYPE:-release}"

case "$UPSIDE_BUILD_TYPE" in
    release) CMAKE_DEBUG_FLAG="OFF" ;;
    debug)   CMAKE_DEBUG_FLAG="ON" ;;
    *)
        echo "ERROR: UPSIDE_BUILD_TYPE must be 'release' or 'debug' (got '$UPSIDE_BUILD_TYPE')." >&2
        exit 1
        ;;
esac

echo "Building Upside2 for $(uname -m) architecture (build_type=${UPSIDE_BUILD_TYPE})..."

export UPSIDE_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MY_PYTHON="/opt/conda"
export PATH="$MY_PYTHON/bin:$PATH"
export PATH="$UPSIDE_HOME/obj:$PATH"
export PYTHONPATH="$UPSIDE_HOME/py:${PYTHONPATH:-}"
export EIGEN_HOME="/usr/include/eigen3"

mkdir -p "$UPSIDE_HOME/obj"
rm -rf "$UPSIDE_HOME/obj"/*
cd "$UPSIDE_HOME/obj"

# IMPORTANT: -DDEBUG=OFF gets us -O3 --fast-math (release). With DEBUG=ON the
# x86 CMakeLists uses -Og -g -pg, which is 5-10x slower for hot MD loops.
cmake ../src/ -DEIGEN3_INCLUDE_DIR="$EIGEN_HOME" -DDEBUG="$CMAKE_DEBUG_FLAG"
make -j"$(nproc 2>/dev/null || echo 2)"

if [[ ! -x "$UPSIDE_HOME/obj/upside" ]]; then
    echo "ERROR: build finished but $UPSIDE_HOME/obj/upside is missing." >&2
    exit 1
fi

# Sanity-check that the binary was actually built release. We look for the
# tell-tale gprof instrumentation symbol; release builds do NOT have it.
if [[ "$UPSIDE_BUILD_TYPE" == "release" ]] && command -v nm >/dev/null 2>&1; then
    if nm -an "$UPSIDE_HOME/obj/upside" 2>/dev/null | grep -q ' mcount\| __gmon_start__'; then
        echo "WARNING: obj/upside appears to contain gprof (-pg) symbols even though release was requested." >&2
        echo "         The matrix will run, but performance will be 5-10x worse than expected." >&2
    fi
fi

echo "Build complete! (build_type=${UPSIDE_BUILD_TYPE})"
ls -lh "$UPSIDE_HOME/obj/upside" "$UPSIDE_HOME/obj/libupside.so" 2>/dev/null || true

# Marker so bootstrap.sh can detect stale debug-mode binaries from a previous run.
echo "$UPSIDE_BUILD_TYPE" > "$UPSIDE_HOME/obj/.upside_build_type"

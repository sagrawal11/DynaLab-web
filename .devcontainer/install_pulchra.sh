#!/usr/bin/env bash
# Build PULCHRA from source.
#
# PULCHRA (PowerfUL CHain Restoration Algorithm) reconstructs all heavy atoms
# from a CA-only protein trace. We use it in Phase 2 of the back-mapping
# pipeline: Upside is a coarse-grained engine, but AI design tools
# (RFdiffusion / ProteinMPNN / AlphaFold-Multimer) need all-atom inputs.
#
# Upstream: https://www.pirx.com/pulchra/
# Mirror used here: https://github.com/euplotes/pulchra (faithful github mirror).
#
# Per the upstream README, the canonical build is a single command:
#
#   cc -O3 -o pulchra pulchra.c pulchra_data.c -lm
#
# There is *no Makefile* in the repository - earlier versions of this script
# called `make pulchra`, which silently fell back to GNU make's implicit
# %: %.c rule and:
#   1. only compiled pulchra.c (skipping pulchra_data.c, which #includes the
#      giant nco_data.h / rot_data_coords.h / rot_data_idx.h tables that
#      define nco_stat, rot_stat_idx, rot_stat_coords, etc.); and
#   2. did not link against libm, so acos/sqrt/atan/sincos were undefined.
# We now invoke gcc directly with both source files and -lm.
#
# We also patch pulchra.c to add `#include <time.h>`. Modern gcc (Debian
# trixie ships gcc 14) treats implicit-function-declaration as an error,
# and pulchra.c uses time(NULL) without including its header. Belt-and-
# suspenders, we also pass -Wno-error=implicit-function-declaration and
# -Wno-deprecated-declarations to silence the deprecated-ftime warnings
# that would otherwise be promoted to errors under -Werror in some envs.
#
# This script is invoked from .devcontainer/Dockerfile during image build.
# It compiles for the host architecture (works on x86_64 and aarch64).
# Idempotent: re-running on an already-patched checkout is a no-op.

set -euo pipefail

PULCHRA_VERSION="307"
PULCHRA_SRC=$(mktemp -d)

apt-get update
apt-get install -y --no-install-recommends \
    build-essential \
    git
# Don't clean apt lists here - the next layer might still need them.

cd "$PULCHRA_SRC"
git clone --depth 1 https://github.com/euplotes/pulchra .

# Add `#include <time.h>` at the top of pulchra.c if not already present.
if ! grep -q '^#include <time.h>' pulchra.c; then
    sed -i '1i#include <time.h>' pulchra.c
fi

CC_BIN="${CC:-gcc}"
CFLAGS_EXTRA="-O3 -Wno-error=implicit-function-declaration -Wno-deprecated-declarations"

echo "Compiling pulchra: ${CC_BIN} ${CFLAGS_EXTRA} -o pulchra pulchra.c pulchra_data.c -lm"
${CC_BIN} ${CFLAGS_EXTRA} -o pulchra pulchra.c pulchra_data.c -lm

install -m 0755 pulchra /usr/local/bin/pulchra

# Sanity check: pulchra prints usage and exits non-zero when given no args,
# so don't propagate its exit status here.
/usr/local/bin/pulchra 2>&1 | head -n 5 || true
echo "PULCHRA installed at /usr/local/bin/pulchra (version ${PULCHRA_VERSION})."

rm -rf "$PULCHRA_SRC"

#!/usr/bin/env bash
# Build mkdssp (PDB-REDO/dssp v4) from source.
#
# Why this script exists:
#   On linux/arm64 (Apple Silicon dev containers, GitHub Codespaces) there
#   is no prebuilt mkdssp binary on apt or bioconda. The only reliable
#   path is to build it from source. This takes ~5-10 minutes once.
#
# Usage:
#   - Inside the running dev container:
#       bash .devcontainer/install_dssp.sh
#   - From the Dockerfile (see Dockerfile for the matching RUN line),
#     so the binary is baked into the image and survives rebuilds.
#
# Installs:
#   /usr/local/bin/mkdssp
#   /usr/local/lib/libcifpp.*
#
# Idempotent: if mkdssp is already on PATH, exits early.

set -euo pipefail

if command -v mkdssp >/dev/null 2>&1; then
    echo "mkdssp already installed at $(command -v mkdssp)"
    mkdssp --version || true
    exit 0
fi

# Use sudo if available (running container) or run directly (Docker build, root)
if command -v sudo >/dev/null 2>&1 && [ "$(id -u)" != "0" ]; then
    SUDO="sudo"
else
    SUDO=""
fi

echo "[1/4] Installing build dependencies via apt..."
$SUDO apt-get update
$SUDO apt-get install -y --no-install-recommends \
    cmake \
    build-essential \
    git \
    ca-certificates \
    libboost-all-dev \
    zlib1g-dev \
    libbz2-dev \
    libsqlite3-dev

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

JOBS=$(nproc 2>/dev/null || echo 2)

echo "[2/4] Building libmcfp (small CLI/config parser used by libcifpp)..."
git clone --depth 1 https://github.com/mhekkel/libmcfp.git "$WORK_DIR/libmcfp"
cmake -S "$WORK_DIR/libmcfp" -B "$WORK_DIR/libmcfp/build" -DCMAKE_BUILD_TYPE=Release
cmake --build "$WORK_DIR/libmcfp/build" --parallel "$JOBS"
$SUDO cmake --install "$WORK_DIR/libmcfp/build"

echo "[3/4] Building libcifpp (mmCIF/PDB parser; the slow step, ~5 min)..."
git clone --depth 1 https://github.com/PDB-REDO/libcifpp.git "$WORK_DIR/libcifpp"
cmake -S "$WORK_DIR/libcifpp" -B "$WORK_DIR/libcifpp/build" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCIFPP_DOWNLOAD_CCD=ON \
    -DCIFPP_INSTALL_UPDATE_SCRIPT=OFF \
    -DCIFPP_BUILD_TESTS=OFF
cmake --build "$WORK_DIR/libcifpp/build" --parallel "$JOBS"
$SUDO cmake --install "$WORK_DIR/libcifpp/build"
$SUDO ldconfig

echo "[4/4] Building dssp (mkdssp itself)..."
git clone --depth 1 https://github.com/PDB-REDO/dssp.git "$WORK_DIR/dssp"
cmake -S "$WORK_DIR/dssp" -B "$WORK_DIR/dssp/build" \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_TESTING=OFF
cmake --build "$WORK_DIR/dssp/build" --parallel "$JOBS"
$SUDO cmake --install "$WORK_DIR/dssp/build"

echo
echo "Done. Verifying..."
mkdssp --version
echo "mkdssp installed at $(command -v mkdssp)"

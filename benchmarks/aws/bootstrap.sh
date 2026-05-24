#!/usr/bin/env bash
# bootstrap.sh — runs ON the EC2 instance to set up Docker, build the dev
# container image, and run the DynaLab benchmark matrix.
#
# Idempotent: re-running picks up where the last run stopped.
#
# Inputs (env vars, all optional):
#   REPO_DIR        path to a DynaLab checkout on the EC2 box (default: $HOME/DynaLab-merge-dynalab)
#   RESULTS_DIR     where to write results on the box (default: $HOME/dynalab_results)
#   IMAGE_TAG       Docker image tag to build (default: dynalab-bench:latest)
#   MATRIX_TIER     which tier from matrix.json to run (default: aws)
#   MATRIX_ARGS     extra args passed to run_matrix.py (e.g. "--only aws_med_const")
#   OMP_THREADS     override OMP_NUM_THREADS for the container (default: $(nproc))
#
# Usage on the EC2 box:
#   cd ~/DynaLab-merge-dynalab
#   bash benchmarks/aws/bootstrap.sh

set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/DynaLab-merge-dynalab}"
RESULTS_DIR="${RESULTS_DIR:-$HOME/dynalab_results}"
IMAGE_TAG="${IMAGE_TAG:-dynalab-bench:latest}"
MATRIX_TIER="${MATRIX_TIER:-aws}"
MATRIX_ARGS="${MATRIX_ARGS:-}"
OMP_THREADS="${OMP_THREADS:-$(nproc)}"

LOG_DIR="$RESULTS_DIR/_logs"
mkdir -p "$RESULTS_DIR" "$LOG_DIR"

log() { echo "[bootstrap $(date -u +%H:%M:%S)] $*"; }

# --- 1. Verify we are on a Linux box with internet --------------------------

log "host info"
uname -a
if ! command -v sudo >/dev/null; then
    echo "ERROR: sudo not available (run on Amazon Linux 2023 or Ubuntu)." >&2
    exit 1
fi

# --- 2. Install Docker + git if missing -------------------------------------

if ! command -v docker >/dev/null; then
    log "installing docker"
    if command -v dnf >/dev/null; then
        sudo dnf install -y docker git rsync awscli
    elif command -v yum >/dev/null; then
        sudo yum install -y docker git rsync awscli
    elif command -v apt-get >/dev/null; then
        sudo apt-get update -y
        sudo apt-get install -y docker.io git rsync awscli
    else
        echo "ERROR: unsupported package manager. Install docker, git, rsync manually." >&2
        exit 1
    fi
else
    log "docker already installed"
fi

sudo systemctl enable --now docker
sudo usermod -aG docker "$USER" || true
# Membership refresh requires re-login, so we use sudo for docker calls below.

# --- 3. Verify the repo is here --------------------------------------------

if [[ ! -d "$REPO_DIR/.devcontainer" ]]; then
    echo "ERROR: $REPO_DIR is not a DynaLab checkout (no .devcontainer/)." >&2
    echo "       Push your local copy with rsync (see launch_ec2.sh output)," >&2
    echo "       or set REPO_DIR=/path/to/your/checkout." >&2
    exit 1
fi
cd "$REPO_DIR"

# --- 4. Build the dev container image (slow first time, fast on rerun) ----

if ! sudo docker image inspect "$IMAGE_TAG" >/dev/null 2>&1; then
    log "building docker image $IMAGE_TAG (15-25 min on c7i.4xlarge)"
    sudo docker build \
        --build-arg TARGETPLATFORM=linux/amd64 \
        --build-arg BUILDPLATFORM=linux/amd64 \
        -f .devcontainer/Dockerfile \
        -t "$IMAGE_TAG" \
        . 2>&1 | tee "$LOG_DIR/docker-build.log"
else
    log "docker image $IMAGE_TAG already present"
fi

# --- 5. Run the matrix inside the container -------------------------------

log "running benchmark matrix (tier=$MATRIX_TIER, OMP_NUM_THREADS=$OMP_THREADS)"

RUN_CMD="set -euo pipefail
cd /workspaces/DynaLab-merge-dynalab
source /opt/conda/etc/profile.d/conda.sh
conda activate upside2-env
export UPSIDE_HOME=/workspaces/DynaLab-merge-dynalab
export PYTHONPATH=\"\$UPSIDE_HOME/py:\$PYTHONPATH\"
export PATH=\"\$UPSIDE_HOME/py:\$UPSIDE_HOME/obj:\$PATH\"

# (Re)build Upside in the mounted tree if missing.
# obj/ is gitignored and rsync typically skips it — install.sh must create it.
if [[ ! -x obj/upside ]]; then
    echo '[bootstrap] building Upside in the mounted tree...'
    mkdir -p obj
    if ! sudo ./install.sh; then
        echo '[bootstrap] ERROR: install.sh failed — cannot run benchmarks without obj/upside.' >&2
        exit 1
    fi
    if [[ ! -x obj/upside ]]; then
        echo '[bootstrap] ERROR: obj/upside still missing after install.sh.' >&2
        exit 1
    fi
    echo '[bootstrap] Upside build OK'
    ls -lh obj/upside obj/libupside.so
fi

# Fetch any extra PDBs that the matrix references but aren't in example/.
python benchmarks/scripts/fetch_proteins.py

# Run.
python benchmarks/scripts/run_matrix.py \
    --matrix benchmarks/matrix.json \
    --output-dir /results \
    --tier $MATRIX_TIER \
    $MATRIX_ARGS

# Summarize.
python benchmarks/scripts/summarize.py \
    --results-dir /results \
    --pricing benchmarks/pricing.json \
    --output /results/report.md
"

sudo docker run --rm \
    -v "$REPO_DIR:/workspaces/DynaLab-merge-dynalab" \
    -v "$RESULTS_DIR:/results" \
    -e UPSIDE_HOME=/workspaces/DynaLab-merge-dynalab \
    -e OMP_NUM_THREADS="$OMP_THREADS" \
    "$IMAGE_TAG" \
    bash -lc "$RUN_CMD" 2>&1 | tee "$LOG_DIR/matrix.log"

log "done. Results live in $RESULTS_DIR"
log "    - $RESULTS_DIR/report.md      (markdown summary)"
log "    - $RESULTS_DIR/results.csv    (full table)"
log "    - $RESULTS_DIR/status.json    (pass/fail per case)"
log "    - $RESULTS_DIR/_logs/         (raw stdout)"

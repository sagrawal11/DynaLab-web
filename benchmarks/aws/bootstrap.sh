#!/usr/bin/env bash
# bootstrap.sh — runs ON the EC2 instance to install Docker, build the dev
# container image, build Upside (release mode), run a smoke speed-check, then
# run the DynaLab benchmark matrix.
#
# Idempotent: re-running picks up where the last run stopped, but if the
# previous run produced in-progress case directories (no result.json) you must
# clean them up first or set RESULTS_DIR to a fresh path.
#
# Inputs (env vars, all optional):
#   REPO_DIR           DynaLab checkout on the box (default: $HOME/DynaLab-merge-dynalab)
#   RESULTS_DIR        where to write results       (default: $HOME/dynalab_results)
#   IMAGE_TAG          Docker image tag             (default: dynalab-bench:latest)
#   MATRIX_TIER        which tier from matrix.json  (default: aws)
#   MATRIX_ARGS        extra args for run_matrix.py (e.g. "--only aws_baseline_small")
#   OMP_THREADS        env-default OMP_NUM_THREADS  (default: $(nproc))
#                      Per-case "omp_threads" in matrix.json still overrides this.
#   UPSIDE_BUILD_TYPE  release (default) or debug   (debug is 5-10x slower; profiling only)
#   FORCE_REBUILD      1 to force a full Upside rebuild even if obj/upside is current
#   SKIP_SMOKE         1 to skip the pre-flight smoke speed-check
#   SMOKE_MAX_SECONDS  hard ceiling for the smoke case wall time (default: 60)
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
UPSIDE_BUILD_TYPE="${UPSIDE_BUILD_TYPE:-release}"
FORCE_REBUILD="${FORCE_REBUILD:-0}"
SKIP_SMOKE="${SKIP_SMOKE:-0}"
SMOKE_MAX_SECONDS="${SMOKE_MAX_SECONDS:-60}"

LOG_DIR="$RESULTS_DIR/_logs"
mkdir -p "$RESULTS_DIR" "$LOG_DIR"

log() { echo "[bootstrap $(date -u +%H:%M:%S)] $*"; }
die() { echo "[bootstrap $(date -u +%H:%M:%S)] ERROR: $*" >&2; exit 1; }

# --- 1. Verify we are on a Linux box with internet --------------------------

log "host info"
uname -a
command -v sudo >/dev/null || die "sudo not available (Amazon Linux 2023 or Ubuntu expected)."

# --- 2. Install Docker + git + rsync if missing -----------------------------

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
        die "unsupported package manager. Install docker, git, rsync manually."
    fi
else
    log "docker already installed"
fi

sudo systemctl enable --now docker
sudo usermod -aG docker "$USER" || true

# --- 3. Verify the repo is here --------------------------------------------

[[ -d "$REPO_DIR/.devcontainer" ]] || die "$REPO_DIR is not a DynaLab checkout (no .devcontainer/)."
cd "$REPO_DIR"

# --- 4. Safety check: warn about stale in-progress case dirs ---------------

stale_cases=$(find "$RESULTS_DIR" -mindepth 1 -maxdepth 1 -type d ! -name '_logs' \
    -exec test '!' -f '{}/result.json' ';' -print 2>/dev/null | wc -l || echo 0)
if [[ "$stale_cases" -gt 0 ]]; then
    echo
    echo "WARNING: $RESULTS_DIR contains $stale_cases case directories without a result.json."
    echo "         (probably leftovers from a previous run that was killed)"
    echo "         summarize.py only counts cases that have result.json, but the in-progress"
    echo "         directories may confuse rsync/inspection."
    echo "         To clean them up, run:"
    echo "             find $RESULTS_DIR -mindepth 1 -maxdepth 1 -type d ! -name '_logs' \\"
    echo "                 -exec test '!' -f '{}/result.json' ';' -exec rm -rf '{}' +"
    echo "         Or set RESULTS_DIR to a fresh path (e.g. ~/dynalab_results_v2)."
    echo
fi

# --- 5. Build the dev container image (slow first time, fast on rerun) ----

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

# --- 6. Build Upside in release mode inside the container -----------------

# The mounted obj/.upside_build_type marker tells us whether the existing
# binary is release or debug. If it's missing, "debug", or FORCE_REBUILD=1,
# wipe and rebuild.
EXISTING_BUILD_TYPE="unknown"
if [[ -f "$REPO_DIR/obj/.upside_build_type" ]]; then
    EXISTING_BUILD_TYPE="$(<"$REPO_DIR/obj/.upside_build_type")"
fi

NEED_REBUILD=0
if [[ "$FORCE_REBUILD" == "1" ]]; then
    log "FORCE_REBUILD=1: will rebuild Upside"
    NEED_REBUILD=1
elif [[ ! -x "$REPO_DIR/obj/upside" ]]; then
    log "no obj/upside present: will build Upside"
    NEED_REBUILD=1
elif [[ "$EXISTING_BUILD_TYPE" != "$UPSIDE_BUILD_TYPE" ]]; then
    log "existing build type '$EXISTING_BUILD_TYPE' != requested '$UPSIDE_BUILD_TYPE': will rebuild"
    NEED_REBUILD=1
else
    log "obj/upside present, build_type=$EXISTING_BUILD_TYPE — reusing"
fi

if [[ "$NEED_REBUILD" == "1" ]]; then
    log "building Upside in the mounted tree (build_type=$UPSIDE_BUILD_TYPE)..."
    sudo rm -rf "$REPO_DIR/obj"
    sudo docker run --rm \
        -v "$REPO_DIR:/workspaces/DynaLab-merge-dynalab" \
        -e UPSIDE_BUILD_TYPE="$UPSIDE_BUILD_TYPE" \
        "$IMAGE_TAG" \
        bash -lc "set -euo pipefail
        cd /workspaces/DynaLab-merge-dynalab
        source /opt/conda/etc/profile.d/conda.sh
        conda activate upside2-env
        ./install.sh" 2>&1 | tee "$LOG_DIR/upside-build.log"
    [[ -x "$REPO_DIR/obj/upside" ]] || die "obj/upside missing after install.sh"
    log "Upside build OK ($(cat "$REPO_DIR/obj/.upside_build_type" 2>/dev/null || echo unknown))"
fi

# --- 7. Pre-flight: smoke speed-check ------------------------------------

if [[ "$SKIP_SMOKE" == "1" ]]; then
    log "SKIP_SMOKE=1: skipping the pre-flight speed-check"
else
    log "pre-flight smoke speed-check (smoke_chig, max ${SMOKE_MAX_SECONDS}s)..."

    SMOKE_DIR="$RESULTS_DIR/_smoke"
    sudo rm -rf "$SMOKE_DIR"
    mkdir -p "$SMOKE_DIR"

    set +e
    sudo docker run --rm \
        -v "$REPO_DIR:/workspaces/DynaLab-merge-dynalab" \
        -v "$SMOKE_DIR:/results" \
        -e UPSIDE_HOME=/workspaces/DynaLab-merge-dynalab \
        -e OMP_NUM_THREADS=1 \
        -e PYTHONUNBUFFERED=1 \
        "$IMAGE_TAG" \
        bash -lc "set -euo pipefail
        cd /workspaces/DynaLab-merge-dynalab
        source /opt/conda/etc/profile.d/conda.sh
        conda activate upside2-env
        export UPSIDE_HOME=/workspaces/DynaLab-merge-dynalab
        export PYTHONPATH=\"\$UPSIDE_HOME/py:\${PYTHONPATH:-}\"
        export PATH=\"\$UPSIDE_HOME/py:\$UPSIDE_HOME/obj:\$PATH\"
        python benchmarks/scripts/run_matrix.py \
            --matrix benchmarks/matrix.json \
            --output-dir /results \
            --only smoke_chig" 2>&1 | tee "$LOG_DIR/smoke.log"
    SMOKE_EXIT=$?
    set -e

    SMOKE_RESULT="$SMOKE_DIR/smoke_chig/result.json"
    if [[ "$SMOKE_EXIT" -ne 0 || ! -f "$SMOKE_RESULT" ]]; then
        echo
        die "smoke speed-check FAILED. See $LOG_DIR/smoke.log. Do not run the full matrix."
    fi

    SMOKE_WALL=$(python3 -c "import json,sys; print(round(float(json.load(open('$SMOKE_RESULT'))['wall_seconds']),2))")
    SMOKE_RATE=$(python3 -c "import json,sys; r=json.load(open('$SMOKE_RESULT')); print(round(float(r.get('steps_per_second') or 0),1))")
    log "smoke wall=${SMOKE_WALL}s, rate=${SMOKE_RATE} steps/sec on chig (5000 steps)"

    SMOKE_OVER=$(python3 -c "print(1 if $SMOKE_WALL > $SMOKE_MAX_SECONDS else 0)")
    if [[ "$SMOKE_OVER" == "1" ]]; then
        echo
        echo "ERROR: smoke case took ${SMOKE_WALL}s > ${SMOKE_MAX_SECONDS}s ceiling."
        echo "       A release-mode Upside should do 5000 chig steps in <10s on c7i.4xlarge."
        echo "       If this number is high, the binary may still be debug-mode or the box may be wrong-sized."
        echo "       Inspect:  $LOG_DIR/upside-build.log  and  $LOG_DIR/smoke.log"
        echo "       To override anyway: SKIP_SMOKE=1 bash $0"
        exit 2
    fi

    # Rough wall-time projection so the user can decide before committing.
    # The aws-tier total work is approximately 750k step-equivalents at the
    # smoke protein's per-core rate. Real wall time will be HIGHER than this
    # because chig (~24 residues) is faster than 1dfn (38 res) and much faster
    # than 1ubq (76 res) / 2qke_mon (216 res). Treat the number as a lower bound.
    if [[ "$MATRIX_TIER" == "aws" ]]; then
        EST_HOURS=$(python3 -c "r=$SMOKE_RATE; print(round(750000.0/r/3600, 1) if r>0 else 'n/a')")
        log "rough projected aws-tier wall time: >= ${EST_HOURS} hours (chig rate is an upper bound; real wall time is typically 1.5-3x this)"
    fi
fi

# --- 8. Run the benchmark matrix ----------------------------------------

log "running benchmark matrix (tier=$MATRIX_TIER, default OMP_NUM_THREADS=$OMP_THREADS)"

RUN_CMD="set -euo pipefail
cd /workspaces/DynaLab-merge-dynalab
source /opt/conda/etc/profile.d/conda.sh
conda activate upside2-env
export UPSIDE_HOME=/workspaces/DynaLab-merge-dynalab
export PYTHONPATH=\"\$UPSIDE_HOME/py:\${PYTHONPATH:-}\"
export PATH=\"\$UPSIDE_HOME/py:\$UPSIDE_HOME/obj:\$PATH\"
[[ -x obj/upside ]] || { echo 'ERROR: obj/upside missing; rebuild Upside first.' >&2; exit 1; }
python benchmarks/scripts/fetch_proteins.py
python benchmarks/scripts/run_matrix.py \
    --matrix benchmarks/matrix.json \
    --output-dir /results \
    --tier $MATRIX_TIER \
    $MATRIX_ARGS
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
    -e PYTHONUNBUFFERED=1 \
    "$IMAGE_TAG" \
    bash -lc "$RUN_CMD" 2>&1 | tee "$LOG_DIR/matrix.log"

log "done. Results live in $RESULTS_DIR"
log "    - $RESULTS_DIR/report.md      (markdown summary)"
log "    - $RESULTS_DIR/results.csv    (full table)"
log "    - $RESULTS_DIR/status.json    (pass/fail per case)"
log "    - $RESULTS_DIR/_logs/         (raw stdout)"

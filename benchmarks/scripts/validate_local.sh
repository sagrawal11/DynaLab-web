#!/usr/bin/env bash
# Quick local validation: runs only the smoke case and confirms the pipeline
# produces the expected files. Run inside the dev container.
#
# Usage:
#   bash benchmarks/scripts/validate_local.sh

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"

# Always use the repo this script lives in — ignore a stale UPSIDE_HOME from the image.
export UPSIDE_HOME="$REPO"

echo "[validate] UPSIDE_HOME=$UPSIDE_HOME"

if [[ ! -x "$REPO/obj/upside" ]]; then
    echo "[validate] obj/upside missing — building Upside (requires sudo)..."
    sudo ./install.sh
fi

OUT="$REPO/benchmarks/results/smoke"
rm -rf "$OUT"

python "$REPO/benchmarks/scripts/run_matrix.py" \
    --matrix "$REPO/benchmarks/matrix.json" \
    --output-dir "$OUT" \
    --only smoke_chig

if [[ ! -f "$OUT/smoke_chig/result.json" ]]; then
    echo "[validate] FAIL: result.json was not written" >&2
    exit 1
fi

python "$REPO/benchmarks/scripts/summarize.py" \
    --results-dir "$OUT" \
    --pricing "$REPO/benchmarks/pricing.json" \
    --output "$OUT/report.md"

echo
echo "[validate] OK"
echo "  result:  $OUT/smoke_chig/result.json"
echo "  report:  $OUT/report.md"

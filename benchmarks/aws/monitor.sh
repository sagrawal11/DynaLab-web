#!/usr/bin/env bash
# monitor.sh — run ON the EC2 instance to get a one-shot benchmark progress report.
#
# Usage (on EC2 inside ~/DynaLab-merge-dynalab):
#   bash benchmarks/aws/monitor.sh
#   bash benchmarks/aws/monitor.sh ~/dynalab_results_v2   # custom results dir

set -uo pipefail

RESULTS_DIR="${1:-$HOME/dynalab_results}"

header() {
    echo
    echo "================================================================"
    echo "  $*"
    echo "================================================================"
}

header "process status"
if pgrep -af bootstrap.sh >/dev/null; then
    pgrep -af bootstrap.sh
else
    echo "(no bootstrap.sh process)"
fi
if pgrep -af "docker run" >/dev/null; then
    pgrep -af "docker run" | sed 's/\(.\{200\}\).*/\1.../'
else
    echo "(no docker run process)"
fi

header "docker containers"
sudo docker ps --format 'table {{.ID}}\t{{.Image}}\t{{.Status}}\t{{.Names}}' || true

header "results dir"
if [[ -d "$RESULTS_DIR" ]]; then
    ls -lah "$RESULTS_DIR" | head -40
else
    echo "(no $RESULTS_DIR)"
    exit 0
fi

header "completed cases (have result.json)"
shopt -s nullglob
done_cases=0
for f in "$RESULTS_DIR"/*/result.json; do
    case_id="$(basename "$(dirname "$f")")"
    ok=$(python3 -c "import json,sys; r=json.load(open('$f')); print('OK' if r.get('ok') else 'FAIL', round(float(r.get('wall_seconds',0)),1), 'sec,', round(float(r.get('steps_per_second') or 0),1), 'steps/s,', round(float(r.get('peak_rss_mb') or 0),1), 'MB RSS')" 2>/dev/null || echo "??")
    printf "  %-30s %s\n" "$case_id" "$ok"
    done_cases=$((done_cases + 1))
done
if [[ $done_cases -eq 0 ]]; then
    echo "  (none yet)"
fi

header "in-progress case directories (no result.json yet)"
for d in "$RESULTS_DIR"/*/; do
    base="$(basename "$d")"
    [[ "$base" == "_logs" || "$base" == "_smoke" ]] && continue
    if [[ ! -f "$d/result.json" ]]; then
        printf "  %-30s" "$base"
        sim_log=$(find "$d" -name 'sim.run.log' -type f 2>/dev/null | head -1)
        if [[ -n "$sim_log" ]]; then
            last=$(tail -1 "$sim_log" | tr -s ' ' | cut -d' ' -f1-4)
            printf "  sim.run.log tail: %s\n" "$last"
        else
            echo "  (no sim.run.log yet)"
        fi
    fi
done

header "matrix log tail"
if [[ -f "$RESULTS_DIR/_logs/matrix.log" ]]; then
    tail -15 "$RESULTS_DIR/_logs/matrix.log"
else
    echo "(no matrix.log yet)"
fi

header "status.json"
if [[ -f "$RESULTS_DIR/status.json" ]]; then
    cat "$RESULTS_DIR/status.json"
else
    echo "(no status.json — matrix has not finished)"
fi

header "report.md"
if [[ -f "$RESULTS_DIR/report.md" ]]; then
    head -25 "$RESULTS_DIR/report.md"
    echo "..."
    echo "(full report: $RESULTS_DIR/report.md)"
else
    echo "(no report.md — matrix has not finished)"
fi

echo

#!/usr/bin/env bash
# Pull the benchmark results back to your laptop.
#
# Usage:
#   bash benchmarks/aws/collect_results.sh [LOCAL_DIR]
# Defaults LOCAL_DIR to benchmarks/results/aws.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_FILE="$HERE/.last_instance.env"

if [[ -f "$STATE_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$STATE_FILE"
fi

PUBLIC_IP="${PUBLIC_IP:-}"
KEY_NAME="${KEY_NAME:-dynalab-bench}"
KEY_PATH="${KEY_PATH:-$HOME/.ssh/${KEY_NAME}.pem}"

if [[ -z "$PUBLIC_IP" ]]; then
    echo "ERROR: PUBLIC_IP not set; either launch_ec2.sh hasn't run or .last_instance.env is missing." >&2
    echo "       You can also pass it explicitly: PUBLIC_IP=1.2.3.4 bash $0" >&2
    exit 1
fi

LOCAL_DIR="${1:-benchmarks/results/aws}"
mkdir -p "$LOCAL_DIR"

echo "Pulling ~/dynalab_results/ from ec2-user@${PUBLIC_IP} into ${LOCAL_DIR}/"
rsync -avz \
    -e "ssh -i ${KEY_PATH} -o StrictHostKeyChecking=accept-new" \
    "ec2-user@${PUBLIC_IP}:~/dynalab_results/" \
    "$LOCAL_DIR/"

echo
echo "Done. Open $LOCAL_DIR/report.md to read the cost report."

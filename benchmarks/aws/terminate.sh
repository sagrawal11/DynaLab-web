#!/usr/bin/env bash
# Terminate the EC2 instance launched by launch_ec2.sh.
#
# Reads benchmarks/aws/.last_instance.env. If you want to terminate a
# different instance, set INSTANCE_ID and REGION explicitly.
#
# Usage:
#   bash benchmarks/aws/terminate.sh
#   INSTANCE_ID=i-0123 REGION=us-east-1 bash benchmarks/aws/terminate.sh

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_FILE="$HERE/.last_instance.env"

if [[ -f "$STATE_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$STATE_FILE"
fi

INSTANCE_ID="${INSTANCE_ID:-}"
REGION="${REGION:-us-east-1}"

if [[ -z "$INSTANCE_ID" ]]; then
    echo "ERROR: INSTANCE_ID not set. Either run launch_ec2.sh first," >&2
    echo "       or pass it explicitly: INSTANCE_ID=i-xxx bash $0" >&2
    exit 1
fi

echo "About to terminate $INSTANCE_ID in $REGION."
read -r -p "Type the instance id to confirm: " confirm
if [[ "$confirm" != "$INSTANCE_ID" ]]; then
    echo "Confirmation did not match. Aborting." >&2
    exit 1
fi

aws ec2 terminate-instances --region "$REGION" --instance-ids "$INSTANCE_ID" >/dev/null
echo "Termination requested. Waiting for it to complete..."
aws ec2 wait instance-terminated --region "$REGION" --instance-ids "$INSTANCE_ID"
echo "Terminated."

# Mark the state file as stale so we don't accidentally reuse it.
mv "$STATE_FILE" "$STATE_FILE.terminated.$(date -u +%Y%m%dT%H%M%SZ)" 2>/dev/null || true
echo "Stamped $STATE_FILE as .terminated.*"

echo
echo "Reminder: confirm in the AWS console that no EBS volumes were left over."
echo "    EC2 -> Volumes -> filter by tag dynalab-bench"

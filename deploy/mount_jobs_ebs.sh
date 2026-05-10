#!/usr/bin/env bash
# Mount a fresh EBS volume at /var/lib/dynalab/jobs and bind-mount it
# into the container at runtime. Idempotent: safe to re-run.
#
# Usage: mount_jobs_ebs.sh /dev/nvme1n1

set -euo pipefail

DEVICE="${1:?usage: $0 /dev/nvme1n1}"
MOUNT=/var/lib/dynalab/jobs

mkdir -p "$MOUNT"

# Only format the device if it isn't already an ext4 filesystem.
if ! blkid "$DEVICE" >/dev/null 2>&1; then
    echo "Formatting $DEVICE as ext4 (first run on this volume)"
    mkfs.ext4 -q "$DEVICE"
fi

# Add to fstab if missing so the volume comes back after reboot.
if ! grep -q "$DEVICE" /etc/fstab; then
    echo "$DEVICE  $MOUNT  ext4  defaults,nofail  0 2" >> /etc/fstab
fi

mountpoint -q "$MOUNT" || mount "$MOUNT"
chown 1000:1000 "$MOUNT"
echo "Job artifacts persistent volume mounted at $MOUNT"

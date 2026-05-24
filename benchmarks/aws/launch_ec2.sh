#!/usr/bin/env bash
# Launch one EC2 instance suitable for running the DynaLab benchmark matrix.
#
# Defaults (override with environment variables):
#   INSTANCE_TYPE     c7i.4xlarge (16 vCPU, 32 GiB) — fits all matrix cases
#   REGION            us-east-1
#   KEY_NAME          dynalab-bench
#   SECURITY_GROUP    dynalab-bench-sg
#   ROOT_VOLUME_GB    60
#   AMI_ALIAS         /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64
#   USE_SPOT          0 (set to 1 to request a Spot instance — cheaper, can be interrupted)
#
# Writes ``benchmarks/aws/.last_instance.env`` with the resulting instance ID,
# IP, key, region — terminate.sh and other helpers read from it.
#
# Usage:
#   bash benchmarks/aws/launch_ec2.sh
#   USE_SPOT=1 INSTANCE_TYPE=c7i.2xlarge bash benchmarks/aws/launch_ec2.sh

set -euo pipefail

INSTANCE_TYPE="${INSTANCE_TYPE:-c7i.4xlarge}"
REGION="${REGION:-us-east-1}"
KEY_NAME="${KEY_NAME:-dynalab-bench}"
SECURITY_GROUP="${SECURITY_GROUP:-dynalab-bench-sg}"
ROOT_VOLUME_GB="${ROOT_VOLUME_GB:-60}"
AMI_ALIAS="${AMI_ALIAS:-/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64}"
USE_SPOT="${USE_SPOT:-0}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_FILE="$HERE/.last_instance.env"

# --- Sanity checks ---------------------------------------------------------

command -v aws >/dev/null || { echo "ERROR: aws CLI not found. See benchmarks/README.md §3.1.2." >&2; exit 1; }
aws sts get-caller-identity >/dev/null 2>&1 || {
    echo "ERROR: AWS credentials not configured. Run 'aws configure' first." >&2
    exit 1
}

echo "Launching:"
echo "  region:        $REGION"
echo "  type:          $INSTANCE_TYPE"
echo "  spot:          $([[ "$USE_SPOT" == "1" ]] && echo yes || echo no)"
echo "  key:           $KEY_NAME"
echo "  security-grp:  $SECURITY_GROUP"
echo "  root volume:   ${ROOT_VOLUME_GB} GB"
echo

# --- Resolve AMI and security group ---------------------------------------

AMI_ID="$(aws ssm get-parameters \
    --region "$REGION" \
    --names "$AMI_ALIAS" \
    --query 'Parameters[0].Value' --output text)"
if [[ -z "$AMI_ID" || "$AMI_ID" == "None" ]]; then
    echo "ERROR: Could not resolve AMI from SSM parameter $AMI_ALIAS" >&2
    exit 1
fi
echo "AMI:           $AMI_ID"

SG_ID="$(aws ec2 describe-security-groups \
    --region "$REGION" \
    --group-names "$SECURITY_GROUP" \
    --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "")"
if [[ -z "$SG_ID" || "$SG_ID" == "None" ]]; then
    echo "ERROR: Security group '$SECURITY_GROUP' not found in $REGION." >&2
    echo "       Create it once with the commands in benchmarks/README.md §3.1.4." >&2
    exit 1
fi
echo "SG:            $SG_ID"

KEY_EXISTS="$(aws ec2 describe-key-pairs \
    --region "$REGION" --key-names "$KEY_NAME" \
    --query 'KeyPairs[0].KeyName' --output text 2>/dev/null || echo "")"
if [[ -z "$KEY_EXISTS" || "$KEY_EXISTS" == "None" ]]; then
    echo "ERROR: SSH key pair '$KEY_NAME' not found in $REGION." >&2
    echo "       Create it once with the commands in benchmarks/README.md §3.1.3." >&2
    exit 1
fi

# --- Build the run-instances arguments ------------------------------------

BLOCK_DEV=$(cat <<EOF
[
  {
    "DeviceName": "/dev/xvda",
    "Ebs": {
      "VolumeSize": ${ROOT_VOLUME_GB},
      "VolumeType": "gp3",
      "DeleteOnTermination": true
    }
  }
]
EOF
)

RUN_ARGS=(
    --region "$REGION"
    --image-id "$AMI_ID"
    --instance-type "$INSTANCE_TYPE"
    --key-name "$KEY_NAME"
    --security-group-ids "$SG_ID"
    --block-device-mappings "$BLOCK_DEV"
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=dynalab-bench},{Key=managed-by,Value=benchmarks/aws/launch_ec2.sh}]'
    --count 1
)

if [[ "$USE_SPOT" == "1" ]]; then
    RUN_ARGS+=(--instance-market-options 'MarketType=spot,SpotOptions={SpotInstanceType=one-time,InstanceInterruptionBehavior=terminate}')
fi

# --- Launch ----------------------------------------------------------------

echo "Calling ec2 run-instances..."
INSTANCE_ID="$(aws ec2 run-instances "${RUN_ARGS[@]}" --query 'Instances[0].InstanceId' --output text)"
echo "Instance ID:   $INSTANCE_ID"

echo "Waiting for instance to enter 'running' state..."
aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE_ID"

PUBLIC_IP="$(aws ec2 describe-instances --region "$REGION" --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)"
PUBLIC_DNS="$(aws ec2 describe-instances --region "$REGION" --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].PublicDnsName' --output text)"

# --- Persist state and print summary --------------------------------------

cat > "$STATE_FILE" <<EOF
INSTANCE_ID=$INSTANCE_ID
REGION=$REGION
PUBLIC_IP=$PUBLIC_IP
PUBLIC_DNS=$PUBLIC_DNS
KEY_NAME=$KEY_NAME
INSTANCE_TYPE=$INSTANCE_TYPE
USE_SPOT=$USE_SPOT
EOF

cat <<EOF

--------------------------------------------------------------------
  EC2 instance is up.
--------------------------------------------------------------------
  Instance ID:  $INSTANCE_ID
  Public IP:    $PUBLIC_IP
  Public DNS:   $PUBLIC_DNS

  SSH (use the .pem you created in §3.1.3):
    ssh -i ~/.ssh/${KEY_NAME}.pem ec2-user@${PUBLIC_IP}

  Push your local checkout up (run from this repo's root):
    rsync -avz --exclude='.git' --exclude='obj/' --exclude='benchmarks/results' \\
        -e "ssh -i ~/.ssh/${KEY_NAME}.pem" \\
        ./ ec2-user@${PUBLIC_IP}:~/DynaLab-merge-dynalab/

  Then SSH in and run:
    cd ~/DynaLab-merge-dynalab
    bash benchmarks/aws/bootstrap.sh

  When done, tear down with:
    bash benchmarks/aws/terminate.sh
--------------------------------------------------------------------
EOF

echo "State persisted to $STATE_FILE"

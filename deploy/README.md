# Deploying DynaLab to EC2

The dev container in `.devcontainer/` is what we run on a developer's
laptop. For an always-on team-shared deployment, the same image runs on
an EC2 instance with three additions:

1. **Persistent jobs** - mount an EBS volume at `/var/lib/dynalab/jobs`
   so trajectories and analyses survive instance restarts.
2. **Secret handling** - read `TAMARIND_API_KEY` from AWS Systems Manager
   Parameter Store at startup instead of from a checked-in `.env`.
3. **Process supervision** - run the Flask backend under `systemd`
   instead of an interactive shell.

The scripts in this directory implement those three pieces. They are
intentionally small (~40 lines each) and self-documenting.

## Recommended instance shape

* **AMI:** Amazon Linux 2023 (or Ubuntu 22.04 LTS).
* **Type:** `c6i.4xlarge` (16 vCPU / 32 GiB RAM) - enough to run a 7-force
  x 2-replica sweep in parallel without thrashing.
* **Storage:** 100 GiB gp3 root + a separate 200 GiB gp3 EBS volume for
  `/var/lib/dynalab/jobs`.
* **Networking:** allow inbound 80/443 from your VPN/CIDR only. Don't
  expose the Flask dev server to the internet directly; put it behind
  nginx + an HTTPS terminator (ALB, Caddy, or a manual nginx config).
* **IAM role:** attach a role with `ssm:GetParameter` for the
  `/dynalab/*` parameter prefix (least-privilege secret read).

## Steps

```bash
# 1. SSH to the instance
ssh ec2-user@<instance-ip>

# 2. Pull the repo and the env-loader script
sudo yum install -y git docker
sudo systemctl enable --now docker
git clone https://github.com/<your-org>/DynaLab-merge-dynalab.git /opt/dynalab
cd /opt/dynalab

# 3. Mount the persistent EBS volume for job artifacts
sudo /opt/dynalab/deploy/mount_jobs_ebs.sh /dev/nvme1n1

# 4. Install secrets from SSM (writes /etc/dynalab/env)
sudo /opt/dynalab/deploy/load_ssm_secrets.sh

# 5. Build + start the service
sudo cp deploy/dynalab.service /etc/systemd/system/dynalab.service
sudo systemctl daemon-reload
sudo systemctl enable --now dynalab
```

The Flask backend listens on `127.0.0.1:5001`. Front it with nginx /
ALB / Caddy for TLS - the systemd unit deliberately doesn't bind 0.0.0.0.

## Logs + monitoring

* `journalctl -u dynalab -f` -- live server logs.
* Per-job logs live in `/var/lib/dynalab/jobs/<job_id>/sim.log` and
  `sweeps/<sweep_id>/sweep.log`.
* The image already has matplotlib + mdtraj + scikit-learn baked in;
  no need to `pip install` on the host.

## Updating

```bash
cd /opt/dynalab
git pull
docker build -t dynalab:latest -f .devcontainer/Dockerfile .
sudo systemctl restart dynalab
```

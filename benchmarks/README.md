# DynaLab Benchmark Kit

This folder contains everything you need to:

1. Measure how DynaLab simulations perform (wall time, CPU usage, memory, output size).
2. Convert those measurements into AWS dollar cost.
3. Run the same benchmark on AWS so the report is defensible.

The plan, in plain English:

> Run a small but representative set of simulations both on your laptop (to make sure
> nothing is broken) and on a single AWS EC2 instance (to get real numbers).
> Then a script turns those numbers into a cost table you can hand to a stakeholder.

You do **not** need AWS Batch, Terraform, ECR, or any other heavy infrastructure to do this.
One EC2 box is enough. Once you have numbers, you can decide whether Batch is worth the work.

---

## What you will get at the end

- `benchmarks/results/<run_id>/<case_id>/result.json` — raw metrics for each case.
- `benchmarks/results/<run_id>/results.csv` — every case in one table.
- `benchmarks/results/<run_id>/report.md` — a human-readable cost report.

`report.md` is the deliverable. It looks like:

```
| case | protein | mode | vCPU | wall (min) | vCPU-h | $ on-demand | $ spot | output GB |
| ---- | ------- | ---- | ---- | ---------- | ------ | ----------- | ------ | --------- |
| ...  | ...     | ...  | ...  | ...        | ...    | ...         | ...    | ...       |
```

---

## How to read this guide

There are three phases. **Do them in order.** Each step says exactly what to type and
what to expect.

- **Phase 1 — Local smoke test (15 min).**
  Make sure the benchmark scripts work on your laptop dev container before paying for AWS.
- **Phase 2 — Local mini matrix (30–90 min).**
  Run a tiny version of the matrix to validate the cost report.
- **Phase 3 — AWS full matrix (1–2 hours of EC2 time, < $5 of credit).**
  Run on AWS and get the real numbers.

If anything fails, scroll to the [Troubleshooting](#troubleshooting) section at the bottom.

---

# Phase 1 — Local smoke test

Goal: prove that one tiny simulation runs end-to-end and produces a `result.json`.

### 1.1 Open the dev container

In VS Code: `View → Command Palette → Dev Containers: Reopen in Container`.

If you don’t use VS Code, run inside the project folder:

```bash
docker build -f .devcontainer/Dockerfile -t dynalab-dev .
docker run -it --rm \
  -v "$(pwd):/workspaces/DynaLab-merge-dynalab" \
  -e UPSIDE_HOME=/workspaces/DynaLab-merge-dynalab \
  dynalab-dev bash
```

You should now be at a shell prompt inside the container.

### 1.2 Activate the conda environment

```bash
source /opt/conda/etc/profile.d/conda.sh
conda activate upside2-env
```

Verify:

```bash
which python              # should contain /opt/conda/envs/upside2-env/
python -c "import tables, numpy, mdtraj; print('OK')"
```

### 1.3 Build Upside in the DynaLab tree (one time, ~5 min)

```bash
cd /workspaces/DynaLab-merge-dynalab
[ -x obj/upside ] || sudo ./install.sh
ls -lh obj/upside obj/libupside.so
```

You should see two files. If not, see [Troubleshooting](#troubleshooting).

### 1.4 Run the smoke test

The benchmark scripts auto-detect your repo root (they prefer the bind-mounted
checkout under `/workspaces/…` over the image's baked-in `/upside2-md` path).
If you want to be explicit:

```bash
export UPSIDE_HOME=/workspaces/DynaLab-merge-dynalab   # adjust if your folder name differs
```

Then run the smoke case:

```bash
cd /workspaces/DynaLab-merge-dynalab
python benchmarks/scripts/run_matrix.py \
    --matrix benchmarks/matrix.json \
    --output-dir benchmarks/results/smoke \
    --only smoke_chig
```

Or use the one-shot validator (sets `UPSIDE_HOME` for you):

```bash
bash benchmarks/scripts/validate_local.sh
```

Expected output, last lines:

```
  OK wall=<a few>s peak_rss=...MB output=...MB
Matrix done: 1/1 OK
```

If you see `FAIL` with `wall=0.0s`, see [Troubleshooting](#troubleshooting).

If you see `1/1 OK`, the runner works. Move on to Phase 2.

---

# Phase 2 — Local mini matrix

Goal: run 2–3 small cases on your laptop and produce the cost report. This validates
the whole pipeline before you pay for an EC2 instance.

```bash
cd /workspaces/DynaLab-merge-dynalab
python benchmarks/scripts/run_matrix.py \
    --matrix benchmarks/matrix.json \
    --output-dir benchmarks/results/local \
    --tier local
```

This runs only the cases tagged `tier: "local"` in the matrix (small, short jobs).
Expected total time: 5–20 minutes depending on your laptop.

When it finishes, generate the cost report:

```bash
python benchmarks/scripts/summarize.py \
    --results-dir benchmarks/results/local \
    --pricing benchmarks/pricing.json \
    --output benchmarks/results/local/report.md
```

Open `benchmarks/results/local/report.md`. You should see a populated table.

> The dollar numbers in this local report are projections based on AWS pricing
> (we *imagine* the case ran on a c7i.2xlarge), not real bills. The wall times
> are real.

---

# Phase 3 — AWS full matrix

You will:

1. Launch one EC2 instance (~$0.36/hr on-demand, ~$0.11/hr spot for c7i.2xlarge).
2. SSH in.
3. Run a single bootstrap script that builds the image and runs the matrix.
4. Download the results.
5. Terminate the instance (very important — that's how you avoid paying $50 in idle).

The whole thing should cost **< $5** of your $200 credit, and take ~1.5–2.5 hours.

## 3.1 One-time AWS account setup

If you have *never* used AWS from the command line on this laptop, do this once.

### 3.1.1 Create an IAM user with programmatic access

1. Sign in to the AWS console as the root user (or an existing admin).
2. Go to **IAM → Users → Create user**.
3. Name it `dynalab-bench`. Click **Next**.
4. Select **Attach policies directly**, attach **AdministratorAccess** for now
   (you can lock this down later). Click **Next → Create user**.
5. Open the new user → **Security credentials → Create access key → CLI**.
   Download the CSV. **Keep it safe** — these are your AWS keys.

### 3.1.2 Install AWS CLI

```bash
# macOS
brew install awscli
# or: curl "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o AWSCLIV2.pkg && sudo installer -pkg AWSCLIV2.pkg -target /

# Linux
sudo apt-get install -y awscli
```

Then configure:

```bash
aws configure
# AWS Access Key ID:     <paste from CSV>
# AWS Secret Access Key: <paste from CSV>
# Default region name:   us-east-1
# Default output format: json
```

### 3.1.3 Create an SSH key pair (one time)

```bash
aws ec2 create-key-pair \
    --key-name dynalab-bench \
    --query 'KeyMaterial' --output text > ~/.ssh/dynalab-bench.pem
chmod 600 ~/.ssh/dynalab-bench.pem
```

This downloads a private key. AWS keeps the public half. We use it to SSH in.

### 3.1.4 Create a security group that allows SSH from your IP

```bash
MY_IP=$(curl -s https://checkip.amazonaws.com)
aws ec2 create-security-group \
    --group-name dynalab-bench-sg \
    --description "Allow SSH from my laptop"
aws ec2 authorize-security-group-ingress \
    --group-name dynalab-bench-sg \
    --protocol tcp --port 22 \
    --cidr ${MY_IP}/32
```

You're done with one-time setup.

## 3.2 Launch the EC2 instance

From your laptop, in this repo's root:

```bash
bash benchmarks/aws/launch_ec2.sh
```

The script prints something like:

```
Instance ID:  i-0abc...
Public IP:    3.92.xx.xx
SSH command:  ssh -i ~/.ssh/dynalab-bench.pem ec2-user@3.92.xx.xx
```

**Save that information.** Wait ~30 seconds, then SSH in:

```bash
ssh -i ~/.ssh/dynalab-bench.pem ec2-user@<public-ip>
```

The first time you connect, it will ask `Are you sure you want to continue connecting`.
Type `yes`.

## 3.3 Bootstrap the instance and run the matrix

You have two options for getting the code onto the instance:

### Option A — Push your local checkout (simplest, recommended)

From a **second terminal on your laptop** (keep the SSH terminal too):

```bash
rsync -avz --exclude='.git' --exclude='obj/' --exclude='benchmarks/results' \
    -e "ssh -i ~/.ssh/dynalab-bench.pem" \
    ./ ec2-user@<public-ip>:~/DynaLab-merge-dynalab/
```

### Option B — Clone from GitHub (if your fork is pushed)

In the SSH terminal:

```bash
git clone https://github.com/<you>/DynaLab-merge-dynalab.git ~/DynaLab-merge-dynalab
```

### Now run the bootstrap inside the SSH terminal

```bash
cd ~/DynaLab-merge-dynalab
bash benchmarks/aws/bootstrap.sh
```

This script:

1. Installs Docker (~1 min).
2. Builds the dev container image (~15–25 min the first time).
3. Runs the full benchmark matrix inside the container (~30–90 min).
4. Writes `~/dynalab_results/` with `result.json` per case + a CSV + a report.

You will see progress in the terminal. **Do not close the terminal until it finishes.**
If your laptop sleeps and SSH dies, see [Resuming after disconnect](#resuming-after-disconnect).

## 3.4 Download the results

In a terminal on your laptop:

```bash
mkdir -p benchmarks/results/aws
rsync -avz \
    -e "ssh -i ~/.ssh/dynalab-bench.pem" \
    ec2-user@<public-ip>:~/dynalab_results/ \
    benchmarks/results/aws/
```

You now have the AWS report at `benchmarks/results/aws/report.md`.

## 3.5 ⚠️ Terminate the instance

This is the step you cannot skip. An idle EC2 instance still costs money.

```bash
bash benchmarks/aws/terminate.sh
```

Confirm in the AWS console (**EC2 → Instances**) that the instance state is
`Terminated`. You're done.

---

# How the matrix is structured

The benchmark cases live in `benchmarks/matrix.json`. Each case has these fields:

```json
{
  "case_id": "med_const_8vcpu",
  "tier": "aws",
  "mode": "constant",
  "pdb_id": "1ubq",
  "pdb_source": "example/07.MoreRestraints/pdb/1UBQ.pdb",
  "duration": 1000000,
  "frame_interval": 200,
  "temperature": "0.85",
  "n_replicas": 1,
  "omp_threads": 8,
  "instance_assumed": "c7i.2xlarge"
}
```

Tiers:

- `smoke` — runs in seconds. Just to verify nothing is broken.
- `local` — small enough to run on a laptop, ~5–20 min total.
- `aws` — real benchmarks. Run on a c7i.2xlarge (8 vCPU) in AWS.

Run the matrix with `--tier <name>` or pick a single case with `--only <case_id>`.

---

# How the cost model works

For each case we measure:

- `wall_seconds` — real time the simulation took.
- `peak_rss_kb` — peak memory the simulation used.
- `output_bytes` — bytes written under the work directory.
- `cpu_user_seconds` — CPU work done by user code.
- `steps_per_second` — derived from duration ÷ wall.

`summarize.py` joins each result with `pricing.json` to compute:

```
vcpu_hours          = vcpu_count * (wall_seconds / 3600)
on_demand_cost_usd  = (wall_seconds / 3600) * on_demand_per_hour
spot_cost_usd       = (wall_seconds / 3600) * spot_per_hour
ebs_cost_per_month  = (output_bytes / 1e9) * ebs_gp3_per_gb_month
s3_cost_per_month   = (output_bytes / 1e9) * s3_standard_per_gb_month
```

For force sweeps, total cost is the sum across all sub-jobs, but wall time is the
slowest sub-job (because they run in parallel on Batch).

Edit `benchmarks/pricing.json` if AWS pricing changes.

---

# Troubleshooting

### `obj/upside: No such file or directory`

You forgot to build Upside in the DynaLab tree. Run `sudo ./install.sh` from the
repo root inside the dev container.

### `can't open file '/upside2-md/start/Single_Replica.py'` (or `FAIL wall=0.0s`)

The dev container image sets `UPSIDE_HOME=/upside2-md`, but your real code lives
under `/workspaces/DynaLab-merge-dynalab`. The benchmark scripts now auto-detect
the mounted checkout — **re-open your terminal** (or re-run the entrypoint) so
the updated `.devcontainer/entrypoint.sh` picks up the right path.

Quick fix without restarting:

```bash
export UPSIDE_HOME=/workspaces/DynaLab-merge-dynalab   # adjust if your folder name differs
cd "$UPSIDE_HOME"
[ -x obj/upside ] || sudo ./install.sh
python benchmarks/scripts/run_matrix.py \
    --matrix benchmarks/matrix.json \
    --output-dir benchmarks/results/smoke \
    --only smoke_chig
```

Check `benchmarks/results/smoke/smoke_chig/work/bench.log` if it still fails.

### Simulation fails instantly with `input.pdb is not a valid filename`

The start scripts need an **absolute** job directory path. If you see a relative
path like `benchmarks/results/.../work/input.pdb` in `bench.log`, update to the
latest benchmark scripts (they now resolve paths automatically) and re-run.

### Tension case fails with `residue -1` in `bench.log`

Pulling benchmarks need anchor + puller rows in `Tension_Simulations.dat`, with
`-1` resolved to the last Cα index. Update to the latest `run_one.py` (matches
`start/Force_Sweep.py`) and re-run only the failed case:

```bash
python benchmarks/scripts/run_matrix.py \
    --matrix benchmarks/matrix.json \
    --output-dir benchmarks/results/local \
    --only local_small_tension
```

Either way, passing an absolute `--output-dir` also works:

```bash
python benchmarks/scripts/run_matrix.py \
    --matrix benchmarks/matrix.json \
    --output-dir /workspaces/DynaLab-merge-dynalab/benchmarks/results/local \
    --tier local
```

### `RuntimeError: UPSIDE_HOME not set`

The benchmark runner needs a valid DynaLab checkout. Either run from inside the
repo or:

```bash
export UPSIDE_HOME=/workspaces/DynaLab-merge-dynalab   # adjust path
```

### Docker build fails on `pip install` step

This sometimes happens because of network flakiness. Just retry:

```bash
sudo docker build -f .devcontainer/Dockerfile -t dynalab-bench:latest .
```

### `bash benchmarks/aws/bootstrap.sh` fails

Read the last 30 lines of output. Common causes:

- Out of disk space — relaunch the EC2 with a bigger root volume (the launch
  script defaults to 60 GB which is enough; if you tweaked it, raise it).
- Conda environment didn't build — the Docker build retries 3× but rare network
  outages can still kill it. Re-run the script; the cached layers make it fast.

### Resuming after disconnect

If your SSH session drops while bootstrap is running, **the script keeps running
on the EC2 box** because it was started with nohup-ish protection. SSH back in and:

```bash
tail -f ~/dynalab_results/bootstrap.log
```

When it stops growing, the matrix is done.

If you want it fully detached up front, run instead:

```bash
nohup bash benchmarks/aws/bootstrap.sh > ~/dynalab_results/bootstrap.log 2>&1 &
disown
```

Then `tail -f ~/dynalab_results/bootstrap.log` to watch progress.

### I terminated the instance but I still see charges

EBS volumes can outlive the instance if "Delete on termination" was off. The
launch script sets it on by default. Double-check in the EC2 console under
**Volumes**.

---

# What this kit does NOT do

This kit deploys benchmarks. It does **not**:

- Stand up an always-on Flask server (use `deploy/` for that).
- Build a multi-user AWS Batch architecture (a future step, justified by the
  numbers this kit produces).
- Set up CloudWatch alarms or budget alerts (do that in the AWS console once,
  separately).

When you have the report, the right next conversation is:

> *"Given these numbers, do we need AWS Batch, or is a single shared EC2 enough
> for our actual usage pattern?"*

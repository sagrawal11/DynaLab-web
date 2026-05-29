# DynaLab Benchmark Kit

This folder contains everything you need to:

1. Measure how DynaLab simulations perform (wall time, CPU usage, memory, output size).
2. Convert those measurements into AWS dollar cost projections.
3. Run the same benchmark on a real EC2 instance so the report is defensible.

The plan, in plain English:

> Run a small validation suite in your dev container (Phases 1–2), then run a
> representative benchmark matrix on one EC2 box (Phase 3). A script turns the
> raw timings into a cost table you can hand to a stakeholder.

You do **not** need AWS Batch, Terraform, or ECR for this kit. One EC2 instance
is enough. Once you have numbers, you can decide whether Batch is worth building.

---

## Table of contents

1. [Where to run each command](#where-to-run-each-command)
2. [What you get at the end](#what-you-get-at-the-end)
3. [Folder layout](#folder-layout)
4. [Do I need to provide PDB files?](#do-i-need-to-provide-pdb-files)
5. [Phase 1 — Local smoke test](#phase-1--local-smoke-test)
6. [Phase 2 — Local mini matrix](#phase-2--local-mini-matrix)
7. [Phase 3 — AWS full matrix](#phase-3--aws-full-matrix)
8. [How to read the report](#how-to-read-the-report)
9. [Matrix reference](#matrix-reference)
10. [Cost model](#cost-model)
11. [Troubleshooting](#troubleshooting)
12. [What this kit does NOT do](#what-this-kit-does-not-do)

---

## Where to run each command

| Command / phase | Run on | Why |
|-----------------|--------|-----|
| Phases 1–2 (`run_matrix.py`, `validate_local.sh`) | **Dev container** | Needs Upside, conda, and `obj/upside` |
| Phase 3 AWS setup (`aws configure`, `launch_ec2.sh`, `terminate.sh`, `collect_results.sh`) | **Your laptop/host terminal** | Needs AWS CLI credentials and your `.pem` key |
| `bootstrap.sh` | **EC2 instance** (via SSH) | Builds Docker and runs the matrix on AWS hardware |

If your repo is mounted at a path other than `/workspaces/DynaLab-merge-dynalab`,
substitute that path everywhere below.

---

## What you get at the end

After each matrix run:

| File | Contents |
|------|----------|
| `benchmarks/results/<run>/status.json` | Pass/fail summary for the whole run |
| `benchmarks/results/<run>/<case_id>/result.json` | Raw metrics for one case |
| `benchmarks/results/<run>/<case_id>/work/bench.log` | Full stdout/stderr from the simulation |
| `benchmarks/results/<run>/results.csv` | All cases in one spreadsheet-friendly table |
| `benchmarks/results/<run>/report.md` | **The deliverable** — human-readable cost report |

**Phase 2 deliverable:** `benchmarks/results/local/report.md` — validates the pipeline.

**Phase 3 deliverable:** `benchmarks/results/aws/report.md` — real EC2 numbers for
your deployment case.

---

## Folder layout

```
benchmarks/
  README.md              ← this file
  matrix.json            ← all benchmark cases (smoke / local / aws tiers)
  pricing.json           ← AWS us-east-1 instance + storage rates
  scripts/
    run_one.py           ← run a single case, write result.json
    run_matrix.py        ← run many cases from matrix.json
    summarize.py         ← build report.md + results.csv from result.json files
    fetch_proteins.py    ← download missing PDBs from RCSB (optional)
    validate_local.sh    ← one-shot Phase 1 smoke + report
    dynalab_paths.py     ← finds repo root (ignores stale UPSIDE_HOME)
  aws/
    launch_ec2.sh        ← start a benchmark EC2 instance
    bootstrap.sh         ← on EC2: install Docker, build image, build Upside (release), run aws tier
    monitor.sh           ← on EC2: one-shot progress report (case status, log tail, sim.run.log)
    collect_results.sh   ← rsync results from EC2 to laptop
    terminate.sh         ← stop the instance (required!)
  proteins/              ← auto-downloaded PDBs land here (usually empty)
  results/               ← all outputs (gitignored)
```

---

## Do I need to provide PDB files?

**No.** Every case in the default `matrix.json` points at PDB files already in the
repo under `example/`. The runner copies them into each job's work directory as
`input.pdb` automatically.

The `benchmarks/proteins/` folder is only used if you add matrix cases that
reference structures not in the repo — `fetch_proteins.py` can download those
from RCSB.

This is different from the Flask web UI, where you upload a PDB through the browser.

---

## Phase 1 — Local smoke test

**Goal:** prove one tiny simulation runs end-to-end and produces `result.json`.

**Time:** ~5–15 minutes (includes one-time Upside build if needed).

**Where:** Dev container.

### 1.1 Open the dev container

In VS Code: `View → Command Palette → Dev Containers: Reopen in Container`.

Without VS Code, from your project folder on the host:

```bash
docker build -f .devcontainer/Dockerfile -t dynalab-dev .
docker run -it --rm \
  -v "$(pwd):/workspaces/DynaLab-merge-dynalab" \
  -e UPSIDE_HOME=/workspaces/DynaLab-merge-dynalab \
  dynalab-dev bash
```

### 1.2 Activate the conda environment

```bash
source /opt/conda/etc/profile.d/conda.sh
conda activate upside2-env
which python    # should contain /opt/conda/envs/upside2-env/
python -c "import tables, numpy, mdtraj; print('OK')"
```

The entrypoint may already activate `upside2-env`; running the commands above is
safe either way.

### 1.3 Build Upside in your mounted repo (one time, ~5 min)

The dev container image contains a clone at `/upside2-md`, but benchmarks run
against **your mounted checkout**. Build Upside there once:

```bash
cd /workspaces/DynaLab-merge-dynalab
[ -x obj/upside ] || sudo ./install.sh
ls -lh obj/upside obj/libupside.so
```

Both files must exist before any benchmark will succeed.

### 1.4 Run the smoke test

**Recommended — one-shot validator** (sets `UPSIDE_HOME`, builds Upside if needed,
runs smoke case, writes report):

```bash
cd /workspaces/DynaLab-merge-dynalab
bash benchmarks/scripts/validate_local.sh
```

**Alternative — manual command:**

```bash
cd /workspaces/DynaLab-merge-dynalab
export UPSIDE_HOME=/workspaces/DynaLab-merge-dynalab

python benchmarks/scripts/run_matrix.py \
    --matrix benchmarks/matrix.json \
    --output-dir benchmarks/results/smoke \
    --only smoke_chig
```

### Success criteria

Last lines should look like:

```
  OK wall=<5–30>s peak_rss=...MB output=...MB
Matrix done: 1/1 OK
```

Failure signs:

- `FAIL wall=0.0s` — instant crash; see [Troubleshooting](#troubleshooting)
- `0/1 OK` — did not pass

If `1/1 OK`, move to Phase 2.

---

## Phase 2 — Local mini matrix

**Goal:** run two short cases (constant-T + tension pulling), produce a cost report,
and validate the full pipeline before spending on AWS.

**Time:** ~90–100 minutes on a typical laptop dev container (~49 min per case).
Not 5–20 minutes — local runs are slow because Docker shares limited CPU.

**Where:** Dev container.

### 2.1 Run the local tier

```bash
cd /workspaces/DynaLab-merge-dynalab
export UPSIDE_HOME=/workspaces/DynaLab-merge-dynalab

python benchmarks/scripts/run_matrix.py \
    --matrix benchmarks/matrix.json \
    --output-dir benchmarks/results/local \
    --tier local
```

This runs **2 cases** sequentially:

| case_id | mode | protein | steps |
|---------|------|---------|-------|
| `local_small_const` | constant-T MD | 1dfn | 50,000 |
| `local_small_tension` | constant-tension pull @ 22 pN | 1dfn | 50,000 |

Each case **replaces** its previous results (work dir wiped, `result.json` overwritten).

### 2.2 Generate the report

```bash
python benchmarks/scripts/summarize.py \
    --results-dir benchmarks/results/local \
    --pricing benchmarks/pricing.json \
    --output benchmarks/results/local/report.md
```

Open `benchmarks/results/local/report.md`.

### Success criteria

- `status.json` shows `"ok_count": 2, "fail_count": 0`
- Both cases have wall times of **many minutes**, not ~1 second
- Report table has 2 rows with `ok: True`

### What Phase 2 numbers mean (and don't mean)

| Column | Trust for pipeline validation? | Trust for AWS planning? |
|--------|-------------------------------|----------------------|
| `wall_minutes` | ✅ Yes (real, on your laptop) | ❌ No — EC2 will differ |
| `seconds_per_1M_steps` | ✅ Rough sanity check | ❌ Wait for Phase 3 |
| `on_demand_cost_usd` / `spot_cost_usd` | ⚠️ Formula check only | ❌ Based on laptop wall time |
| `peak_rss_mb` | ✅ Yes (~120 MB for 1dfn) | ✅ Memory won't be the bottleneck |

Phase 2 proves the kit works. **Phase 3 gives the numbers you cite externally.**

### CPU usage during local runs

Each local case sets `omp_threads: 4`. During the run:

- **First ~30–60 s:** mostly single-threaded Python setup (PDB parsing, config) → looks like 1 core
- **MD phase:** up to 4 OpenMP threads in `obj/upside`
- Docker Desktop may cap container CPUs — check **Settings → Resources → CPUs**

Cases run **one at a time**, not in parallel.

---

## Phase 3 — AWS full matrix

**Goal:** run 9 representative cases on real EC2 hardware and produce the
defensible cost/performance report.

**Where:**

- Steps 3.1–3.2, 3.4–3.5 → **laptop**
- Step 3.3 → **EC2 via SSH**

### Time and cost expectations (realistic)

| Stage | Duration | Notes |
|-------|----------|-------|
| Docker image build (first time) | ~15–25 min | Cached on re-run |
| Upside build inside container | ~3–5 min | First time only; release mode |
| Pre-flight smoke speed-check | <30 s | Aborts if release build looks wrong |
| **16 aws-tier cases** | **~11–15 hours** typical | Sequential; biggest cases are `aws_ladder_ITQN` (~1.5 h) and `aws_ladder_IDP0` (~2 h) |
| **Total EC2 wall time** | **~12–16 hours** typical | Depends on per-core throughput on large proteins |

**Instance launched by default:** `c7i.4xlarge` (16 vCPU = 8 physical + 8 HT, 32 GiB RAM).

| Billing mode | ~$ / hour | ~$ for 14 hr run |
|--------------|-----------|-------------------|
| On-demand | ~$0.71 | ~$10 |
| Spot (`USE_SPOT=1`) | ~$0.22 | ~$3.10 |

> **Critical:** the build must be **release mode** (`-O3 --fast-math`). The build
> system used to default to **debug** (`-Og -g -pg`), which is **5–10× slower**.
> `install.sh` now defaults to release; bootstrap also detects + force-rebuilds
> any stale debug binary. See [Troubleshooting → "Upside runs ~7× slower than expected"](#upside-runs-7x-slower-than-expected) if you ever see single-core
> rates below ~10 steps/sec on `c7i.4xlarge` for 1dfn.

Plan to start the run, **detach with `nohup`**, and check back later. Even on a
fast network your laptop's SSH session is unrelated to job survival.

---

### 3.1 One-time AWS account setup

Skip this section if you already have AWS CLI configured with a key pair and
security group in `us-east-1`.

All commands below run on your **laptop**, not in the dev container.

#### 3.1.1 Create an IAM user

1. AWS Console → **IAM → Users → Create user**
2. Name: `dynalab-bench`
3. Attach **AdministratorAccess** (you can restrict later)
4. **Security credentials → Create access key → CLI** → download CSV

#### 3.1.2 Install and configure AWS CLI

```bash
# macOS
brew install awscli

# verify
aws --version
aws configure
# AWS Access Key ID:     <from CSV>
# AWS Secret Access Key: <from CSV>
# Default region name:   us-east-1
# Default output format: json

aws sts get-caller-identity    # should print your account ID
```

#### 3.1.3 Create an SSH key pair

```bash
aws ec2 create-key-pair \
    --region us-east-1 \
    --key-name dynalab-bench \
    --query 'KeyMaterial' --output text > ~/.ssh/dynalab-bench.pem
chmod 600 ~/.ssh/dynalab-bench.pem
```

#### 3.1.4 Create a security group (SSH from your IP only)

```bash
MY_IP=$(curl -s https://checkip.amazonaws.com)

aws ec2 create-security-group \
    --region us-east-1 \
    --group-name dynalab-bench-sg \
    --description "SSH from my laptop for DynaLab benchmarks"

aws ec2 authorize-security-group-ingress \
    --region us-east-1 \
    --group-name dynalab-bench-sg \
    --protocol tcp --port 22 \
    --cidr ${MY_IP}/32
```

If your IP changes (different Wi‑Fi), re-run the `authorize-security-group-ingress`
command with the new IP, or temporarily use your current `/32`.

---

### 3.2 Launch the EC2 instance

From your **laptop**, in the repo root:

```bash
cd /path/to/DynaLab-merge-dynalab

# recommended: Spot saves ~70% vs on-demand
USE_SPOT=1 bash benchmarks/aws/launch_ec2.sh
```

Default settings (override with env vars):

| Variable | Default | Meaning |
|----------|---------|---------|
| `INSTANCE_TYPE` | `c7i.4xlarge` | 16 vCPU — fits all matrix cases including parallel replicas |
| `REGION` | `us-east-1` | |
| `USE_SPOT` | `0` | Set to `1` for Spot pricing |
| `ROOT_VOLUME_GB` | `60` | Enough for Docker image + results |

Other examples:

```bash
# on-demand c7i.4xlarge (no Spot)
bash benchmarks/aws/launch_ec2.sh

# Spot c7i.2xlarge (cheaper, less RAM — still OK for most cases)
USE_SPOT=1 INSTANCE_TYPE=c7i.2xlarge bash benchmarks/aws/launch_ec2.sh
```

The script prints:

```
Instance ID:  i-0abc...
Public IP:    3.92.xx.xx
SSH command:  ssh -i ~/.ssh/dynalab-bench.pem ec2-user@3.92.xx.xx
```

State is saved to `benchmarks/aws/.last_instance.env` for `terminate.sh` and
`collect_results.sh`.

Wait ~30 seconds, then test SSH:

```bash
ssh -i ~/.ssh/dynalab-bench.pem ec2-user@<public-ip>
```

Type `yes` on first connect. `exit` to return to your laptop.

---

### 3.3 Push code and run bootstrap

#### 3.3.1 Push your local checkout (recommended)

**Important:** rsync your current repo so EC2 gets all benchmark fixes (path
resolution, tension `.dat` writing, etc.).

From your **laptop** (second terminal):

```bash
cd /path/to/DynaLab-merge-dynalab

rsync -avz \
    --exclude='.git' \
    --exclude='obj/' \
    --exclude='benchmarks/results' \
    -e "ssh -i ~/.ssh/dynalab-bench.pem" \
    ./ ec2-user@<public-ip>:~/DynaLab-merge-dynalab/
```

Do **not** rsync `obj/` — Upside is built fresh on EC2 inside the container.

#### 3.3.2 Alternative: clone from GitHub

Only if your fork is pushed with the latest benchmark fixes:

```bash
ssh -i ~/.ssh/dynalab-bench.pem ec2-user@<public-ip>
git clone https://github.com/<you>/DynaLab-merge-dynalab.git ~/DynaLab-merge-dynalab
```

#### 3.3.3 Run bootstrap on EC2

SSH into the instance:

```bash
ssh -i ~/.ssh/dynalab-bench.pem ec2-user@<public-ip>
cd ~/DynaLab-merge-dynalab
```

**If your laptop might sleep or disconnect**, run detached (recommended):

```bash
mkdir -p ~/dynalab_results/_logs
nohup bash benchmarks/aws/bootstrap.sh \
    > ~/dynalab_results/_logs/bootstrap.log 2>&1 &
disown
tail -f ~/dynalab_results/_logs/bootstrap.log
```

Press `Ctrl+C` to stop watching — the job keeps running. Reconnect later with
the same `tail -f` command.

**If you will stay connected the whole time:**

```bash
bash benchmarks/aws/bootstrap.sh
```

#### What bootstrap does

1. Installs Docker + git (~1 min)
2. Builds dev container image (~15–25 min first time; cached after)
3. Builds Upside **release mode** in the mounted repo (force-rebuild if a stale
   debug binary is present; ~3–5 min first time)
4. **Pre-flight smoke speed-check** — runs `smoke_chig` and checks wall time is
   under `SMOKE_MAX_SECONDS` (default 60 s). If the binary is somehow still
   debug, bootstrap aborts before you commit to the full matrix.
5. Runs `fetch_proteins.py` (no-op for default matrix — all PDBs in `example/`)
6. Runs **`run_matrix.py --tier aws`** (16 cases, sequential) with `PYTHONUNBUFFERED=1`
   so `matrix.log` shows live progress
7. Runs `summarize.py` → writes `~/dynalab_results/report.md`

Logs: `~/dynalab_results/_logs/bootstrap.log`, `_logs/upside-build.log`,
`_logs/smoke.log`, `_logs/matrix.log`.

Monitor matrix progress (single command):

```bash
bash benchmarks/aws/monitor.sh
```

That prints the pass/fail summary, what case is currently running (with the
`sim.run.log` step counter), the matrix log tail, and the report preview if it
exists. You can run it any time, from a second SSH session if you want.

Lower-level monitoring:

```bash
cat ~/dynalab_results/status.json           # written only when the matrix finishes
tail -f ~/dynalab_results/_logs/matrix.log  # live matrix output
ls -lh ~/dynalab_results/*/result.json      # per-case completion (one file per finished case)
```

#### Bootstrap environment variables (optional)

```bash
# run only one case on EC2
MATRIX_ARGS="--only aws_baseline_small" bash benchmarks/aws/bootstrap.sh

# override results directory (recommended when re-running on a box with stale state)
RESULTS_DIR=$HOME/dynalab_results_v2 bash benchmarks/aws/bootstrap.sh

# force a clean Upside rebuild even if obj/upside exists
FORCE_REBUILD=1 bash benchmarks/aws/bootstrap.sh

# skip the smoke speed-check (rarely needed; saves ~30 s)
SKIP_SMOKE=1 bash benchmarks/aws/bootstrap.sh
```

| Variable | Default | Meaning |
|----------|---------|---------|
| `MATRIX_TIER` | `aws` | Which tier from `matrix.json` to run |
| `MATRIX_ARGS` | (empty) | Extra args passed to `run_matrix.py` |
| `RESULTS_DIR` | `~/dynalab_results` | Where results are written on EC2 |
| `IMAGE_TAG` | `dynalab-bench:latest` | Docker image tag to build/use |
| `OMP_THREADS` | `$(nproc)` | Default `OMP_NUM_THREADS` in the container (per-case `omp_threads` in `matrix.json` still overrides) |
| `UPSIDE_BUILD_TYPE` | `release` | `release` (default, `-O3`) or `debug` (`-Og -pg`, 5–10× slower; profiling only) |
| `FORCE_REBUILD` | `0` | `1` to force a clean Upside rebuild |
| `SKIP_SMOKE` | `0` | `1` to skip the pre-flight speed-check |
| `SMOKE_MAX_SECONDS` | `60` | Hard ceiling for the smoke wall time before bootstrap aborts |

---

### 3.4 Download results

Back on your **laptop**, after bootstrap finishes:

**Option A — helper script** (reads IP from `.last_instance.env`):

```bash
cd /path/to/DynaLab-merge-dynalab
bash benchmarks/aws/collect_results.sh
```

**Option B — manual rsync:**

```bash
mkdir -p benchmarks/results/aws
rsync -avz \
    -e "ssh -i ~/.ssh/dynalab-bench.pem" \
    ec2-user@<public-ip>:~/dynalab_results/ \
    benchmarks/results/aws/
```

Open **`benchmarks/results/aws/report.md`**.

---

### 3.5 Terminate the instance (required)

An idle EC2 instance keeps billing. From your **laptop**:

```bash
bash benchmarks/aws/terminate.sh
```

Type the instance ID when prompted to confirm.

Verify in AWS Console → **EC2 → Instances** → state is **Terminated**.

Also check **EC2 → Volumes** — no orphaned EBS volumes should remain (the launch
script sets DeleteOnTermination on the root volume).

---

## How to read the report

Example header:

```
Cases reported: 16 (ok: 16, fail: 0)
Total compute on-demand cost (this run): $X.XX
Total wall time (sum across cases): XXX min
```

### Column guide

| Column | Meaning |
|--------|---------|
| `wall_minutes` | **Real** elapsed time for that case on the machine that ran it |
| `seconds_per_1M_steps` | `wall_seconds ÷ (duration / 1e6)` — throughput metric |
| `steps_per_second` | Inverse of above, per case step count |
| `peak_rss_mb` | Peak RAM used — if ≪ instance RAM, memory is not your bottleneck |
| `output_mb` | Disk written under the work directory (trajectory + logs) |
| `instance_assumed` | EC2 type used for **cost projection** (from matrix.json) |
| `vcpus` | vCPU count of `instance_assumed` |
| `vcpu_hours` | `vcpus × wall_hours` — capacity accounting |
| `on_demand_cost_usd` | `(wall_hours) × (on-demand $/hr for instance_assumed)` |
| `spot_cost_usd` | Same, using Spot rate from `pricing.json` |
| `sweep_subjobs` | For force sweeps: number of independent sub-jobs (cost scales with this on Batch) |

### Interpreting dollar amounts

Dollar columns answer: *"If this wall time happened on the listed instance type
in us-east-1, what would compute cost?"*

They are **not** your AWS bill unless you actually ran on that instance type at
those rates for exactly that duration. Phase 3 runs on `c7i.4xlarge` by default
but each case may assume a different type for cost comparison (see matrix table).

### Key comparisons to draw from Phase 3

1. **Per-core throughput by protein size:** compare `aws_baseline_small` (1dfn,
   38 res), `aws_baseline_medium` (1ubq, 76 res), `aws_baseline_large`
   (2qke_mon, 216 res) → how does `seconds_per_1M_steps` scale with residue
   count? These cases use `omp_threads=1` because Upside's hot loop
   parallelizes across **systems**, not within one trajectory — see
   `src/main.cpp` near line 917. So 1 system = 1 core, regardless of `OMP_NUM_THREADS`.
2. **OMP scaling (systems-level parallelism):** compare `aws_remd4`, `aws_remd8`,
   `aws_remd16` → REMD has N systems, OMP runs them on N threads. Does going from
   8 → 16 (i.e. across the HT boundary on `c7i.4xlarge`) actually help?
3. **Process-level scaling:** compare `aws_indep8` vs `aws_indep16` → 8 vs 16
   completely independent Upside processes saturating the box. This is the
   closest analogue to running many Phase-1 jobs concurrently on a single host.
4. **Force sweep (production-like):** `aws_force_sweep_8` runs 8 sub-jobs with
   `max_parallel=8` → directly models the Phase-1 sweep cost on a single EC2
   vs hypothetical AWS Batch.
5. **Pulling overhead:** `aws_tension_medium` vs `aws_baseline_medium` (same
   1ubq, same steps) → cost of constant-tension on top of constant-T.

### Extrapolating to production runs

Once you have `seconds_per_1M_steps` from the baseline case on EC2:

```
estimated_wall_hours = (production_steps / 1e6) × seconds_per_1M_steps / 3600
estimated_spot_cost  = estimated_wall_hours × spot_rate_for_instance
```

For a force sweep with N sub-jobs on **one EC2 box** (bounded parallelism P):

```
wall_hours ≈ ceil(N / P) × single_job_wall_hours
total_cost ≈ wall_hours × instance_hourly_rate    # one box the whole time
```

On **AWS Batch** (all N jobs in parallel):

```
wall_hours ≈ single_job_wall_hours
total_cost ≈ N × single_job_wall_hours × instance_hourly_rate
```

That comparison is the main deployment decision the report enables.

---

## Matrix reference

All cases live in `benchmarks/matrix.json`. PDBs come from `example/` — no upload needed.

### Tier summary

| Tier | Cases | Purpose | Where to run |
|------|-------|---------|--------------|
| `smoke` | 1 | Wiring check (~5k steps, < 30 s) | Dev container or as pre-flight inside bootstrap |
| `local` | 2 | Pipeline validation (~50k steps, ~5–60 min total in release mode) | Dev container |
| `aws` | 16 | Defensible performance/cost data | EC2 via bootstrap |

### Full case list (current matrix)

All aws-tier cases run on the same `c7i.4xlarge` (16 vCPU = 8 physical + 8 HT).
`n_residues` below is the per-MODEL Cα count (the relevant residue number for
Upside; counted by `count_residues()` in `run_one.py`).

**Size-ladder cases** — single-replica constant-T across protein sizes; this is the
curve you extrapolate from to estimate any other simulation's cost on bigger proteins:

| case_id | protein | n_residues | steps | rough wall (c7i.4xlarge) | what it measures |
|---------|---------|-----------:|------:|-------------------------:|------------------|
| `aws_baseline_chig`   | chig     |   10 |  50,000 | ~2 min  | tiny-protein per-core throughput |
| `aws_ladder_1aie`     | 1aie     |   31 | 100,000 | ~25 min | small NMR ensemble (first model used) |
| `aws_baseline_small`  | 1dfn     |   60 | 100,000 | ~50 min | small dimer baseline |
| `aws_baseline_long`   | 1dfn     |   60 | 200,000 | ~100 min | steady-state validation (no drift?) |
| `aws_baseline_medium` | 1ubq     |   76 |  50,000 | ~33 min | medium single chain |
| `aws_baseline_large`  | 2qke_mon |  108 |  20,000 | ~18 min | medium-large |
| `aws_ladder_ITQN`     | ITQN     |  503 |  15,000 | ~60–90 min | large single chain |
| `aws_ladder_IDP0`     | IDP0     | 1024 |   8,000 | ~70–120 min | very large (≈1000 residues) |

**Parallelism cases** — same 1dfn protein, varying how many systems / processes run on the box:

| case_id | mode | n_replicas | omp_threads | what it measures |
|---------|------|-----------:|------------:|------------------|
| `aws_remd4`           | REMD     |  4 |  4 | OMP scaling (4 systems) |
| `aws_remd8`           | REMD     |  8 |  8 | OMP scaling (8 systems, 8 physical cores) |
| `aws_remd16`          | REMD     | 16 | 16 | OMP scaling at HT boundary |
| `aws_indep8`          | 8 indep  |  8 |  1 | Process-level parallelism (8 cores) |
| `aws_indep16`         | 16 indep | 16 |  1 | Process-level parallelism (16 cores) |

**Pulling / sweep cases:**

| case_id | mode | protein | n_residues | what it measures |
|---------|------|---------|-----------:|------------------|
| `aws_tension_medium`  | tension @ 22 pN | 1ubq | 76 | tension overhead vs constant-T at same N |
| `aws_velocity_medium` | velocity        | 1ubq | 76 | velocity-clamp overhead vs tension |
| `aws_force_sweep_8`   | 4 forces × 2 reps, max_parallel=8 | 1dfn | 60 | Phase-1 sweep on one box |

> Cases with `n_replicas=1` are deliberately single-thread. Upside parallelizes
> across systems, not within a single trajectory, so for 1 system the inner
> loop only ever uses 1 core. Setting `omp_threads > 1` on those cases wastes
> the rest of the instance — we kept their `duration` capped so each case finishes
> in a bounded time (and the very-large ones get fewer steps to keep wall time
> reasonable).

> **Note on 1tup (skipped):** 1tup has DNA chains (E, F). Upside is a protein-only
> force field, so 1tup was excluded from the ladder to keep the residue-count vs
> cost story clean. If you need a real ~500-residue protein-only data point, ITQN
> (503 residues, single chain) is the one.

### How to extrapolate from the ladder

Once the report is in hand, fit `seconds_per_1M_steps` vs `n_residues` from the
ladder cases. That gives you a per-residue cost model:

```
estimated_seconds_for_N_steps(protein_N_residues) ≈
  f(N_residues) * (N_steps / 1e6)
```

You can then estimate the cost of *any other* simulation type by combining
that throughput with the relevant multiplier from the matrix (e.g. tension is
~1.0× constant-T at the same N; REMD-4 uses ~4 cores; etc.). See the
"Cost model" section for the formulas.

### Running subsets

```bash
# one case
python benchmarks/scripts/run_matrix.py \
    --matrix benchmarks/matrix.json \
    --output-dir benchmarks/results/aws \
    --only aws_baseline_small

# whole tier
python benchmarks/scripts/run_matrix.py \
    --matrix benchmarks/matrix.json \
    --output-dir benchmarks/results/aws \
    --tier aws

# skip a case
python benchmarks/scripts/run_matrix.py ... --tier aws --skip aws_remd16
```

Re-running a case **wipes and replaces** its previous `result.json`.

### Adding a custom case

Copy an existing entry in `matrix.json`. Required fields:

```json
{
  "case_id": "my_case",
  "tier": "aws",
  "mode": "constant",
  "pdb_id": "1dfn",
  "pdb_source": "example/01.GettingStarted/pdb/1dfn.pdb",
  "duration": 1000000,
  "frame_interval": 200,
  "temperature": "0.85",
  "omp_threads": 8,
  "instance_assumed": "c7i.2xlarge"
}
```

For `tension` / `velocity` modes, also set `tension_pn`, `anchor_residue` (default 0),
and `pull_residue` (-1 = last Cα, resolved automatically).

For `force_sweep`, use `forces_pn`, `n_replicas`, `max_parallel`, `sim_type`.

If `pdb_source` is not in the repo, run `python benchmarks/scripts/fetch_proteins.py`
first or place the file in `benchmarks/proteins/`.

---

## Cost model

Rates are in `benchmarks/pricing.json` (approximate us-east-1, May 2026).
Verify against the [AWS Pricing Calculator](https://calculator.aws/) before
quoting externally.

### Measured fields (real)

- `wall_seconds`, `cpu_user_seconds`, `cpu_sys_seconds`
- `peak_rss_mb`, `output_mb`
- `steps_per_second`, `seconds_per_1M_steps`

### Projected fields (computed)

```
wall_hours            = wall_seconds / 3600
vcpu_hours            = vcpus × wall_hours
on_demand_cost_usd    = wall_hours × on_demand_per_hour   # for instance_assumed
spot_cost_usd         = wall_hours × spot_per_hour
ebs_month_usd         = (output_bytes / 1e9) × ebs_gp3_per_gb_month
s3_month_usd          = (output_bytes / 1e9) × s3_standard_per_gb_month
```

Storage costs are **monthly** — multiply by months you retain artifacts.

Spot prices fluctuate; treat the Spot column as an approximate floor.

Edit `benchmarks/pricing.json` when rates change.

---

## Troubleshooting

### All aws cases fail instantly (`0/9 OK`, `wall=0.3s`)

Usually **`obj/upside` was never built** on EC2. Check the bootstrap log for:

```
cd: obj: No such file or directory
CMake Error: The source directory "/workspaces/src" does not exist
```

rsync excludes `obj/` (expected). `install.sh` must create `obj/` before building.
Update to the latest `install.sh`, rsync to EC2, and re-run bootstrap:

```bash
# laptop
rsync -avz --exclude='.git' --exclude='obj/' --exclude='benchmarks/results' \
    -e "ssh -i ~/.ssh/dynalab-bench.pem" \
    ./ ec2-user@<public-ip>:~/DynaLab-merge-dynalab/

# EC2 (Docker image already built — bootstrap skips rebuild)
cd ~/DynaLab-merge-dynalab
bash benchmarks/aws/bootstrap.sh
```

You should see `[bootstrap] Upside build OK` before the matrix starts.

### `obj/upside: No such file or directory`

Build Upside in your mounted repo (not the image clone):

```bash
cd /workspaces/DynaLab-merge-dynalab
sudo ./install.sh
```

### `can't open file '/upside2-md/start/Single_Replica.py'` or `FAIL wall=0.0s`

Stale `UPSIDE_HOME`. The benchmark scripts auto-detect the mounted checkout, but
you still need `obj/upside` built in that tree (step 1.3).

Quick fix:

```bash
export UPSIDE_HOME=/workspaces/DynaLab-merge-dynalab
[ -x obj/upside ] || sudo ./install.sh
bash benchmarks/scripts/validate_local.sh
```

Check `bench.log` — the `cmd=` line should reference `/workspaces/.../start/`,
not `/upside2-md/`.

### `input.pdb is not a valid filename` (instant fail, ~1 s wall time)

The start scripts need an **absolute** job directory. Update to the latest
`run_one.py` (paths are resolved automatically). Re-run the failed tier.

### Tension case fails with `residue -1`

Pulling cases need anchor + puller rows in `Tension_Simulations.dat`, with
`pull_residue: -1` resolved to the last Cα index. Update to the latest
`run_one.py` and re-run:

```bash
python benchmarks/scripts/run_matrix.py \
    --matrix benchmarks/matrix.json \
    --output-dir benchmarks/results/local \
    --only local_small_tension
```

A correct `Tension_Simulations.dat` looks like:

```
residue tension_x tension_y tension_z
0 0.0 0.0 -0.531401
59 0.0 0.0 0.531401
```

### Only one CPU core seems busy

For **single-replica** cases (`n_replicas=1`, e.g. all the `aws_baseline_*`
cases), this is **expected**. Upside parallelizes across `systems` only —
`#pragma omp parallel for` over `for (ns=0; ns<systems.size(); ++ns)` in
`src/main.cpp` near line 917 — and with one system there's nothing to
parallelize. Setting `OMP_NUM_THREADS > 1` does not help; the matrix sets
`omp_threads: 1` on those cases on purpose.

If you want all 16 vCPUs busy, run the cases that actually have N systems:
`aws_remd8` / `aws_remd16` (OMP) or `aws_indep8` / `aws_indep16` / `aws_force_sweep_8`
(separate processes).

### Upside runs ~7× slower than expected

> `~/dynalab_results/_logs/matrix.log` shows `~2–3 steps/sec` on 1dfn, the
> first case takes 30+ hours, and CloudWatch CPU sits at ~6%.

**Cause:** Upside was built with `DEBUG=ON` (the historical CMake default),
which compiles with `-Og -g -pg` (gprof instrumentation) instead of
`-O3 --fast-math`. That's 5–10× slower for the MD hot loop.

**Detect:**

```bash
cat obj/.upside_build_type   # should print "release"
nm -an obj/upside | grep -E 'mcount|__gmon_start__'   # release: no matches
```

If `obj/.upside_build_type` is missing, the binary predates the marker —
treat it as suspect and rebuild.

**Fix:** rebuild release mode. On EC2, in the repo:

```bash
sudo rm -rf obj
sudo docker run --rm \
    -v "$HOME/DynaLab-merge-dynalab:/workspaces/DynaLab-merge-dynalab" \
    -e UPSIDE_BUILD_TYPE=release \
    dynalab-bench:latest \
    bash -lc 'cd /workspaces/DynaLab-merge-dynalab && \
              source /opt/conda/etc/profile.d/conda.sh && \
              conda activate upside2-env && ./install.sh'
```

Or just rerun `bootstrap.sh` — it detects stale debug builds and force-rebuilds.

### Docker Desktop CPU cap (local only)

On macOS, Docker Desktop may cap container CPUs — check Settings → Resources.

### `aws: command not found` or credentials errors

Install AWS CLI on your **laptop** (not dev container) and run `aws configure`.

### Security group / key not found on launch

Add `--region us-east-1` to all `aws ec2` commands if your default region differs.

Re-create resources from §3.1.3–3.1.4 if needed.

### Docker build fails on EC2

Network flake during conda env create. Re-run `bootstrap.sh` — cached Docker
layers make retries fast.

If out of disk: relaunch with `ROOT_VOLUME_GB=100`.

### SSH disconnected during bootstrap

**Foreground** `bash benchmarks/aws/bootstrap.sh` stops if the SSH session dies.

If you used **`nohup`** (recommended in §3.3.3), the job continues. Reconnect:

```bash
ssh -i ~/.ssh/dynalab-bench.pem ec2-user@<public-ip>
tail -f ~/dynalab_results/_logs/bootstrap.log
```

When the log stops growing, check `cat ~/dynalab_results/status.json`.

### Partial aws matrix — rerun failed cases only

```bash
# on EC2, inside the repo, after bootstrap's Docker image exists:
sudo docker run --rm \
    -v "$HOME/DynaLab-merge-dynalab:/workspaces/DynaLab-merge-dynalab" \
    -v "$HOME/dynalab_results:/results" \
    -e UPSIDE_HOME=/workspaces/DynaLab-merge-dynalab \
    -e PYTHONUNBUFFERED=1 \
    dynalab-bench:latest \
    bash -lc 'source /opt/conda/etc/profile.d/conda.sh && conda activate upside2-env && \
      python benchmarks/scripts/run_matrix.py \
        --matrix benchmarks/matrix.json --output-dir /results \
        --only aws_tension_medium && \
      python benchmarks/scripts/summarize.py \
        --results-dir /results --pricing benchmarks/pricing.json \
        --output /results/report.md'
```

### Charges after terminate

Check EC2 → Volumes for orphaned EBS volumes. The launch script sets
DeleteOnTermination on the root volume by default.

---

## What this kit does NOT do

- **Always-on Flask web server** — see `deploy/` for that
- **AWS Batch / multi-user architecture** — a follow-on decision after you
  have Phase 3 numbers
- **CloudWatch alarms or budget alerts** — set those up separately in AWS Console
- **Tamarind API cost** — external; not measured here

When Phase 3 is done, the key question is:

> *Given these EC2 numbers, do we need AWS Batch for force sweeps, or is a
> shared EC2 instance enough for our usage pattern?*

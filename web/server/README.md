# Upside2 Local Web Server

A minimal Flask backend that lets you submit Upside2 simulations from a localhost browser UI and run them on your own machine.

## Run

From inside the Dev Container, with the `upside2-env` conda environment active (it should be activated automatically by your shell — see `.bashrc`):

```bash
conda activate upside2-env   # safe even if it's already active
cd /workspaces/DynaLab-merge-dynalab/web/server
python app.py
```

Then open **http://localhost:5001/** in your browser (redirects to the DynaLab UI at `/intermediate/`).

All Python dependencies (Flask, mdtraj, scikit-learn, matplotlib, etc.) are baked into `upside2-env` via `.devcontainer/environment.yml`, so no extra `pip install` step is needed. If you build on a non-conda system (e.g. plain Linux EC2 without conda), `requirements.txt` lists what pip would need.

### Sanity check before running

```bash
which python                     # should contain /envs/upside2-env/
python -c "import numpy, tables, flask, sklearn, matplotlib" && echo OK
```

If `which python` shows a base conda path (e.g. `/opt/conda/bin/python`) instead of `/opt/conda/envs/upside2-env/bin/python`, run `conda activate upside2-env` first.

## What it does

- Serves the DynaLab static UI under `/intermediate/`; **`GET /` redirects there** (default landing page).
- `POST /api/jobs` — accepts a PDB upload + JSON config, runs the simulation as a subprocess, returns a `job_id`.
- `GET /api/jobs/<job_id>` — returns status, current step, and total steps (parsed from the simulation log).
- `GET /api/jobs/<job_id>/download` — downloads the completed trajectory: a single `.run.up` for one replica, or a zip of all replica files for multi-replica constant-T or replica-exchange jobs.
- `POST /api/jobs/<job_id>/analyze` — body `{"analyses": ["rg", "rmsd", ...]}`; runs `analysis/dynalab_analysis.py`. For a single trajectory, PNGs land in `jobs/<job_id>/analysis/` and `results.json` is a flat map. For **multiple trajectories** (independent replicas or REMD ladder files), each is analyzed under `analysis/replicas/<label>/`, the API response includes `multi_replica`, optional `ensemble_kind` (`independent` or `replica_exchange`), `replicas`, and an `aggregate` section (means of numeric ``stats`` fields only; plots are not averaged).
- `GET /api/jobs/<job_id>/analysis/<filename>` — serves an analysis PNG.
- `DELETE /api/jobs/<job_id>` — removes a job's working directory.

Each job lives in `web/server/jobs/<job_id>/` and contains the input PDB, config, log, simulation outputs, and (after analysis) generated plots under `analysis/`.

## Supported simulation types

The server invokes the existing scripts in `start/`:

| Config | Script invoked |
|---|---|
| `simulationMode: "constant"`, `enablePulling: false` | `start/Single_Replica.py` (constant-T MD) |
| `simulationMode: "replica"`, `enablePulling: false` | `start/Replica_Exchange.py` (replica exchange; outputs under `outputs/remd/`) |
| `enablePulling: true` with AFM entries | `start/Pulling_Simulations.py` (velocity-clamp) |
| `enablePulling: true` with tension entries | `start/Pulling_Simulations.py` (constant tension) |

Replica exchange cannot be combined with pulling; the API returns `400` if both are requested.

For plain MD, `basicIndependentReplicas` (1–32, default 1) is passed as a 10th argument to `Single_Replica.py`: values greater than 1 run that many independent simulations with distinct random seeds; outputs go to `outputs/sim_r{j}/` and download is a zip of all `.run.up` files. Those replicas run **concurrently** (thread pool), up to `min(replica_count, os.cpu_count())` simultaneous `obj/upside` processes. Override the cap with environment variable `DYNALAB_REPLICA_MAX_PARALLEL` (integer ≥ 1). Restart (`continue_sim` true) stays a single sequential run.

**Restraints:** `distanceLockPairs` and optional `restraintGroupRigidSpring` (default `true`: server uses a high `pair_spring` constant for near-rigid pairs); manual pair-spring text can still be used. These produce `spring-pair-xyz.dat` in the job directory; the server passes that filename to the start scripts as ``pair_spring``. Other restraint types in the UI (walls, nails, fixed springs) are not yet wired through this backend.

Membrane sliders in the UI are not applied to web jobs. Constant-T `Single_Replica.py` runs use no implicit membrane from that card. `Pulling_Simulations.py` uses a fixed default membrane thickness in its Upside config (see `start/Pulling_Simulations.py`).

## Post-processing analyses

Once a simulation finishes, the UI exposes a list of analyses extracted from `analysis/Dynalab_Analysis_Final (2).ipynb` and packaged into `analysis/dynalab_analysis.py`:

| Key | What it computes |
|---|---|
| `rg` | Radius of gyration vs. frame |
| `rmsd` | RMSD relative to the initial structure |
| `rmsf` | Per-residue RMSF (backbone CA) |
| `e2e` | End-to-end distance (first CA &harr; last CA) |
| `hbonds` | Backbone H-bond count per frame (Baker-Hubbard) |
| `salt_bridges` | CB-CB ionic contacts between charged residues (CG approximation) |
| `shape` | Gyration-tensor descriptors (asphericity, acylindricity, anisotropy) |
| `cross_corr` | Pairwise CA dynamic cross-correlation matrix |
| `ss` | Secondary structure (helix/sheet/coil) — uses `mkdssp` if installed, otherwise a pure-Python H-bond-based fallback |
| `pca` | PCA on CA coordinates with configurable number of components |
| `force_ext` | Force vs. extension curves (pulling sims only) |
| `contacts` | CA-CA contact frequency map (cutoff 4.5 Å) |

### Secondary structure: DSSP

The `ss` analysis prefers the canonical `mkdssp` binary, which is now built from source during the Dev Container image build (see `.devcontainer/install_dssp.sh`). After a clean rebuild it lives at `/usr/local/bin/mkdssp` and gets picked up automatically.

If for some reason mkdssp isn't available (e.g. you're running outside the Dev Container), the analysis falls back to a pure-Python H-bond-based H/E/C assignment via `mdtraj.kabsch_sander` — slightly less precise, but no binary required. The label on the plot tells you which method was used.

### CLI usage

The same module is runnable from the command line, including per-analysis params:

```bash
# Basic
python analysis/dynalab_analysis.py path/to/sim.run.up output_dir rg rmsd e2e

# PCA with 5 components
python analysis/dynalab_analysis.py path/to/sim.run.up output_dir pca:n_components=5 rg
```

It writes one PNG per analysis plus a `results.json` with stats.

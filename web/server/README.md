# Upside2 Local Web Server

A minimal Flask backend that lets you submit Upside2 simulations from a localhost browser UI and run them on your own machine.

## Run

From inside the Dev Container, with the `upside2-env` conda environment active (it should be activated automatically by your shell — see `.bashrc`):

```bash
conda activate upside2-env   # safe even if it's already active
cd /workspaces/DynaLab-merge-dynalab/web/server
python app.py
```

Then open http://localhost:5001/intermediate/ in your browser.

All Python dependencies (Flask, mdtraj, scikit-learn, matplotlib, etc.) are baked into `upside2-env` via `.devcontainer/environment.yml`, so no extra `pip install` step is needed. If you build on a non-conda system (e.g. plain Linux EC2 without conda), `requirements.txt` lists what pip would need.

### Sanity check before running

```bash
which python                     # should contain /envs/upside2-env/
python -c "import numpy, tables, flask, sklearn, matplotlib" && echo OK
```

If `which python` shows a base conda path (e.g. `/opt/conda/bin/python`) instead of `/opt/conda/envs/upside2-env/bin/python`, run `conda activate upside2-env` first.

## What it does

- Serves the existing static UIs at `/intermediate/` and `/advanced/`.
- `POST /api/jobs` — accepts a PDB upload + JSON config, runs the simulation as a subprocess, returns a `job_id`.
- `GET /api/jobs/<job_id>` — returns status, current step, and total steps (parsed from the simulation log).
- `GET /api/jobs/<job_id>/download` — downloads the completed `.run.up` trajectory.
- `POST /api/jobs/<job_id>/analyze` — body `{"analyses": ["rg", "rmsd", "rmsf", "e2e", "contacts"]}`; runs the requested analyses (powered by `analysis/dynalab_analysis.py`), saves PNGs into `jobs/<job_id>/analysis/`, returns image URLs and stats.
- `GET /api/jobs/<job_id>/analysis/<filename>` — serves an analysis PNG.
- `DELETE /api/jobs/<job_id>` — removes a job's working directory.

Each job lives in `web/server/jobs/<job_id>/` and contains the input PDB, config, log, simulation outputs, and (after analysis) generated plots under `analysis/`.

## Supported simulation types

The server invokes the existing scripts in `start/`:

| Config | Script invoked |
|---|---|
| `enablePulling: false` | `start/Single_Replica.py` (constant-T MD) |
| `enablePulling: true` with AFM entries | `start/Pulling_Simulations.py` (velocity-clamp) |

Membrane and restraint options from the UI are ignored by this minimal backend.

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

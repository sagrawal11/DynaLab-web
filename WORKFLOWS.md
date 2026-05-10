# DynaLab Workflows

End-to-end recipes for the four phases of the cryptic-epitope binder pipeline.

The web UI ([web/intermediate/](web/intermediate/)) wraps each step. CLIs are
provided for power users and CI; everything you can do from the UI you can
also do from a terminal.

---

## Phase 0 — Sanity check (constant-T sim)

Confirm Upside, the dev container, and the Flask server all talk to each other.

```bash
# 1. Start the server (inside the dev container, with upside2-env active)
cd web/server
python app.py     # http://127.0.0.1:5001/  (opens DynaLab UI; redirects to /intermediate/)
```

Upload any small PDB, leave all defaults, hit **Run Simulation**. When the
progress bar reaches 100%, you'll see the trajectory download button. Done.

CLI equivalent:

```bash
python start/Single_Replica.py myprotein /tmp/job1 sim 100000 200 False 0.85 None
```

---

## Phase 1 — Find cryptic epitopes (force sweep)

The point of pulling: figure out which residues become solvent-exposed
specifically when the protein is under tension.

### From the UI

1. Toggle **Pulling** + **Force Sweep**.
2. Pick the sweep mode (constant-tension matches the centrifuge experiment).
3. Forces: e.g. `14,18,22,26,30,34,38` pN — these match the radial zones the
   centrifuge can deliver.
4. Replicas: 2 (more if you can spare CPU).
5. **Run**. Each force × replica becomes a sub-job; you'll see them tick
   off as completed.
6. When the sweep finishes, scroll down and hit
   **Compute Epitope Candidates**. This produces three plots:
   * `EpitopeCandidates.png` — ranked residue list (the headline result).
   * `BurialSweep.png`        — exposure heat-map over force × residue.
   * `IntermediateClustering.png` — K-means in contact-PC space; the
     representative frames are saved as PDBs to
     `web/server/jobs/<job_id>/intermediates/`.

### From the CLI

```bash
python start/Force_Sweep.py \
    --pdb /path/to/protein.pdb \
    --sweep-dir /tmp/sweep_x \
    --manifest /tmp/sweep_x/manifest.json \
    --upside-home "$UPSIDE_HOME" \
    --duration 200000 --frame-interval 200 \
    --temperature 0.85 \
    --anchor-residue 0 --pull-residue -1 \
    --n-replicas 2 \
    --sim-type tension \
    --forces-pn 14,18,22,26,30,34,38
```

Each sub-job lands in `<sweep-dir>/F_<pN>pN_rep_<i>/`.

### Calibrate forces (optional)

The default conversion `41.4 pN per Upside-force unit` comes from the FN3
unfolding fit. Refine it for your build with:

```bash
python analysis/force_calibration.py --reference fn3-d10 --traj-file my_fn3_pull.run.up
# -> writes analysis/calibration.json
```

`Force_Sweep.py` will pick up the new factor automatically on the next run.

---

## Phase 2 — Back-mapping intermediates

The clustering step from Phase 1 saves CG (Cα/N/C only) PDBs. AI design tools
need full all-atom inputs, so we rebuild them.

### From the UI

After running **Compute Epitope Candidates**, hit **Back-map intermediates**
in the *All-atom Back-mapping* card. PULCHRA + a short OpenMM minimisation
turns each CG intermediate into an all-atom PDB at
`web/server/jobs/<job_id>/backmapped/intermediate_*_aa.pdb`.

### From the CLI

```bash
python analysis/backmapping.py jobs/<id>/intermediates/intermediate_03.pdb \
       jobs/<id>/backmapped/intermediate_03_aa.pdb
```

Use `--no-minimize` to skip the OpenMM step (e.g. if OpenMM isn't installed).

---

## Phase 3 — AI nanobody design

Send a back-mapped intermediate to Tamarind Bio (RFdiffusion → ProteinMPNN →
AlphaFold-Multimer) and read back ranked binders.

### Pre-flight

* Open **Settings** (top-right) and paste your `TAMARIND_API_KEY`.
  It's saved to `web/server/.env` (gitignored).
* If you don't have a key yet, leave it blank and check
  **Use mock client (offline / testing)** in the design card. This runs
  the deterministic stub at `design/tamarind_mock.py` so you can practice
  the full flow without spending API credits.

### From the UI

1. Pick the back-mapped intermediate.
2. Paste hotspot residues (typically the top 3-5 from the
   *Epitope Candidates* rollup).
3. `n_designs` = 50 is a sensible default. If you crank it past 100 the UI
   will pop a cost confirmation.
4. **Run Design Pipeline**. Tamarind streams progress; the UI polls every
   ~2 s and renders ranked candidates by ipTM.

### From the CLI

```bash
python -c "
import json
from pathlib import Path
import design.pipeline as p
out = p.run_design_pipeline(
    job_dir=Path('web/server/jobs/<job_id>'),
    design_dir=Path('web/server/jobs/<job_id>/design/cli_run'),
    request_body={'intermediate_state': 'intermediate_03',
                  'hotspots': [42,43,44],
                  'n_designs': 30,
                  'use_mock': True},
)
print(json.dumps(out, indent=2))
"
```

---

## Phase 4 — Centrifuge experiment + comparison

### Generate a bench-ready protocol

In the *Centrifuge Experiment Design + Comparison* card:

1. Set zone count, force range, predicted thresholds (the top exposure
   forces from Phase 1), and attachment chemistry.
2. **Generate experiment sheet** — produces a markdown protocol with
   rotor speed, radial layout, attachment chemistry, controls, and a
   spin-protocol.
3. The markdown is saved to
   `web/server/jobs/<job_id>/experimental/design_sheet.md`.

### Upload wet-lab data

After running the centrifuge experiment, dump fluorescence-vs-zone data
into a CSV with columns `force_pN, fluorescence, replicate, condition`,
where `condition` is one of `primary`, `no-spin`, `scrambled-cdr`,
`disulfide-stapled`. Upload via the *Wet-lab data upload* file picker.

### Compare with prediction

Enter the predicted activation threshold (the force the binder *should*
start binding at, from Upside) and hit **Compare with Upside prediction**.
The plot overlays your wet-lab points on the predicted curve and reports
the experimental threshold inferred from the half-max of the primary
condition.

CLI equivalent:

```bash
python -c "
import analysis.dynalab_analysis as da
print(da.analyze_force_binding_comparison(
    'web/server/jobs/<job_id>/experimental/wetlab.csv',
    'web/server/jobs/<job_id>/experimental/comparison.png',
    predicted_threshold_pn=22.0,
))"
```

---

## Job directory layout

```
web/server/jobs/<job_id>/
    input.pdb
    config.json
    status.json
    sim.log
    outputs/sim/sim.run.up               # final trajectory
    sweeps/<sweep_id>/                   # Phase 1
        manifest.json
        sweep.log
        F_14.0pN_rep_0/                  # one per (force, replica)
            outputs/sim/sim.run.up
            sim.log
            Tension_Simulations.dat
        ...
        analysis/                        # sweep-level rollups
            EpitopeCandidates.png
            BurialSweep.png
            IntermediateClustering.png
            results.json
    intermediates/                       # Phase 1 -> Phase 2 input
        intermediate_00.pdb
        ...
    backmapped/                          # Phase 2 output -> Phase 3 input
        intermediate_00_aa.pdb
        summary.json
        backmap.log
    design/<design_id>/                  # Phase 3
        request.json
        manifest.json
        scores.json
        candidates/rank_001.pdb
        ...
    experimental/                        # Phase 4
        design_sheet.md
        design.json
        wetlab.csv
        comparison.png
        comparison.json
    analysis/                            # single-traj analyses
        Rg.png, RMSD.png, ...
        results.json
```

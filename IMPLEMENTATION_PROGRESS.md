# Research Vision Implementation Progress

Live status of the build-out of the [research vision plan](RESEARCH_VISION.md).

## Legend
- [x] Done
- [~] In progress
- [ ] Pending

---

## Phase 0 — Cross-cutting infrastructure

- [x] `phase0-storage` — Job-storage layout extension (sweeps/, intermediates/, backmapped/, design/, experimental/) + `kind` field
- [x] `phase0-secrets` — Secrets handling (`.env`, `TAMARIND_API_KEY`)
- [x] `phase0-runupside` — Normalize duplicated content in `py/run_upside.py` (1383 -> 698 lines, removed older duplicate that was overriding the bug-fixed version)
- [x] `phase0-tension` — Wire constant-tension mode through Flask + UI

## Phase 1 — Pulling pipeline

- [x] `p1-sweep-script` — `start/Force_Sweep.py` orchestrator + bounded parallelism
- [x] `p1-sweep-api` — `POST /api/sweeps`, `GET /api/sweeps/<id>` + manifest tracking
- [x] `p1-calibration` — `analysis/force_calibration.py` + `calibration.json` + `/api/calibrate` + `/api/calibration`
- [x] `p1-engine-bridge` — `_load_engine_outputs` (compute_upside_values bridge in dynalab_analysis)
- [x] `p1-burial-scan` — `analyze_burial_scan` (single-traj, exposure delta + ranked candidates)
- [x] `p1-dihedral` — `analyze_dihedral_unfolding` (Ramachandran-basin loss across the trajectory)
- [x] `p1-clustering` — `analyze_intermediate_clustering` (contact-PCA + KMeans, saves rep PDBs)
- [x] `p1-epitope-rollup` — `analyze_epitope_candidates_sweep` + `analyze_burial_scan_sweep` + `analyze_intermediate_clustering_sweep` (sweep-level dispatchers)
- [x] `p1-ui-sweep` — Force-Sweep card in UI + sub-job progress + Compute-Epitope-Candidates button + sweep results page

## Phase 2 — Back-mapping

- [x] `p2-pulchra-docker` — PULCHRA build in Dockerfile (`.devcontainer/install_pulchra.sh`)
- [x] `p2-backmap-module` — `analysis/backmapping.py` (PULCHRA + optional OpenMM minimisation, no-op fallback)
- [x] `p2-backmap-api-ui` — `POST /api/jobs/<id>/backmap`, list endpoints, UI card with intermediate list and PDB download links

## Phase 3 — AI nanobody design (Tamarind Bio)

- [x] `p3-tamarind-client` — `design/tamarind_client.py` real REST wrapper + `design/tamarind_mock.py` deterministic stub
- [x] `p3-pipeline` — `design/pipeline.py` orchestrator (auto-fallback to mock if no API key, full RFdiff -> MPNN -> AF-Multimer)
- [x] `p3-api` — `/api/jobs/<id>/design`, `/api/design/<job_id>/<design_id>`, `/api/design/<job_id>/<design_id>/candidate/<rank>`
- [x] `p3-ui-design` — Design card + Settings dialog (API key never echoed back, persisted to `.env`)
- [x] `p3-cost-guard` — Browser confirm() if `n_designs > 100`

## Phase 4 — Experimental comparison

- [x] `p4-centrifuge-design` — `analysis/centrifuge_design.py` + `/api/jobs/<id>/experiment-design` + markdown sheet + JSON
- [x] `p4-wetlab-upload` — `/api/jobs/<id>/experimental` CSV upload + column validation + condition warnings
- [x] `p4-comparison` — `analyze_force_binding_comparison` + `/api/jobs/<id>/comparison` + UI tab with overlay plot

## Phase 5 — Docs, tests, deployment

- [x] `p5-docs` — Added `WORKFLOWS.md`, this progress doc, updated server README. (`ARCHITECTURE.md`, `RESEARCH_VISION.md`, `SIMULATION_COOKBOOK.md` already cover the underlying pieces)
- [x] `p5-tests` — Test fixtures + analysis tests (`tests/test_force_calibration.py`, `test_centrifuge_design.py`, `test_design_pipeline.py`, `test_dynalab_analysis.py`, `test_backmapping.py`). 28/28 pure-Python tests pass locally.
- [x] `p5-deployment` — EC2 polish: `deploy/load_ssm_secrets.sh`, `deploy/mount_jobs_ebs.sh`, `deploy/dynalab.service` systemd unit, `deploy/README.md` runbook

---

## Files added

* `start/Force_Sweep.py` — multi-force pulling sweep orchestrator
* `analysis/force_calibration.py` — Upside-force -> pN calibration
* `analysis/backmapping.py` — PULCHRA + OpenMM back-mapping
* `analysis/centrifuge_design.py` — centrifuge experiment design sheet
* `design/__init__.py`, `design/tamarind_client.py`, `design/tamarind_mock.py`, `design/pipeline.py` — AI design pipeline
* `.devcontainer/install_pulchra.sh` — PULCHRA build script for the dev container
* `web/server/.env.example` — environment template
* `web/server/.gitignore` — keep `.env` and per-job artifacts out of git
* `tests/conftest.py` + `tests/test_force_calibration.py` + `tests/test_centrifuge_design.py` + `tests/test_design_pipeline.py` + `tests/test_dynalab_analysis.py` + `tests/test_backmapping.py`
* `deploy/load_ssm_secrets.sh`, `deploy/mount_jobs_ebs.sh`, `deploy/dynalab.service`, `deploy/README.md`
* `WORKFLOWS.md` — phase-by-phase recipes (UI + CLI for each step)
* `IMPLEMENTATION_PROGRESS.md` — this file

## Files modified

* `web/server/app.py` — full pipeline endpoints (single, sweep, analyze, analyze-sweep, intermediates, backmap, design, calibrate, experiment-design, experimental, comparison, settings/tamarind), `.env` loading, `_init_job_layout`, `kind` field on every status write, child-env helper
* `web/server/requirements.txt` — added `requests` (Tamarind client) + `openmm` (optional back-map minimisation)
* `analysis/dynalab_analysis.py` — engine bridge, three new single-traj analyses (`burial_scan`, `dihedral`, `intermediates`), three sweep-level analyses (`epitope_candidates`, `burial_sweep`, `intermediates`), `analyze_force_binding_comparison`, `run_sweep_analyses`
* `web/intermediate/index.html` — Settings dialog, Pulling-mode select + tension entry table, Force-Sweep card, intermediates / backmap / design / experimental sections
* `web/intermediate/script.js` — sweep submission/polling, sweep analysis, intermediate listing, backmap polling + listing, design submission with cost guard, experimental sheet generation, CSV upload, comparison; settings open/save
* `web/intermediate/style.css` — settings button + dialog, sweep / experimental section styling
* `.devcontainer/Dockerfile` — invokes `install_pulchra.sh`
* `py/run_upside.py` — removed duplicated second copy that overrode the bug-fixed first copy

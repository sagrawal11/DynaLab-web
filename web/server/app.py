"""Flask backend for the DynaLab / Upside2 web UI.

Submits jobs from the localhost frontend to this server, which executes
them locally as subprocesses using the existing ``start/`` scripts.

This file deliberately stays thin. Anything bigger than 'orchestrate a
subprocess and report status' lives elsewhere:
  - ``analysis/dynalab_analysis.py``  -> trajectory analyses
  - ``analysis/force_calibration.py`` -> Upside-units -> pN calibration
  - ``analysis/backmapping.py``       -> CG -> all-atom (PULCHRA + OpenMM)
  - ``analysis/centrifuge_design.py`` -> centrifuge experiment design sheet
  - ``design/pipeline.py``            -> RFdiff -> MPNN -> AF-Multimer pipeline
  - ``design/tamarind_client.py``     -> hosted-AI client (Tamarind Bio)
  - ``start/Force_Sweep.py``          -> N-force pulling sweep orchestrator
"""

import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path

from flask import Flask, jsonify, redirect, request, send_file, send_from_directory


SERVER_DIR = Path(__file__).resolve().parent
WEB_DIR = SERVER_DIR.parent
REPO_ROOT = WEB_DIR.parent
ANALYSIS_DIR = REPO_ROOT / "analysis"
DESIGN_DIR = REPO_ROOT / "design"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _load_dotenv(path: Path) -> None:
    """Tiny .env loader (no python-dotenv dependency).

    Only sets variables that aren't already in os.environ so an existing
    real environment wins over the file. Handles ``KEY=value`` and
    ``KEY="value with spaces"`` forms; ignores blank lines and ``#`` comments.
    """
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv(SERVER_DIR / ".env")


def _resolve_upside_home() -> str:
    """Prefer ``UPSIDE_HOME`` from env only if it actually contains the
    start/ scripts; otherwise fall back to the repo root inferred from
    this file's location."""
    candidate = os.environ.get("UPSIDE_HOME")
    if candidate and (Path(candidate) / "start" / "Single_Replica.py").is_file():
        return candidate
    return str(REPO_ROOT)


UPSIDE_HOME = _resolve_upside_home()
JOBS_DIR = SERVER_DIR / "jobs"
JOBS_DIR.mkdir(exist_ok=True)


# Subdirectories created inside every job for the multi-phase pipeline.
# Sweeps put per-force trajectories under sweeps/. Intermediate cluster PDBs
# from Phase 1 land in intermediates/. PULCHRA back-mapped all-atom PDBs
# go into backmapped/. AI design results live under design/<design_id>/.
# Wet-lab CSVs and the centrifuge design sheet go into experimental/.
JOB_SUBDIRS = ("sweeps", "intermediates", "backmapped", "design", "experimental", "analysis")


def _init_job_layout(job_dir: Path) -> None:
    job_dir.mkdir(exist_ok=True)
    for sub in JOB_SUBDIRS:
        (job_dir / sub).mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Lazy module loading
# ---------------------------------------------------------------------------

def _load_module(module_dir: Path, module_name: str):
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))
    return __import__(module_name)


def _load_analysis_module():
    return _load_module(ANALYSIS_DIR, "dynalab_analysis")


def _load_calibration_module():
    return _load_module(ANALYSIS_DIR, "force_calibration")


def _load_backmapping_module():
    return _load_module(ANALYSIS_DIR, "backmapping")


def _load_centrifuge_module():
    return _load_module(ANALYSIS_DIR, "centrifuge_design")


def _load_design_pipeline():
    return _load_module(DESIGN_DIR, "pipeline")


app = Flask(__name__, static_folder=None)


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Default UI: serve the DynaLab intermediate workflow."""
    return redirect("/intermediate/", code=302)


@app.route("/intermediate/")
def intermediate_index():
    return send_from_directory(WEB_DIR / "intermediate", "index.html")


@app.route("/intermediate/<path:filename>")
def intermediate_static(filename):
    return send_from_directory(WEB_DIR / "intermediate", filename)


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------

def _write_status(job_dir: Path, **fields) -> None:
    """Write status.json. ``kind`` is preserved across writes if set previously."""
    existing = {}
    p = job_dir / "status.json"
    if p.exists():
        try:
            existing = json.loads(p.read_text())
        except Exception:
            existing = {}
    existing.update(fields)
    p.write_text(json.dumps(existing))


def _read_status(job_dir: Path) -> dict:
    return json.loads((job_dir / "status.json").read_text())


def _child_env() -> dict:
    """Environment for subprocess invocations: same Python on PATH, UPSIDE_HOME set."""
    python_bin = str(Path(sys.executable).parent)
    return {
        **os.environ,
        "UPSIDE_HOME": UPSIDE_HOME,
        "PATH": python_bin + os.pathsep + os.environ.get("PATH", ""),
    }


# ---------------------------------------------------------------------------
# Single-job execution (constant T, velocity-clamp pulling, or constant tension)
# ---------------------------------------------------------------------------

def _write_velocity_dat(job_dir: Path, entries: list) -> None:
    with (job_dir / "Velocity_Simulations.dat").open("w") as f:
        f.write("residue spring_const pulling_vel_x pulling_vel_y pulling_vel_z\n")
        for entry in entries:
            f.write(
                f"{int(entry['residue'])} "
                f"{float(entry.get('spring', 0.05))} "
                f"{float(entry.get('velX', 0))} "
                f"{float(entry.get('velY', 0))} "
                f"{float(entry.get('velZ', 0))}\n"
            )


def _write_tension_dat(job_dir: Path, entries: list) -> None:
    """Write Tension_Simulations.dat for constant-tension pulling.

    Each entry has ``residue`` and the three force components ``tx``/``ty``/``tz``
    (in Upside reduced units, kT/A). This is the centrifuge-equivalent
    pulling mode (constant force, not velocity-clamp).
    """
    with (job_dir / "Tension_Simulations.dat").open("w") as f:
        f.write("residue tension_x tension_y tension_z\n")
        for entry in entries:
            f.write(
                f"{int(entry['residue'])} "
                f"{float(entry.get('tx', 0))} "
                f"{float(entry.get('ty', 0))} "
                f"{float(entry.get('tz', 0))}\n"
            )


def _build_simulation_command(job_dir: Path, config: dict) -> tuple:
    """Return ``(cmd, mode)`` for a single-job simulation invocation.

    ``mode`` is ``'tension'``, ``'velocity'``, or ``'plain'``. The corresponding
    ``.dat`` file (if any) is written into ``job_dir`` as a side effect.
    """
    pdb_id = "input"
    sim_id = "sim"
    duration = str(int(float(config.get("duration", 1e6))))
    frame_interval = str(int(config.get("frameInterval", 100)))
    temperature = str(config.get("temperature", 0.85))

    # Constant-tension mode (centrifuge analog)
    tension_entries = config.get("tensionEntries") or []
    if config.get("enablePulling") and config.get("pullingMode") == "tension" and tension_entries:
        _write_tension_dat(job_dir, tension_entries)
        script = f"{UPSIDE_HOME}/start/Pulling_Simulations.py"
        cmd = [
            sys.executable, script, pdb_id, str(job_dir), sim_id,
            duration, frame_interval, "tension", "False", temperature, "None",
        ]
        return cmd, "tension"

    # Velocity-clamp / AFM mode
    afm_entries = config.get("afmEntries") or []
    if config.get("enablePulling") and afm_entries:
        _write_velocity_dat(job_dir, afm_entries)
        script = f"{UPSIDE_HOME}/start/Pulling_Simulations.py"
        cmd = [
            sys.executable, script, pdb_id, str(job_dir), sim_id,
            duration, frame_interval, "velocity", "False", temperature, "None",
        ]
        return cmd, "velocity"

    # Plain constant-T
    script = f"{UPSIDE_HOME}/start/Single_Replica.py"
    cmd = [
        sys.executable, script, pdb_id, str(job_dir), sim_id,
        duration, frame_interval, "False", temperature, "None",
    ]
    return cmd, "plain"


def _run_simulation(job_id: str, config: dict) -> None:
    job_dir = JOBS_DIR / job_id
    log_file = job_dir / "sim.log"
    cmd, mode = _build_simulation_command(job_dir, config)

    _write_status(job_dir, job_id=job_id, status="running",
                  cmd=" ".join(cmd), pulling_mode=mode)

    try:
        with log_file.open("w") as log_fp:
            log_fp.write(f"$ {' '.join(cmd)}\n\n")
            log_fp.flush()
            proc = subprocess.Popen(
                cmd, cwd=str(job_dir),
                stdout=log_fp, stderr=subprocess.STDOUT,
                env=_child_env(),
            )
            proc.wait()

        if proc.returncode == 0:
            _write_status(job_dir, status="completed")
        else:
            _write_status(job_dir, status="failed", returncode=proc.returncode)
    except Exception as exc:
        _write_status(job_dir, status="failed", error=str(exc))


# ---------------------------------------------------------------------------
# Single-job API
# ---------------------------------------------------------------------------

@app.route("/api/jobs", methods=["POST"])
def submit_job():
    if "pdb" not in request.files:
        return jsonify({"error": "Missing 'pdb' file"}), 400

    pdb_file = request.files["pdb"]
    if not pdb_file.filename.lower().endswith(".pdb"):
        return jsonify({"error": "File must have .pdb extension"}), 400

    try:
        config = json.loads(request.form.get("config", "{}"))
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid config JSON"}), 400

    job_id = uuid.uuid4().hex[:8]
    job_dir = JOBS_DIR / job_id
    _init_job_layout(job_dir)

    pdb_file.save(job_dir / "input.pdb")
    (job_dir / "config.json").write_text(json.dumps(config, indent=2))
    _write_status(job_dir, job_id=job_id, status="queued", kind="single")

    threading.Thread(
        target=_run_simulation, args=(job_id, config), daemon=True,
    ).start()

    return jsonify({"job_id": job_id, "status": "queued"})


_STEP_RE = re.compile(r"^\s*([\d.]+)\s*/\s*([\d.]+)\s+elapsed")


def _parse_progress(log_file: Path, total_steps: int) -> tuple:
    """Return ``(current_step, total_steps)`` by scanning the tail of ``log_file``."""
    if not log_file.exists():
        return 0, total_steps
    try:
        with log_file.open() as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 4096))
            tail = f.read()
        current = 0
        for line in reversed(tail.splitlines()):
            m = _STEP_RE.match(line)
            if m:
                current = int(float(m.group(1)))
                total_steps = int(float(m.group(2)))
                break
        return current, total_steps
    except Exception:
        return 0, total_steps


@app.route("/api/jobs/<job_id>", methods=["GET"])
def get_job(job_id):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        return jsonify({"error": "Job not found"}), 404

    status = _read_status(job_dir)

    config_file = job_dir / "config.json"
    total_steps = 1
    if config_file.exists():
        try:
            total_steps = int(json.loads(config_file.read_text()).get("duration", 1))
        except Exception:
            pass

    current_step, total_steps = _parse_progress(job_dir / "sim.log", total_steps)
    status["current_step"] = current_step
    status["total_steps"] = total_steps
    return jsonify(status)


@app.route("/api/jobs/<job_id>/download", methods=["GET"])
def download_result(job_id):
    job_dir = JOBS_DIR / job_id
    output_file = job_dir / "outputs" / "sim" / "sim.run.up"
    if not output_file.exists():
        return jsonify({"error": "Output not ready"}), 404
    return send_file(output_file, as_attachment=True,
                     download_name=f"{job_id}.run.up")


@app.route("/api/jobs/<job_id>", methods=["DELETE"])
def delete_job(job_id):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        return jsonify({"error": "Job not found"}), 404
    shutil.rmtree(job_dir)
    return jsonify({"deleted": job_id})


# ---------------------------------------------------------------------------
# Force sweeps (Phase 1.1)
# ---------------------------------------------------------------------------

def _parse_sweep_progress(sweep_dir: Path) -> tuple:
    """Return (overall_pct, completed, total) by scanning each sub-job manifest."""
    manifest_file = sweep_dir / "manifest.json"
    if not manifest_file.is_file():
        return 0, 0, 0
    try:
        manifest = json.loads(manifest_file.read_text())
    except Exception:
        return 0, 0, 0
    sub = manifest.get("sub_jobs") or []
    if not sub:
        return 0, 0, 0
    total = len(sub)
    completed = sum(1 for s in sub if s.get("status") == "completed")
    running_pcts = []
    for s in sub:
        if s.get("status") == "running":
            log = sweep_dir / s["sub_dir"] / "sim.log"
            cur, tot = _parse_progress(log, max(1, int(s.get("total_steps", 1))))
            running_pcts.append(min(100.0, 100.0 * cur / max(1, tot)))
    failed = sum(1 for s in sub if s.get("status") == "failed")
    finished = completed + failed
    pct = (finished * 100.0 + sum(running_pcts)) / total
    return pct, completed, total


def _run_sweep(job_id: str, sweep_id: str, config: dict) -> None:
    """Run the orchestrator script start/Force_Sweep.py for this sweep_id.

    The orchestrator is a separate file (start/Force_Sweep.py) so that it
    stays runnable from the command line independently of the web server.
    The server simply invokes it, parses its progress from manifest.json,
    and reports status.
    """
    job_dir = JOBS_DIR / job_id
    sweep_dir = job_dir / "sweeps" / sweep_id
    sweep_dir.mkdir(parents=True, exist_ok=True)

    forces_pn = list(config.get("forces_pn") or [])
    n_replicas = int(config.get("n_replicas", 1))
    duration = int(config.get("duration", 100000))
    frame_interval = int(config.get("frameInterval", 200))
    temperature = float(config.get("temperature", 0.85))
    pull_residue = int(config.get("pullResidue", -1))   # -1 -> last residue
    anchor_residue = int(config.get("anchorResidue", 0))
    sim_type = config.get("sweepMode", "tension")        # tension | velocity

    # Manifest skeleton; each sub_jobs entry is filled in by the orchestrator.
    manifest = {
        "sweep_id":      sweep_id,
        "job_id":        job_id,
        "sim_type":      sim_type,
        "forces_pn":     forces_pn,
        "n_replicas":    n_replicas,
        "duration":      duration,
        "anchor_residue": anchor_residue,
        "pull_residue":  pull_residue,
        "sub_jobs":      [],
        "status":        "running",
        "started":       int(time.time()),
    }
    (sweep_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    cmd = [
        sys.executable,
        f"{UPSIDE_HOME}/start/Force_Sweep.py",
        "--pdb", str(job_dir / "input.pdb"),
        "--sweep-dir", str(sweep_dir),
        "--manifest", str(sweep_dir / "manifest.json"),
        "--upside-home", UPSIDE_HOME,
        "--duration", str(duration),
        "--frame-interval", str(frame_interval),
        "--temperature", str(temperature),
        "--anchor-residue", str(anchor_residue),
        "--pull-residue", str(pull_residue),
        "--n-replicas", str(n_replicas),
        "--sim-type", sim_type,
        "--forces-pn", ",".join(str(f) for f in forces_pn),
    ]

    _write_status(job_dir, status="running", sweep_id=sweep_id, sweep_cmd=" ".join(cmd))

    try:
        log_file = sweep_dir / "sweep.log"
        with log_file.open("w") as log_fp:
            log_fp.write(f"$ {' '.join(cmd)}\n\n")
            log_fp.flush()
            proc = subprocess.Popen(
                cmd, stdout=log_fp, stderr=subprocess.STDOUT, env=_child_env(),
            )
            proc.wait()

        manifest = json.loads((sweep_dir / "manifest.json").read_text())
        manifest["status"] = "completed" if proc.returncode == 0 else "failed"
        manifest["finished"] = int(time.time())
        (sweep_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        _write_status(job_dir, status="completed" if proc.returncode == 0 else "failed")
    except Exception as exc:
        _write_status(job_dir, status="failed", error=str(exc))


@app.route("/api/sweeps", methods=["POST"])
def submit_sweep():
    if "pdb" not in request.files:
        return jsonify({"error": "Missing 'pdb' file"}), 400
    pdb_file = request.files["pdb"]
    if not pdb_file.filename.lower().endswith(".pdb"):
        return jsonify({"error": "File must have .pdb extension"}), 400

    try:
        config = json.loads(request.form.get("config", "{}"))
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid config JSON"}), 400

    forces = config.get("forces_pn") or []
    if not isinstance(forces, list) or len(forces) == 0:
        return jsonify({"error": "config.forces_pn must be a non-empty list"}), 400
    try:
        config["forces_pn"] = [float(x) for x in forces]
    except (TypeError, ValueError):
        return jsonify({"error": "forces_pn must be numbers"}), 400

    job_id = uuid.uuid4().hex[:8]
    job_dir = JOBS_DIR / job_id
    _init_job_layout(job_dir)
    pdb_file.save(job_dir / "input.pdb")
    (job_dir / "config.json").write_text(json.dumps(config, indent=2))

    sweep_id = uuid.uuid4().hex[:6]
    _write_status(
        job_dir, job_id=job_id, status="queued", kind="sweep", sweep_id=sweep_id,
    )

    threading.Thread(
        target=_run_sweep, args=(job_id, sweep_id, config), daemon=True,
    ).start()

    return jsonify({"job_id": job_id, "sweep_id": sweep_id, "status": "queued"})


@app.route("/api/sweeps/<job_id>", methods=["GET"])
def get_sweep(job_id):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        return jsonify({"error": "Job not found"}), 404
    status = _read_status(job_dir)
    sweep_id = status.get("sweep_id")
    if sweep_id is None:
        return jsonify({"error": "Job is not a sweep"}), 400
    sweep_dir = job_dir / "sweeps" / sweep_id
    pct, done, total = _parse_sweep_progress(sweep_dir)
    manifest_file = sweep_dir / "manifest.json"
    manifest = json.loads(manifest_file.read_text()) if manifest_file.exists() else {}
    status.update({
        "progress_pct": round(pct, 1),
        "completed":    done,
        "total":        total,
        "manifest":     manifest,
    })
    return jsonify(status)


# ---------------------------------------------------------------------------
# Calibration (Phase 1.2)
# ---------------------------------------------------------------------------

def _run_calibration(reference: str) -> None:
    try:
        cal = _load_calibration_module()
        cal.calibrate_against_reference(reference=reference)
    except Exception as exc:
        # Persist the error to disk so the UI can see it
        ANALYSIS_DIR.mkdir(exist_ok=True)
        (ANALYSIS_DIR / "calibration_error.json").write_text(json.dumps({
            "error": f"{type(exc).__name__}: {exc}",
            "trace": traceback.format_exc(),
        }, indent=2))


@app.route("/api/calibrate", methods=["POST"])
def calibrate():
    body = request.get_json(silent=True) or {}
    reference = body.get("reference", "fn3-d10")
    threading.Thread(
        target=_run_calibration, args=(reference,), daemon=True,
    ).start()
    return jsonify({"status": "started", "reference": reference})


@app.route("/api/calibration", methods=["GET"])
def get_calibration():
    """Return the current calibration record if it exists, else default."""
    cal_file = ANALYSIS_DIR / "calibration.json"
    if cal_file.exists():
        return jsonify(json.loads(cal_file.read_text()))
    return jsonify({
        "factor_pn_per_upside_force": 41.4,
        "reference": "default (uncalibrated)",
        "T": 0.85,
        "note": "Run /api/calibrate to refine this against a reference protein.",
    })


# ---------------------------------------------------------------------------
# Analysis (Phase 1.3 + earlier general analysis)
# ---------------------------------------------------------------------------

def _resolve_traj_for_job(job_dir: Path) -> Path | None:
    direct = job_dir / "outputs" / "sim" / "sim.run.up"
    if direct.exists():
        return direct
    return None


@app.route("/api/jobs/<job_id>/analyze", methods=["POST"])
def analyze_job(job_id):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        return jsonify({"error": "Job not found"}), 404

    traj_file = _resolve_traj_for_job(job_dir)
    if traj_file is None:
        return jsonify({"error": "Trajectory not ready"}), 400

    body = request.get_json(silent=True) or {}
    requested = body.get("analyses") or []
    if not isinstance(requested, list) or not requested:
        return jsonify({"error": "Body must include non-empty 'analyses' list"}), 400
    params = body.get("params") or {}
    if not isinstance(params, dict):
        return jsonify({"error": "'params' must be an object if provided"}), 400

    try:
        dynalab = _load_analysis_module()
    except ImportError as exc:
        return jsonify({"error": f"Analysis dependencies missing: {exc}"}), 500

    analysis_dir = job_dir / "analysis"
    try:
        results = dynalab.run_analyses(
            str(traj_file), str(analysis_dir), requested, params=params,
        )
    except Exception as exc:
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500

    for key, result in results.items():
        image = result.pop("image", None)
        if image:
            result["image_url"] = f"/api/jobs/{job_id}/analysis/{Path(image).name}"

    (analysis_dir / "results.json").write_text(json.dumps(results, indent=2))
    return jsonify({"job_id": job_id, "results": results})


@app.route("/api/jobs/<job_id>/analyze-sweep", methods=["POST"])
def analyze_sweep(job_id):
    """Run cross-replica rollup analyses on a completed sweep.

    Body: ``{"analyses": ["epitope_candidates", "burial_scan", ...]}``.
    The functions live in ``analysis/dynalab_analysis.py`` but take the
    sweep manifest as input rather than a single trajectory.
    """
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        return jsonify({"error": "Job not found"}), 404
    status = _read_status(job_dir)
    sweep_id = status.get("sweep_id")
    if sweep_id is None:
        return jsonify({"error": "Job is not a sweep"}), 400

    body = request.get_json(silent=True) or {}
    requested = body.get("analyses") or ["epitope_candidates"]
    params = body.get("params") or {}

    try:
        dynalab = _load_analysis_module()
    except ImportError as exc:
        return jsonify({"error": f"Analysis dependencies missing: {exc}"}), 500

    sweep_dir = job_dir / "sweeps" / sweep_id
    out_dir = sweep_dir / "analysis"
    try:
        results = dynalab.run_sweep_analyses(
            str(sweep_dir), str(out_dir), requested, params=params,
        )
    except Exception as exc:
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500

    for key, result in results.items():
        image = result.pop("image", None)
        if image:
            result["image_url"] = (
                f"/api/sweeps/{job_id}/analysis/{Path(image).name}"
            )

    (out_dir / "results.json").write_text(json.dumps(results, indent=2))
    return jsonify({"job_id": job_id, "sweep_id": sweep_id, "results": results})


@app.route("/api/sweeps/<job_id>/analysis/<path:filename>", methods=["GET"])
def get_sweep_analysis_file(job_id, filename):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        return jsonify({"error": "Job not found"}), 404
    status = _read_status(job_dir)
    sweep_id = status.get("sweep_id")
    if sweep_id is None:
        return jsonify({"error": "Job is not a sweep"}), 400
    base = (job_dir / "sweeps" / sweep_id / "analysis").resolve()
    file_path = (base / filename).resolve()
    if not str(file_path).startswith(str(base)):
        return jsonify({"error": "Invalid path"}), 400
    if not file_path.is_file():
        return jsonify({"error": "File not found"}), 404
    return send_file(file_path)


@app.route("/api/jobs/<job_id>/analysis/<path:filename>", methods=["GET"])
def get_analysis_file(job_id, filename):
    job_dir = JOBS_DIR / job_id
    base = (job_dir / "analysis").resolve()
    file_path = (base / filename).resolve()
    if not str(file_path).startswith(str(base)):
        return jsonify({"error": "Invalid path"}), 400
    if not file_path.is_file():
        return jsonify({"error": "File not found"}), 404
    return send_file(file_path)


# ---------------------------------------------------------------------------
# Intermediates (Phase 1.3 + Phase 2)
# ---------------------------------------------------------------------------

@app.route("/api/jobs/<job_id>/intermediates", methods=["GET"])
def list_intermediates(job_id):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        return jsonify({"error": "Job not found"}), 404
    inter = job_dir / "intermediates"
    files = sorted(p.name for p in inter.glob("*.pdb")) if inter.exists() else []
    return jsonify({"job_id": job_id, "files": files})


@app.route("/api/jobs/<job_id>/intermediates/<path:filename>", methods=["GET"])
def get_intermediate(job_id, filename):
    job_dir = JOBS_DIR / job_id
    base = (job_dir / "intermediates").resolve()
    p = (base / filename).resolve()
    if not str(p).startswith(str(base)):
        return jsonify({"error": "Invalid path"}), 400
    if not p.is_file():
        return jsonify({"error": "File not found"}), 404
    return send_file(p)


# ---------------------------------------------------------------------------
# Back-mapping (Phase 2)
# ---------------------------------------------------------------------------

def _run_backmap(job_id: str) -> None:
    job_dir = JOBS_DIR / job_id
    inter = job_dir / "intermediates"
    out_dir = job_dir / "backmapped"
    log_file = out_dir / "backmap.log"
    out_dir.mkdir(exist_ok=True)
    summary = []
    try:
        bm = _load_backmapping_module()
    except ImportError as exc:
        log_file.write_text(f"backmapping module unavailable: {exc}\n")
        _write_status(job_dir, backmap_status="failed", backmap_error=str(exc))
        return

    pdbs = sorted(inter.glob("*.pdb"))
    if not pdbs:
        log_file.write_text("No intermediate PDBs to back-map.\n")
        _write_status(job_dir, backmap_status="empty")
        return

    log_lines = []
    for pdb in pdbs:
        target = out_dir / pdb.name.replace(".pdb", "_aa.pdb")
        try:
            info = bm.backmap_pdb(str(pdb), str(target), minimize=True)
            summary.append({"input": pdb.name, "output": target.name, **info})
            log_lines.append(f"{pdb.name} -> {target.name}: OK")
        except Exception as exc:
            summary.append({"input": pdb.name, "error": f"{type(exc).__name__}: {exc}"})
            log_lines.append(f"{pdb.name}: FAILED ({type(exc).__name__}: {exc})")

    log_file.write_text("\n".join(log_lines) + "\n")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    _write_status(job_dir, backmap_status="completed")


@app.route("/api/jobs/<job_id>/backmap", methods=["POST"])
def backmap(job_id):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        return jsonify({"error": "Job not found"}), 404
    inter = job_dir / "intermediates"
    if not inter.exists() or not any(inter.glob("*.pdb")):
        return jsonify({"error": "No intermediate PDBs found - run sweep analysis first"}), 400

    _write_status(job_dir, backmap_status="running")
    threading.Thread(target=_run_backmap, args=(job_id,), daemon=True).start()
    return jsonify({"status": "started", "job_id": job_id})


@app.route("/api/jobs/<job_id>/backmapped", methods=["GET"])
def list_backmapped(job_id):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        return jsonify({"error": "Job not found"}), 404
    bm_dir = job_dir / "backmapped"
    files = sorted(p.name for p in bm_dir.glob("*.pdb")) if bm_dir.exists() else []
    summary_file = bm_dir / "summary.json"
    summary = json.loads(summary_file.read_text()) if summary_file.exists() else []
    return jsonify({"job_id": job_id, "files": files, "summary": summary})


@app.route("/api/jobs/<job_id>/backmapped/<path:filename>", methods=["GET"])
def get_backmapped(job_id, filename):
    job_dir = JOBS_DIR / job_id
    base = (job_dir / "backmapped").resolve()
    p = (base / filename).resolve()
    if not str(p).startswith(str(base)):
        return jsonify({"error": "Invalid path"}), 400
    if not p.is_file():
        return jsonify({"error": "File not found"}), 404
    return send_file(p)


# ---------------------------------------------------------------------------
# AI nanobody design (Phase 3)
# ---------------------------------------------------------------------------

def _run_design(job_id: str, design_id: str, request_body: dict) -> None:
    job_dir = JOBS_DIR / job_id
    design_dir = job_dir / "design" / design_id
    design_dir.mkdir(parents=True, exist_ok=True)
    (design_dir / "request.json").write_text(json.dumps(request_body, indent=2))
    manifest_file = design_dir / "manifest.json"
    manifest_file.write_text(json.dumps({
        "status": "running", "design_id": design_id, "job_id": job_id,
        "started": int(time.time()),
    }))
    try:
        pipeline = _load_design_pipeline()
        results = pipeline.run_design_pipeline(
            job_dir=job_dir,
            design_dir=design_dir,
            request_body=request_body,
        )
        manifest = json.loads(manifest_file.read_text())
        manifest.update({"status": "completed", "results": results,
                         "finished": int(time.time())})
        manifest_file.write_text(json.dumps(manifest, indent=2))
    except Exception as exc:
        manifest_file.write_text(json.dumps({
            "status": "failed", "design_id": design_id, "job_id": job_id,
            "error": f"{type(exc).__name__}: {exc}",
            "trace": traceback.format_exc(),
        }, indent=2))


@app.route("/api/jobs/<job_id>/design", methods=["POST"])
def submit_design(job_id):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        return jsonify({"error": "Job not found"}), 404

    body = request.get_json(silent=True) or {}
    intermediate_state = body.get("intermediate_state")
    if not intermediate_state:
        return jsonify({"error": "Body must include 'intermediate_state'"}), 400
    n_designs = int(body.get("n_designs", 50))
    if n_designs < 1:
        return jsonify({"error": "n_designs must be >= 1"}), 400

    design_id = uuid.uuid4().hex[:6]
    threading.Thread(
        target=_run_design, args=(job_id, design_id, body), daemon=True,
    ).start()
    return jsonify({"job_id": job_id, "design_id": design_id, "status": "queued"})


@app.route("/api/design/<job_id>/<design_id>", methods=["GET"])
def get_design(job_id, design_id):
    job_dir = JOBS_DIR / job_id
    manifest_file = job_dir / "design" / design_id / "manifest.json"
    if not manifest_file.exists():
        return jsonify({"error": "Design not found"}), 404
    return jsonify(json.loads(manifest_file.read_text()))


@app.route("/api/design/<job_id>/<design_id>/candidate/<int:rank>", methods=["GET"])
def get_design_candidate(job_id, design_id, rank):
    job_dir = JOBS_DIR / job_id
    base = (job_dir / "design" / design_id / "candidates").resolve()
    p = base / f"rank_{rank:03d}.pdb"
    if not p.exists():
        return jsonify({"error": "Candidate not found"}), 404
    return send_file(p)


# ---------------------------------------------------------------------------
# Centrifuge experiment design + wet-lab data (Phase 4)
# ---------------------------------------------------------------------------

@app.route("/api/jobs/<job_id>/experiment-design", methods=["POST"])
def make_experiment_design(job_id):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        return jsonify({"error": "Job not found"}), 404
    body = request.get_json(silent=True) or {}
    target_force_range = body.get("target_force_range", [14.0, 38.0])
    n_zones = int(body.get("n_zones", 10))
    predicted_thresholds = body.get("predicted_thresholds_pn") or []
    attachment = body.get("attachment", "his-tag")
    pdb_path = job_dir / "input.pdb"

    try:
        cd = _load_centrifuge_module()
        result = cd.design_centrifuge_experiment(
            target_pdb=str(pdb_path),
            predicted_thresholds_pn=list(predicted_thresholds),
            n_zones=n_zones,
            target_force_range=tuple(target_force_range),
            attachment=attachment,
        )
    except Exception as exc:
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500

    out_dir = job_dir / "experimental"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "design_sheet.md").write_text(result["markdown"])
    (out_dir / "design.json").write_text(json.dumps(result, indent=2))
    return jsonify({"job_id": job_id, **result})


@app.route("/api/jobs/<job_id>/experimental", methods=["POST"])
def upload_experimental(job_id):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        return jsonify({"error": "Job not found"}), 404

    if "csv" not in request.files:
        return jsonify({"error": "Missing 'csv' file"}), 400
    csv_file = request.files["csv"]
    text = csv_file.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    required = {"force_pN", "fluorescence", "replicate", "condition"}
    if not required.issubset(set((reader.fieldnames or []))):
        return jsonify({"error": f"CSV must have columns {sorted(required)}"}), 400

    rows = list(reader)
    conditions = {r["condition"] for r in rows}
    expected = {"primary", "no-spin", "scrambled-cdr", "disulfide-stapled"}
    missing = expected - conditions
    warnings = []
    if missing:
        warnings.append(f"Missing conditions: {sorted(missing)} - comparison will be partial")

    out_dir = job_dir / "experimental"
    out_dir.mkdir(exist_ok=True)
    target = out_dir / (csv_file.filename or "wetlab.csv")
    target.write_text(text)
    return jsonify({
        "job_id": job_id, "filename": target.name,
        "n_rows": len(rows), "warnings": warnings,
    })


@app.route("/api/jobs/<job_id>/comparison", methods=["POST"])
def comparison(job_id):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        return jsonify({"error": "Job not found"}), 404
    body = request.get_json(silent=True) or {}
    csv_filename = body.get("csv")
    predicted_threshold = body.get("predicted_threshold_pn")
    if not csv_filename or predicted_threshold is None:
        return jsonify({"error": "Body must include 'csv' and 'predicted_threshold_pn'"}), 400
    csv_path = job_dir / "experimental" / csv_filename
    if not csv_path.is_file():
        return jsonify({"error": f"CSV not found: {csv_filename}"}), 404

    try:
        dynalab = _load_analysis_module()
    except ImportError as exc:
        return jsonify({"error": f"Analysis dependencies missing: {exc}"}), 500

    out_dir = job_dir / "experimental"
    image_path = out_dir / "comparison.png"
    try:
        result = dynalab.analyze_force_binding_comparison(
            str(csv_path), str(image_path), predicted_threshold_pn=float(predicted_threshold),
        )
    except Exception as exc:
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500

    result["image_url"] = f"/api/jobs/{job_id}/experimental/{image_path.name}"
    (out_dir / "comparison.json").write_text(json.dumps(result, indent=2))
    return jsonify(result)


@app.route("/api/jobs/<job_id>/experimental/<path:filename>", methods=["GET"])
def get_experimental_file(job_id, filename):
    job_dir = JOBS_DIR / job_id
    base = (job_dir / "experimental").resolve()
    p = (base / filename).resolve()
    if not str(p).startswith(str(base)):
        return jsonify({"error": "Invalid path"}), 400
    if not p.is_file():
        return jsonify({"error": "File not found"}), 404
    return send_file(p)


# ---------------------------------------------------------------------------
# Settings: Tamarind API key
# ---------------------------------------------------------------------------

@app.route("/api/settings/tamarind", methods=["GET"])
def get_tamarind_settings():
    """Return whether a Tamarind API key is configured. Never echoes the key itself."""
    key = os.environ.get("TAMARIND_API_KEY", "")
    return jsonify({
        "configured": bool(key),
        "endpoint":   os.environ.get("TAMARIND_API_URL", "https://api.tamarind.bio"),
    })


@app.route("/api/settings/tamarind", methods=["POST"])
def set_tamarind_settings():
    """Persist API key to the .env file (set in-process and on disk).

    .env is gitignored. Storing the key here avoids requiring the user to
    restart the server every time they update it.
    """
    body = request.get_json(silent=True) or {}
    key = (body.get("api_key") or "").strip()
    endpoint = (body.get("endpoint") or "").strip()

    env_path = SERVER_DIR / ".env"
    lines = []
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("TAMARIND_API_KEY=") or line.startswith("TAMARIND_API_URL="):
                continue
            lines.append(line)
    if key:
        lines.append(f'TAMARIND_API_KEY="{key}"')
        os.environ["TAMARIND_API_KEY"] = key
    if endpoint:
        lines.append(f'TAMARIND_API_URL="{endpoint}"')
        os.environ["TAMARIND_API_URL"] = endpoint
    env_path.write_text("\n".join(lines) + "\n")
    return jsonify({"ok": True, "configured": bool(os.environ.get("TAMARIND_API_KEY"))})


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)

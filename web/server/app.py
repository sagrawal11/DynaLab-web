"""Minimal Flask backend for running Upside2 simulations from the web UI.

Submits jobs from the localhost frontend to this server, which executes
them locally as subprocesses using the existing start/ scripts.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory


SERVER_DIR = Path(__file__).resolve().parent
WEB_DIR = SERVER_DIR.parent
REPO_ROOT = WEB_DIR.parent
ANALYSIS_DIR = REPO_ROOT / "analysis"


def _resolve_upside_home() -> str:
    """Prefer UPSIDE_HOME from env only if it actually contains the start/ scripts;
    otherwise fall back to the repo root inferred from this file's location."""
    candidate = os.environ.get("UPSIDE_HOME")
    if candidate and (Path(candidate) / "start" / "Single_Replica.py").is_file():
        return candidate
    return str(REPO_ROOT)


UPSIDE_HOME = _resolve_upside_home()

JOBS_DIR = SERVER_DIR / "jobs"
JOBS_DIR.mkdir(exist_ok=True)


def _load_analysis_module():
    """Import analysis/dynalab_analysis.py lazily so the server starts fast
    (matplotlib + mdtraj are slow to import) and so a missing scientific
    dependency doesn't crash the whole server."""
    if str(ANALYSIS_DIR) not in sys.path:
        sys.path.insert(0, str(ANALYSIS_DIR))
    import dynalab_analysis
    return dynalab_analysis

app = Flask(__name__, static_folder=None)


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return (
        '<h2>Upside2 local server</h2>'
        '<p><a href="/intermediate/">Intermediate UI</a></p>'
        '<p><a href="/advanced/">Advanced UI</a></p>'
    )


@app.route("/intermediate/")
def intermediate_index():
    return send_from_directory(WEB_DIR / "intermediate", "index.html")


@app.route("/intermediate/<path:filename>")
def intermediate_static(filename):
    return send_from_directory(WEB_DIR / "intermediate", filename)


@app.route("/advanced/")
def advanced_index():
    return send_from_directory(WEB_DIR / "advanced", "index.html")


@app.route("/advanced/<path:filename>")
def advanced_static(filename):
    return send_from_directory(WEB_DIR / "advanced", filename)


# ---------------------------------------------------------------------------
# Job execution
# ---------------------------------------------------------------------------

def _write_status(job_dir: Path, **fields) -> None:
    (job_dir / "status.json").write_text(json.dumps(fields))


def _read_status(job_dir: Path) -> dict:
    return json.loads((job_dir / "status.json").read_text())


def _run_simulation(job_id: str, config: dict) -> None:
    job_dir = JOBS_DIR / job_id
    log_file = job_dir / "sim.log"

    pdb_id = "input"
    sim_id = "sim"
    duration = str(int(float(config.get("duration", 1e6))))
    frame_interval = str(int(config.get("frameInterval", 100)))
    temperature = str(config.get("temperature", 0.85))

    if config.get("enablePulling") and config.get("afmEntries"):
        velocity_file = job_dir / "Velocity_Simulations.dat"
        with velocity_file.open("w") as f:
            f.write("residue spring_const pulling_vel_x pulling_vel_y pulling_vel_z\n")
            for entry in config["afmEntries"]:
                f.write(
                    f"{int(entry['residue'])} "
                    f"{float(entry['spring'])} "
                    f"{float(entry['velX'])} "
                    f"{float(entry['velY'])} "
                    f"{float(entry['velZ'])}\n"
                )
        script = f"{UPSIDE_HOME}/start/Pulling_Simulations.py"
        cmd = [
            sys.executable, script, pdb_id, str(job_dir), sim_id,
            duration, frame_interval, "velocity", "False", temperature, "None",
        ]
    else:
        script = f"{UPSIDE_HOME}/start/Single_Replica.py"
        cmd = [
            sys.executable, script, pdb_id, str(job_dir), sim_id,
            duration, frame_interval, "False", temperature, "None",
        ]

    _write_status(job_dir, job_id=job_id, status="running", cmd=" ".join(cmd))

    try:
        with log_file.open("w") as log_fp:
            log_fp.write(f"$ {' '.join(cmd)}\n\n")
            log_fp.flush()
            python_bin = str(Path(sys.executable).parent)
            child_env = {
                **os.environ,
                "UPSIDE_HOME": UPSIDE_HOME,
                "PATH": python_bin + os.pathsep + os.environ.get("PATH", ""),
            }
            process = subprocess.Popen(
                cmd,
                cwd=str(job_dir),
                stdout=log_fp,
                stderr=subprocess.STDOUT,
                env=child_env,
            )
            process.wait()

        if process.returncode == 0:
            _write_status(job_dir, job_id=job_id, status="completed")
        else:
            _write_status(
                job_dir, job_id=job_id, status="failed",
                returncode=process.returncode,
            )
    except Exception as exc:
        _write_status(job_dir, job_id=job_id, status="failed", error=str(exc))


# ---------------------------------------------------------------------------
# API
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
    job_dir.mkdir()

    pdb_file.save(job_dir / "input.pdb")
    (job_dir / "config.json").write_text(json.dumps(config, indent=2))
    _write_status(job_dir, job_id=job_id, status="queued")

    threading.Thread(
        target=_run_simulation, args=(job_id, config), daemon=True,
    ).start()

    return jsonify({"job_id": job_id, "status": "queued"})


_STEP_RE = re.compile(r"^\s*([\d.]+)\s*/\s*([\d.]+)\s+elapsed")


def _parse_progress(log_file: Path, total_steps: int):
    """Return (current_step, total_steps) by scanning the last few KB of the log."""
    if not log_file.exists():
        return 0, total_steps
    try:
        with log_file.open() as f:
            # Read only the tail to keep this fast for large logs
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
    return send_file(
        output_file, as_attachment=True,
        download_name=f"{job_id}.run.up",
    )


# ---------------------------------------------------------------------------
# Post-processing analysis (calls analysis/dynalab_analysis.py)
# ---------------------------------------------------------------------------

@app.route("/api/jobs/<job_id>/analyze", methods=["POST"])
def analyze_job(job_id):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        return jsonify({"error": "Job not found"}), 404

    traj_file = job_dir / "outputs" / "sim" / "sim.run.up"
    if not traj_file.exists():
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


@app.route("/api/jobs/<job_id>/analysis/<path:filename>", methods=["GET"])
def get_analysis_file(job_id, filename):
    job_dir = JOBS_DIR / job_id
    file_path = (job_dir / "analysis" / filename).resolve()
    # Prevent path traversal: must stay inside job_dir/analysis
    if not str(file_path).startswith(str((job_dir / "analysis").resolve())):
        return jsonify({"error": "Invalid path"}), 400
    if not file_path.is_file():
        return jsonify({"error": "File not found"}), 404
    return send_file(file_path)


@app.route("/api/jobs/<job_id>", methods=["DELETE"])
def delete_job(job_id):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        return jsonify({"error": "Job not found"}), 404
    shutil.rmtree(job_dir)
    return jsonify({"deleted": job_id})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)

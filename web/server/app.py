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

from __future__ import annotations

import csv
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
import zipfile
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


@app.route("/media/<path:filename>")
def media_static(filename):
    """Shared images/GIFs for help copy and docs under web/media/."""
    return send_from_directory(WEB_DIR / "media", filename)


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


def _write_tension_dat(
    job_dir: Path,
    entries: list,
    *,
    tension_in_pn: bool = False,
) -> None:
    """Write Tension_Simulations.dat for constant-tension pulling.

    Each entry has ``residue`` and ``tx``/``ty``/``tz``. By default these are
    Upside reduced units (kT/Å). If ``tension_in_pn`` is true, values are
    treated as piconewtons and converted with
    ``analysis/force_calibration.pn_per_upside_force_unit`` (Upside = pN / factor).
    """
    inv = None
    if tension_in_pn:
        inv = 1.0 / float(_load_calibration_module().pn_per_upside_force_unit())
    with (job_dir / "Tension_Simulations.dat").open("w") as f:
        f.write("residue tension_x tension_y tension_z\n")
        for entry in entries:
            tx = float(entry.get("tx", 0))
            ty = float(entry.get("ty", 0))
            tz = float(entry.get("tz", 0))
            if inv is not None:
                tx, ty, tz = tx * inv, ty * inv, tz * inv
            f.write(f"{int(entry['residue'])} {tx} {ty} {tz}\n")


PAIR_SPRING_FILENAME = "spring-pair-xyz.dat"
PAIR_SPRING_HEADER = "residue1 residue2 radius spring_const xyz"
# Strong harmonic constant in Upside reduced units for near-rigid Cα–Cα bridging (not a chemical disulfide).
RIGID_PAIR_SPRING_CONST = 120.0


def _ordered_ca_xyz_from_pdb(pdb_path: Path) -> list[tuple[float, float, float]]:
    """Ordered Cα positions (one per residue) for 0-based Upside-style indexing."""
    if not pdb_path.is_file():
        return []
    seen: set[tuple[str, int, str]] = set()
    coords: list[tuple[float, float, float]] = []
    for line in pdb_path.read_text().splitlines():
        if not (line.startswith("ATOM  ") or line.startswith("HETATM")):
            continue
        if line[12:16].strip() != "CA":
            continue
        chain = line[21]
        try:
            resseq = int(line[22:26])
        except ValueError:
            continue
        icode = line[26] if len(line) > 26 else " "
        icode = icode.strip() or " "
        key = (chain, resseq, icode)
        if key in seen:
            continue
        seen.add(key)
        try:
            x = float(line[30:38])
            y = float(line[38:46])
            z = float(line[46:54])
        except (ValueError, IndexError):
            continue
        coords.append((x, y, z))
    return coords


def _ca_distance(coords: list[tuple[float, float, float]], i: int, j: int) -> float:
    if i < 0 or j < 0 or i >= len(coords) or j >= len(coords):
        raise ValueError(
            f"Cα distance: residue indices {i}, {j} out of range for this PDB (0..{len(coords) - 1})."
        )
    ax, ay, az = coords[i]
    bx, by, bz = coords[j]
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)


def _write_pair_spring_dat(job_dir: Path, config: dict) -> str | None:
    """Write ``spring-pair-xyz.dat`` if the UI requested distance locks or manual pair spring.

    Returns the filename to pass to ``Single_Replica`` / ``Pulling_Simulations``, or ``None``.
    """
    pdb_path = job_dir / "input.pdb"
    lines_body: list[str] = []

    pairs = config.get("distanceLockPairs") or []
    for p in pairs:
        try:
            r1 = int(p.get("res1"))
            r2 = int(p.get("res2"))
        except (TypeError, ValueError):
            continue
        if r1 == r2:
            raise ValueError(f"Distance lock: residue indices must differ (got {r1}, {r2}).")
        rigid = config.get("restraintGroupRigidSpring")
        if rigid is None:
            rigid = True
        if rigid:
            spring = RIGID_PAIR_SPRING_CONST
        else:
            spring = float(p.get("springConst", 4.0))
        d_raw = (p.get("distanceAngstrom") or "").strip()
        coords = _ordered_ca_xyz_from_pdb(pdb_path)
        if not coords:
            raise ValueError("Distance lock: could not read Cα coordinates from input PDB.")
        if d_raw == "":
            r0 = _ca_distance(coords, r1, r2)
        else:
            r0 = float(d_raw)
        lines_body.append(f"{r1} {r2} {r0:.6f} {spring:g}")

    if lines_body:
        out = job_dir / PAIR_SPRING_FILENAME
        out.write_text(PAIR_SPRING_HEADER + "\n" + "\n".join(lines_body) + "\n")
        return PAIR_SPRING_FILENAME

    if config.get("enablePairSpringText"):
        raw = (config.get("pairSpringText") or "").strip()
        if raw:
            low = raw.splitlines()[0].lower() if raw else ""
            if "residue1" in low and "residue2" in low:
                text = raw if raw.endswith("\n") else raw + "\n"
            else:
                text = PAIR_SPRING_HEADER + "\n" + raw + ("\n" if not raw.endswith("\n") else "")
            (job_dir / PAIR_SPRING_FILENAME).write_text(text)
            return PAIR_SPRING_FILENAME

    return None


def _canonical_pair_int(i: int, j: int) -> tuple[int, int]:
    return (i, j) if i <= j else (j, i)


def _parse_pair_spring_text_residue_pairs(raw: str) -> list[tuple[int, int]]:
    """First two integers per non-comment, non-header line (Upside pair_spring body format)."""
    pairs: list[tuple[int, int]] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        low = s.lower()
        if "residue1" in low and "residue2" in low:
            continue
        parts = s.split()
        if len(parts) < 2:
            continue
        try:
            a = int(float(parts[0]))
            b = int(float(parts[1]))
        except (TypeError, ValueError):
            continue
        pairs.append((a, b))
    return pairs


def _validate_membrane_fields(config: dict) -> None:
    """Reject impossible membrane slab settings from the web UI."""
    if not config.get("membraneEnabled"):
        return
    try:
        inner = float(config.get("membraneInnerAngstrom", -16))
        outer = float(config.get("membraneOuterAngstrom", 16))
    except (TypeError, ValueError) as exc:
        raise ValueError("Membrane inner/outer boundaries must be numbers.") from exc
    if outer <= inner:
        raise ValueError("Membrane outer boundary (Å) must be greater than the inner boundary.")
    thickness = outer - inner
    if thickness < 4.0 or thickness > 120.0:
        raise ValueError("Implied membrane thickness (outer − inner) must be between 4 and 120 Å.")
    coord = str(config.get("membraneCoordSystem") or "cartesian").strip().lower()
    if coord not in ("cartesian", "spherical"):
        raise ValueError("membraneCoordSystem must be 'cartesian' or 'spherical'.")


def _validate_single_job_config(job_dir: Path, config: dict) -> None:
    """Reject inconsistent configs before spawning Upside (also enforced in the UI)."""
    pdb_path = job_dir / "input.pdb"

    _validate_membrane_fields(config)
    if locks is not None and not isinstance(locks, list):
        raise ValueError("distanceLockPairs must be a list when provided.")
    locks = locks or []

    has_manual = bool(config.get("enablePairSpringText")) and str(
        config.get("pairSpringText") or ""
    ).strip()
    if locks and has_manual:
        raise ValueError(
            "Cannot combine distance-lock restraint groups with manual pair spring text in one job. "
            "Disable one of them—they map to the same Upside pair_spring table."
        )

    seen_pairs: set[tuple[int, int]] = set()
    for idx, p in enumerate(locks):
        if not isinstance(p, dict):
            raise ValueError(f"Distance lock entry {idx + 1} must be an object.")
        try:
            r1 = int(p.get("res1"))
            r2 = int(p.get("res2"))
        except (TypeError, ValueError):
            raise ValueError(f"Distance lock entry {idx + 1}: residue indices must be integers.")
        if r1 < 0 or r2 < 0:
            raise ValueError(f"Distance lock entry {idx + 1}: residue indices cannot be negative.")
        if r1 == r2:
            raise ValueError(
                f"Distance lock entry {idx + 1}: the two residues must differ (got {r1}, {r2})."
            )
        key = _canonical_pair_int(r1, r2)
        if key in seen_pairs:
            raise ValueError(
                f"Duplicate distance-lock pair for residues {key[0]} and {key[1]} "
                "(order does not matter). Remove the duplicate row."
            )
        seen_pairs.add(key)

    if locks:
        coords = _ordered_ca_xyz_from_pdb(pdb_path)
        if not coords:
            raise ValueError("Distance locks require a readable PDB with Cα atoms.")
        n = len(coords)
        for idx, p in enumerate(locks):
            r1 = int(p.get("res1"))
            r2 = int(p.get("res2"))
            if r1 >= n or r2 >= n:
                raise ValueError(
                    f"Distance lock entry {idx + 1}: residue indices {r1}, {r2} are out of range "
                    f"for this PDB (valid 0..{n - 1})."
                )

    if has_manual:
        raw = str(config.get("pairSpringText") or "").strip()
        mpairs = _parse_pair_spring_text_residue_pairs(raw)
        if not mpairs:
            raise ValueError(
                "Manual pair spring text is enabled but no residue pair lines could be parsed."
            )
        seen_m: set[tuple[int, int]] = set()
        for a, b in mpairs:
            if a == b:
                raise ValueError(f"Manual pair spring: residue indices must differ (got {a}, {b}).")
            if a < 0 or b < 0:
                raise ValueError("Manual pair spring: residue indices cannot be negative.")
            key = _canonical_pair_int(a, b)
            if key in seen_m:
                raise ValueError(
                    f"Duplicate manual pair-spring line for residues {key[0]} and {key[1]}."
                )
            seen_m.add(key)
        coords = _ordered_ca_xyz_from_pdb(pdb_path)
        if coords:
            n = len(coords)
            for a, b in mpairs:
                if a >= n or b >= n:
                    raise ValueError(
                        f"Manual pair spring: indices {a}, {b} are out of range for this PDB "
                        f"(valid 0..{n - 1})."
                    )

    if not config.get("enablePulling"):
        return

    mode = (config.get("pullingMode") or "velocity").strip().lower()
    if mode == "tension":
        entries = config.get("tensionEntries") or []
        if not isinstance(entries, list) or not entries:
            raise ValueError("Constant-tension pulling requires at least one tension entry.")
        residues: list[int] = []
        for idx, e in enumerate(entries):
            if not isinstance(e, dict):
                raise ValueError(f"Tension entry {idx + 1} must be an object.")
            try:
                r = int(e.get("residue"))
            except (TypeError, ValueError):
                raise ValueError(f"Tension entry {idx + 1}: residue must be an integer.")
            if r < 0:
                raise ValueError(f"Tension entry {idx + 1}: residue index cannot be negative.")
            residues.append(r)
        if len(residues) != len(set(residues)):
            raise ValueError(
                "Constant-tension pulling: each residue may appear at most once across tension rows."
            )
    else:
        entries = config.get("afmEntries") or []
        if not isinstance(entries, list) or not entries:
            raise ValueError("Velocity-clamp pulling requires at least one AFM entry.")
        residues = []
        for idx, e in enumerate(entries):
            if not isinstance(e, dict):
                raise ValueError(f"AFM entry {idx + 1} must be an object.")
            try:
                r = int(e.get("residue"))
            except (TypeError, ValueError):
                raise ValueError(f"AFM entry {idx + 1}: residue must be an integer.")
            if r < 0:
                raise ValueError(f"AFM entry {idx + 1}: residue index cannot be negative.")
            residues.append(r)
        if len(residues) != len(set(residues)):
            raise ValueError(
                "Velocity-clamp pulling: each residue may appear at most once across AFM rows."
            )


def _basic_replica_count(config: dict) -> int:
    """Independent constant-T replicas for ``Single_Replica.py`` (sequential runs, distinct seeds)."""
    try:
        n = int(float(config.get("basicIndependentReplicas", 1)))
    except (TypeError, ValueError):
        n = 1
    return max(1, min(n, 32))


_REMD_TRAJ = re.compile(r"^input\.run\.(\d+)\.up$")


def _collect_remd_trajectories(job_dir: Path) -> list[Path]:
    """Replica-exchange outputs from ``start/Replica_Exchange.py`` (``outputs/remd/input.run.N.up``)."""
    remd_dir = job_dir / "outputs" / "remd"
    if not remd_dir.is_dir():
        return []
    numbered: list[tuple[int, Path]] = []
    for p in remd_dir.iterdir():
        if not p.is_file():
            continue
        m = _REMD_TRAJ.match(p.name)
        if m:
            numbered.append((int(m.group(1)), p))
    return [pair[1] for pair in sorted(numbered, key=lambda t: t[0])]


def _collect_basic_trajectories(job_dir: Path) -> list[Path]:
    """Return completed ``.run.up`` paths for a basic (non-sweep) job."""
    direct = job_dir / "outputs" / "sim" / "sim.run.up"
    if direct.is_file():
        return [direct]
    remd_paths = _collect_remd_trajectories(job_dir)
    if remd_paths:
        return remd_paths
    root = job_dir / "outputs"
    if not root.is_dir():
        return []
    paths = sorted(p for p in root.glob("sim_r*/*.run.up") if p.is_file())
    return paths


def _collect_sweep_trajectories_for_analysis(
    job_dir: Path, sweep_sub_dir: str | None
) -> list[Path]:
    """Return ``sim.run.up`` paths from a completed force sweep (manifest order).

    Sweeps never populate ``job_dir/outputs/sim/``; each sub-run lives under
    ``sweeps/<sweep_id>/<sub_dir>/outputs/sim/sim.run.up``.

    If ``sweep_sub_dir`` is set, it must match a *completed* manifest ``sub_dir``
    (e.g. ``F_22.0pN_rep_0``) and only that trajectory is returned. Otherwise all
    completed sub-jobs with an on-disk trajectory are returned.
    """
    status: dict = {}
    try:
        status = _read_status(job_dir)
    except Exception:
        return []
    sweep_id = status.get("sweep_id")
    if not sweep_id:
        return []
    sweep_dir = job_dir / "sweeps" / sweep_id
    manifest_path = sweep_dir / "manifest.json"
    if not manifest_path.is_file():
        return []
    try:
        manifest = json.loads(manifest_path.read_text())
    except Exception:
        return []
    sub_jobs = manifest.get("sub_jobs") or []
    completed_dirs = [
        e["sub_dir"]
        for e in sub_jobs
        if e.get("status") == "completed" and isinstance(e.get("sub_dir"), str)
    ]
    if not completed_dirs:
        return []

    if sweep_sub_dir:
        rel = sweep_sub_dir.replace("\\", "/").strip("/")
        if ".." in rel or "/" in rel:
            return []
        if rel not in completed_dirs:
            return []
        ordered = [rel]
    else:
        ordered = completed_dirs

    out: list[Path] = []
    for sd in ordered:
        traj = sweep_dir / sd / "outputs" / "sim" / "sim.run.up"
        if traj.is_file():
            out.append(traj)
    return out


def _sweep_subdir_label_from_traj(traj: Path, job_dir: Path) -> str | None:
    """Return manifest ``sub_dir`` (e.g. ``F_22.0pN_rep_0``) for paths under ``job_dir/sweeps``.

    Prefer this over ``Path.parents`` indexing so labels stay correct regardless of
    whether the job also has ``outputs/sim/sim.run.up`` at the root (which would
    otherwise make ``analyze_job`` pick ``basic_paths`` and label every sweep
    trajectory's parent as ``sim``).
    """
    try:
        rel = traj.resolve().relative_to(job_dir.resolve())
    except (ValueError, OSError):
        return None
    parts = rel.parts
    # sweeps/<sweep_id>/<sub_dir>/.../sim.run.up
    if len(parts) >= 4 and parts[0] == "sweeps":
        return parts[2]
    return None


def _mean_numeric_stats_across_replicas(stats_list: list[dict]) -> dict:
    """Average scalar stats across replicas; skip booleans and ambiguous integer indices."""
    if not stats_list:
        return {}
    keys = set(stats_list[0].keys())
    for s in stats_list[1:]:
        keys &= set(s.keys())
    out: dict[str, float] = {}
    for k in sorted(keys):
        vals = [s[k] for s in stats_list]
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
            continue
        if all(isinstance(v, int) for v in vals) and (
            "residue" in k.lower() or k.lower().endswith("_index")
        ):
            continue
        out[k] = sum(float(v) for v in vals) / len(vals)
    return out


def _aggregate_analysis_across_replicas(
    per_replica: dict[str, dict], ensemble_kind: str = "independent"
) -> dict:
    """One entry per analysis key: mean of numeric ``stats`` fields where all replicas succeeded."""
    if not per_replica:
        return {}
    labels = sorted(per_replica.keys())
    analysis_keys = None
    for lab in labels:
        keys = {k for k, v in per_replica[lab].items() if isinstance(v, dict)}
        analysis_keys = keys if analysis_keys is None else (analysis_keys & keys)
    agg: dict[str, dict] = {}
    for akey in sorted(analysis_keys or []):
        parts = []
        for lab in labels:
            r = per_replica[lab].get(akey)
            if not r or r.get("error"):
                parts = None
                break
            parts.append(r)
        if not parts:
            continue
        stats_list = [p.get("stats") or {} for p in parts]
        if not any(stats_list):
            agg[akey] = {
                "name": (parts[0].get("name") or akey) + " (ensemble mean)",
                "description": (
                    f"No comparable scalar stats across {len(labels)} replicas for this analysis."
                ),
            }
            continue
        mean_stats = _mean_numeric_stats_across_replicas(stats_list)
        base_name = parts[0].get("name") or akey
        base_desc = parts[0].get("description") or ""
        if ensemble_kind == "replica_exchange":
            trail = (
                f"fields in ``stats`` across {len(labels)} REMD replica trajectories "
                "(temperature ladder; not independent draws). Per-replica plots are shown above."
            )
        else:
            trail = (
                f"fields in ``stats`` across {len(labels)} independent replicas (same protocol, "
                "different random seeds). Per-replica plots are shown above."
            )
        agg[akey] = {
            "name": base_name + " (ensemble mean of scalars)",
            "description": (f"{base_desc} Values below are arithmetic means of matching numeric " + trail).strip(),
            "stats": mean_stats,
        }
    return agg


def _build_simulation_command(job_dir: Path, config: dict) -> tuple:
    """Return ``(cmd, mode)`` for a single-job simulation invocation.

    ``mode`` is ``'tension'``, ``'velocity'``, ``'replica'``, or ``'plain'``. The corresponding
    ``.dat`` file (if any) is written into ``job_dir`` as a side effect.
    """
    pdb_id = "input"
    sim_id = "sim"
    duration = str(int(float(config.get("duration", 1e6))))
    frame_interval = str(int(config.get("frameInterval", 100)))
    temperature = str(config.get("temperature", 0.85))

    restraint_arg = _write_pair_spring_dat(job_dir, config) or "None"

    # Constant-tension mode (centrifuge analog)
    tension_entries = config.get("tensionEntries") or []
    if config.get("enablePulling") and config.get("pullingMode") == "tension" and tension_entries:
        _write_tension_dat(
            job_dir,
            tension_entries,
            tension_in_pn=bool(config.get("tensionInPiconewtons")),
        )
        script = f"{UPSIDE_HOME}/start/Pulling_Simulations.py"
        cmd = [
            sys.executable, script, pdb_id, str(job_dir), sim_id,
            duration, frame_interval, "tension", "False", temperature, restraint_arg,
        ]
        return cmd, "tension"

    # Velocity-clamp / AFM mode
    afm_entries = config.get("afmEntries") or []
    if config.get("enablePulling") and afm_entries:
        _write_velocity_dat(job_dir, afm_entries)
        script = f"{UPSIDE_HOME}/start/Pulling_Simulations.py"
        cmd = [
            sys.executable, script, pdb_id, str(job_dir), sim_id,
            duration, frame_interval, "velocity", "False", temperature, restraint_arg,
        ]
        return cmd, "velocity"

    sim_mode = (config.get("simulationMode") or "constant").strip().lower()
    if sim_mode == "replica":
        try:
            n_rem = int(float(config.get("replicaNReplicas", 8)))
        except (TypeError, ValueError):
            n_rem = 8
        n_rem = max(2, min(n_rem, 32))
        try:
            t_low = float(config.get("replicaTLow", 0.8))
            t_high = float(config.get("replicaTHigh", 0.94))
        except (TypeError, ValueError):
            t_low, t_high = 0.8, 0.94
        if t_high < t_low:
            t_low, t_high = t_high, t_low
        try:
            repl_interval = int(float(config.get("replicaInterval", 10)))
        except (TypeError, ValueError):
            repl_interval = 10
        repl_interval = max(1, min(repl_interval, 10_000))
        script = f"{UPSIDE_HOME}/start/Replica_Exchange.py"
        cmd = [
            sys.executable,
            script,
            pdb_id,
            str(job_dir),
            duration,
            frame_interval,
            "False",
            str(n_rem),
            str(t_low),
            str(t_high),
            str(repl_interval),
            restraint_arg,
        ]
        return cmd, "replica"

    # Plain constant-T
    script = f"{UPSIDE_HOME}/start/Single_Replica.py"
    cmd = [
        sys.executable, script, pdb_id, str(job_dir), sim_id,
        duration, frame_interval, "False", temperature, restraint_arg,
        str(_basic_replica_count(config)),
    ]
    return cmd, "plain"


def _run_simulation(job_id: str, config: dict) -> None:
    job_dir = JOBS_DIR / job_id
    log_file = job_dir / "sim.log"
    try:
        cmd, mode = _build_simulation_command(job_dir, config)
    except Exception as exc:
        _write_status(job_dir, job_id=job_id, status="failed", error=str(exc))
        return
    if mode in ("tension", "velocity"):
        try:
            _load_calibration_module().write_force_calibration_sidecar(job_dir)
        except Exception:
            pass

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

    sim_mode = (config.get("simulationMode") or "constant").strip().lower()
    if sim_mode == "replica" and config.get("enablePulling"):
        return jsonify(
            {"error": "Replica exchange cannot be combined with pulling in this workflow."}
        ), 400

    job_id = uuid.uuid4().hex[:8]
    job_dir = JOBS_DIR / job_id
    _init_job_layout(job_dir)

    pdb_file.save(job_dir / "input.pdb")
    (job_dir / "config.json").write_text(json.dumps(config, indent=2))
    try:
        _validate_single_job_config(job_dir, config)
    except ValueError as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        return jsonify({"error": str(exc)}), 400

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
    paths = _collect_basic_trajectories(job_dir)
    if not paths:
        return jsonify({"error": "Output not ready"}), 404
    cfg: dict = {}
    cfg_path = job_dir / "config.json"
    if cfg_path.is_file():
        try:
            cfg = json.loads(cfg_path.read_text())
        except Exception:
            cfg = {}
    remd = (cfg.get("simulationMode") or "").strip().lower() == "replica"
    if len(paths) == 1:
        return send_file(
            paths[0],
            as_attachment=True,
            download_name=f"{job_id}.run.up",
        )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in paths:
            zf.write(p, arcname=p.name)
    buf.seek(0)
    zip_name = f"{job_id}_replica_exchange.zip" if remd else f"{job_id}_replicas.zip"
    return send_file(
        buf,
        as_attachment=True,
        download_name=zip_name,
        mimetype="application/zip",
    )


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

    try:
        _validate_membrane_fields(config)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if bool(config.get("enablePulling")):
        return jsonify(
            {"error": "Force sweep cannot be combined with single-job pulling in one job."}
        ), 400
    try:
        bir = int(float(config.get("basicIndependentReplicas", 1)))
    except (TypeError, ValueError):
        bir = 1
    if bir > 1:
        return jsonify(
            {
                "error": (
                    "Force sweep uses n_replicas per force only. "
                    "Do not set basicIndependentReplicas > 1 for a sweep job."
                ),
            }
        ), 400

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
    return jsonify(_load_calibration_module().load_calibration())


# ---------------------------------------------------------------------------
# Analysis (Phase 1.3 + earlier general analysis)
# ---------------------------------------------------------------------------

def _resolve_traj_for_job(job_dir: Path) -> Path | None:
    try:
        status = _read_status(job_dir)
    except Exception:
        status = {}
    if status.get("sweep_id"):
        sweep_first = _collect_sweep_trajectories_for_analysis(job_dir, None)
        if sweep_first:
            return sweep_first[0]
    paths = _collect_basic_trajectories(job_dir)
    if paths:
        return paths[0]
    sweep_paths = _collect_sweep_trajectories_for_analysis(job_dir, None)
    return sweep_paths[0] if sweep_paths else None


@app.route("/api/jobs/<job_id>/analyze", methods=["POST"])
def analyze_job(job_id):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        return jsonify({"error": "Job not found"}), 404

    body = request.get_json(silent=True) or {}
    sweep_sub = body.get("sweep_sub_dir")
    sweep_sub_str = (
        sweep_sub.strip()
        if isinstance(sweep_sub, str) and sweep_sub.strip()
        else None
    )

    try:
        status = _read_status(job_dir)
    except Exception:
        status = {}

    sweep_paths = _collect_sweep_trajectories_for_analysis(job_dir, sweep_sub_str)
    basic_paths = _collect_basic_trajectories(job_dir)

    # Force-sweep jobs must analyze sweep sub-run trajectories first. If we took
    # ``basic_paths`` while a stray ``outputs/sim/sim.run.up`` exists, we would
    # miss sweep runs or mis-label every row as parent folder ``sim``.
    if status.get("sweep_id") and sweep_paths:
        paths = sweep_paths
        paths_from_sweep = True
        force_sweep_multi = True
    elif basic_paths:
        paths = basic_paths
        paths_from_sweep = False
        force_sweep_multi = False
    elif sweep_paths:
        paths = sweep_paths
        paths_from_sweep = True
        force_sweep_multi = True
    else:
        paths = []
        paths_from_sweep = False
        force_sweep_multi = False
    if not paths:
        return jsonify({"error": "Trajectory not ready"}), 400

    cfg: dict = {}
    cfg_path = job_dir / "config.json"
    if cfg_path.is_file():
        try:
            cfg = json.loads(cfg_path.read_text())
        except Exception:
            cfg = {}

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
    analysis_dir.mkdir(parents=True, exist_ok=True)

    def attach_urls_flat(results: dict) -> None:
        for _key, result in results.items():
            if not isinstance(result, dict):
                continue
            image = result.pop("image", None)
            if image:
                result["image_url"] = f"/api/jobs/{job_id}/analysis/{Path(image).name}"

    def attach_urls_nested(results: dict, label: str) -> None:
        for _key, result in results.items():
            if not isinstance(result, dict):
                continue
            image = result.pop("image", None)
            if image:
                result["image_url"] = (
                    f"/api/jobs/{job_id}/analysis/replicas/{label}/{Path(image).name}"
                )

    try:
        if len(paths) == 1:
            traj_file = paths[0]
            results = dynalab.run_analyses(
                str(traj_file), str(analysis_dir), requested, params=params,
            )
            attach_urls_flat(results)
            payload = results
        else:
            per: dict[str, dict] = {}
            labels: list[str] = []
            parents_resolved = [traj.parent.resolve() for traj in paths]
            same_parent = len(set(parents_resolved)) == 1
            for traj in paths:
                # Sweep trajectories all end in .../outputs/sim/sim.run.up — never use
                # ``traj.parent.name`` (``sim``) as the replica key.
                label = _sweep_subdir_label_from_traj(traj, job_dir)
                if label is None and paths_from_sweep:
                    rp = traj.resolve()
                    if len(rp.parents) >= 3:
                        label = rp.parents[2].name
                    else:
                        label = traj.stem if same_parent else traj.parent.name
                elif label is None and same_parent:
                    label = traj.stem
                elif label is None:
                    label = traj.parent.name
                labels.append(label)
                subdir = analysis_dir / "replicas" / label
                subdir.mkdir(parents=True, exist_ok=True)
                res = dynalab.run_analyses(
                    str(traj), str(subdir), requested, params=params,
                )
                attach_urls_nested(res, label)
                per[label] = res
            if force_sweep_multi and len(paths) > 1:
                ensemble_kind = "force_sweep"
                agg: dict = {}
            else:
                ensemble_kind = (
                    "replica_exchange"
                    if (cfg.get("simulationMode") or "").strip().lower() == "replica"
                    else "independent"
                )
                agg = _aggregate_analysis_across_replicas(per, ensemble_kind)
            payload = {
                "multi_replica": True,
                "ensemble_kind": ensemble_kind,
                "replica_labels": labels,
                "replicas": per,
                "aggregate": agg,
            }
    except Exception as exc:
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500

    (analysis_dir / "results.json").write_text(json.dumps(payload, indent=2, default=str))
    return jsonify({"job_id": job_id, "results": payload})


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


@app.route("/api/jobs/<job_id>/analysis/download-all", methods=["GET"])
def download_all_job_analysis(job_id):
    """Zip everything under ``jobs/<job_id>/analysis`` (flat + ``replicas/``)."""
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        return jsonify({"error": "Job not found"}), 404
    analysis_dir = (job_dir / "analysis").resolve()
    if not analysis_dir.is_dir():
        return jsonify({"error": "No analysis directory"}), 404
    buf = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in analysis_dir.rglob("*"):
            if not path.is_file():
                continue
            try:
                arc = path.resolve().relative_to(analysis_dir)
            except ValueError:
                continue
            zf.write(path, arcname=str(arc).replace("\\", "/"))
            count += 1
    if count == 0:
        return jsonify({"error": "Analysis folder is empty"}), 404
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{job_id}_analysis.zip",
    )


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

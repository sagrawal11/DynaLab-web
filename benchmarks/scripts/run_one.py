#!/usr/bin/env python3
"""Run a single Upside2 simulation case and capture metrics.

Reads a case config (one entry from ``benchmarks/matrix.json``), runs the
appropriate ``start/`` script, and writes a ``result.json`` with:

    wall_seconds, cpu_user_seconds, cpu_sys_seconds,
    peak_rss_kb, peak_rss_mb, output_bytes, output_mb,
    steps_per_second, seconds_per_1M_steps,
    exit_code, ok, started_at, finished_at, host, work_dir

Memory measurement uses ``resource.getrusage(RUSAGE_CHILDREN)``. On Linux
``ru_maxrss`` is in kilobytes (this is the assumption); on macOS it is bytes.
The dev container is Linux, so this is fine in the intended runtime.

Examples
--------
::

    python benchmarks/scripts/run_one.py \\
        --case-json '{"case_id":"smoke","mode":"constant","pdb_id":"chig", \\
                      "pdb_source":"example/01.GettingStarted/pdb/chig.pdb", \\
                      "duration":5000,"frame_interval":200,"temperature":"0.85"}' \\
        --output-dir benchmarks/results/smoke
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import resource
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from dynalab_paths import find_dynalab_root  # noqa: E402


def _project_root_from(_env_upside_home: str | None) -> Path:
    return find_dynalab_root()


def measure_dir_size_bytes(p: Path) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(p):
        for f in filenames:
            try:
                total += (Path(dirpath) / f).stat().st_size
            except OSError:
                pass
    return total


def count_residues(pdb_path: Path) -> int:
    seen: set[tuple[str, str]] = set()
    try:
        with pdb_path.open() as f:
            for line in f:
                if line.startswith(("ATOM  ", "HETATM")):
                    chain = line[21:22]
                    resseq = line[22:27].strip()
                    seen.add((chain, resseq))
    except OSError:
        return 0
    return len(seen)


# ---------------------------------------------------------------------------
# Pulling helpers — mirror start/Force_Sweep.py so tension/velocity cases
# write the same Tension_Simulations.dat / Velocity_Simulations.dat layout.
# ---------------------------------------------------------------------------

def count_ca_residues(pdb_path: Path) -> int:
    """Count Cα atoms (Upside uses 0-based residue indexing)."""
    count = 0
    for line in pdb_path.read_text().splitlines():
        if line.startswith(("ATOM ", "HETATM")) and line[12:16].strip() == "CA":
            count += 1
    return count


def resolve_pull_residue(pdb_path: Path, pull_residue: int) -> int:
    """Translate ``pull_residue=-1`` into the last Cα residue index."""
    if pull_residue >= 0:
        return pull_residue
    ca_count = count_ca_residues(pdb_path)
    if ca_count == 0:
        raise RuntimeError(f"Could not determine last CA residue in {pdb_path}")
    return ca_count - 1


def read_calibration_factor(upside_home: Path) -> float:
    """Return pN per Upside-force unit (default 41.4)."""
    fc_path = upside_home / "analysis" / "force_calibration.py"
    if not fc_path.is_file():
        return 41.4
    spec = importlib.util.spec_from_file_location("_dynalab_fc_bench", fc_path)
    if spec is None or spec.loader is None:
        return 41.4
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        return float(mod.pn_per_upside_force_unit())
    except Exception:
        return 41.4


def write_force_calibration_sidecar(work_dir: Path, upside_home: Path, factor: float) -> None:
    fc_path = upside_home / "analysis" / "force_calibration.py"
    if not fc_path.is_file():
        return
    spec = importlib.util.spec_from_file_location("_dynalab_fc_sidecar", fc_path)
    if spec is None or spec.loader is None:
        return
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        mod.write_force_calibration_sidecar(work_dir, factor)
    except Exception:
        pass


def write_tension_dat(
    work_dir: Path,
    anchor: int,
    puller: int,
    force_upside: float,
) -> None:
    """Equal and opposite +z tensions on anchor and puller (Force_Sweep convention)."""
    p = work_dir / "Tension_Simulations.dat"
    p.write_text(
        "residue tension_x tension_y tension_z\n"
        f"{int(anchor)} 0.0 0.0 -{force_upside:.6f}\n"
        f"{int(puller)} 0.0 0.0 {force_upside:.6f}\n"
    )


def write_velocity_dat(
    work_dir: Path,
    anchor: int,
    puller: int,
    vel_z: float,
    spring_k: float = 0.05,
) -> None:
    """Velocity-clamp pull along +z at puller; anchor pinned by spring."""
    p = work_dir / "Velocity_Simulations.dat"
    p.write_text(
        "residue spring_const pulling_vel_x pulling_vel_y pulling_vel_z\n"
        f"{int(anchor)} {spring_k} 0.0 0.0 0.0\n"
        f"{int(puller)} {spring_k} 0.0 0.0 {vel_z:.6f}\n"
    )


def setup_pulling_sidecars(
    work_dir: Path,
    case: dict,
    upside_home: Path,
) -> None:
    """Write .dat pulling tables for tension or velocity benchmark cases."""
    pdb_path = work_dir / "input.pdb"
    anchor = int(case.get("anchor_residue", 0))
    puller = resolve_pull_residue(pdb_path, int(case.get("pull_residue", -1)))
    mode = case["mode"]

    if mode == "tension":
        factor = read_calibration_factor(upside_home)
        force_upside = float(case.get("tension_pn", 22.0)) / factor
        write_tension_dat(work_dir, anchor, puller, force_upside)
        write_force_calibration_sidecar(work_dir, upside_home, factor)
    elif mode == "velocity":
        # Match Force_Sweep default unless overridden in the matrix case.
        vel_z = float(case.get("velocity_z", case.get("velocity_x", -0.001)))
        spring_k = float(case.get("spring_const", 0.05))
        write_velocity_dat(work_dir, anchor, puller, vel_z, spring_k)
    else:
        raise ValueError(f"setup_pulling_sidecars called for mode={mode!r}")


# ---------------------------------------------------------------------------
# Command builders — one per mode, mirroring web/server/app.py conventions.
# ---------------------------------------------------------------------------

def build_command(case: dict, work_dir: Path, upside_home: Path) -> list[str]:
    mode = case["mode"]
    pdb_id = "input"  # always "input" — we copy the source PDB to <work>/input.pdb
    duration = str(int(float(case["duration"])))
    frame_interval = str(int(case.get("frame_interval", 200)))
    temperature = str(case.get("temperature", "0.85"))
    py = sys.executable
    upside_home_str = str(upside_home)

    if mode == "constant":
        n_rep = int(case.get("n_replicas", 1))
        return [
            py, f"{upside_home_str}/start/Single_Replica.py",
            pdb_id, str(work_dir), "sim",
            duration, frame_interval, "False", temperature, "None",
            str(n_rep),
        ]

    if mode == "replica_exchange":
        n_rem = int(case.get("n_replicas", 8))
        t_low = str(case.get("t_low", "0.80"))
        t_high = str(case.get("t_high", "0.94"))
        repl_int = str(int(case.get("replica_interval", 10)))
        return [
            py, f"{upside_home_str}/start/Replica_Exchange.py",
            pdb_id, str(work_dir),
            duration, frame_interval, "False",
            str(n_rem), t_low, t_high, repl_int, "None",
        ]

    if mode == "tension":
        return [
            py, f"{upside_home_str}/start/Pulling_Simulations.py",
            pdb_id, str(work_dir), "sim",
            duration, frame_interval, "tension", "False", temperature, "None",
        ]

    if mode == "velocity":
        return [
            py, f"{upside_home_str}/start/Pulling_Simulations.py",
            pdb_id, str(work_dir), "sim",
            duration, frame_interval, "velocity", "False", temperature, "None",
        ]

    if mode == "force_sweep":
        forces_pn = case["forces_pn"]
        n_replicas = int(case.get("n_replicas", 2))
        sweep_dir = work_dir / "sweep"
        sweep_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            py, f"{upside_home_str}/start/Force_Sweep.py",
            "--pdb", str(work_dir / "input.pdb"),
            "--sweep-dir", str(sweep_dir),
            "--manifest", str(sweep_dir / "manifest.json"),
            "--upside-home", upside_home_str,
            "--duration", duration,
            "--frame-interval", frame_interval,
            "--temperature", temperature,
            "--anchor-residue", str(case.get("anchor_residue", 0)),
            "--pull-residue", str(case.get("pull_residue", -1)),
            "--n-replicas", str(n_replicas),
            "--sim-type", case.get("sim_type", "tension"),
            "--forces-pn", ",".join(str(f) for f in forces_pn),
        ]
        if "max_parallel" in case:
            cmd += ["--max-parallel", str(int(case["max_parallel"]))]
        return cmd

    raise ValueError(f"Unknown mode: {mode!r}. Valid modes: constant, replica_exchange, "
                     "tension, velocity, force_sweep")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_case(case: dict, output_dir: Path, upside_home: Path) -> dict[str, Any]:
    # Start scripts (Single_Replica.py, etc.) receive pdb_dir as argv and run
    # with cwd=work_dir. Relative pdb_dir values break path resolution inside
    # those scripts — always pass absolute paths.
    upside_home = upside_home.resolve()
    output_dir = output_dir.resolve()
    case_id = case["case_id"]
    work_dir = output_dir / case_id / "work"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)

    # Resolve and copy the source PDB into <work_dir>/input.pdb.
    pdb_source = Path(case["pdb_source"])
    if not pdb_source.is_absolute():
        pdb_source = upside_home / pdb_source
    if not pdb_source.is_file():
        raise FileNotFoundError(f"PDB not found: {pdb_source}")
    shutil.copy(pdb_source, work_dir / "input.pdb")

    # Mode-specific setup files (pulling .dat sidecars).
    if case["mode"] in ("tension", "velocity"):
        setup_pulling_sidecars(work_dir, case, upside_home)

    # Environment for the child.
    env = os.environ.copy()
    env["UPSIDE_HOME"] = str(upside_home)
    env["PYTHONPATH"] = f"{upside_home}/py:" + env.get("PYTHONPATH", "")
    env["PATH"] = f"{upside_home}/py:{upside_home}/obj:" + env.get("PATH", "")
    if "omp_threads" in case:
        env["OMP_NUM_THREADS"] = str(int(case["omp_threads"]))

    cmd = build_command(case, work_dir, upside_home)
    log_path = work_dir / "bench.log"

    rusage_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    started = time.time()
    started_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started))

    with log_path.open("w") as logfp:
        logfp.write(f"# case_id={case_id}\n# host={socket.gethostname()}\n")
        logfp.write(f"# OMP_NUM_THREADS={env.get('OMP_NUM_THREADS', '<unset>')}\n")
        logfp.write(f"# cmd={' '.join(cmd)}\n\n")
        logfp.flush()
        proc = subprocess.run(
            cmd,
            stdout=logfp,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=str(work_dir),
        )

    finished = time.time()
    rusage_after = resource.getrusage(resource.RUSAGE_CHILDREN)
    wall_seconds = finished - started
    cpu_user = rusage_after.ru_utime - rusage_before.ru_utime
    cpu_sys = rusage_after.ru_stime - rusage_before.ru_stime
    peak_rss_kb = rusage_after.ru_maxrss
    if platform.system() == "Darwin":
        # macOS reports bytes; convert to KB to match Linux convention.
        peak_rss_kb = peak_rss_kb // 1024

    output_bytes = measure_dir_size_bytes(work_dir)
    n_residues = count_residues(work_dir / "input.pdb")

    result: dict[str, Any] = {
        "case_id": case_id,
        "case": case,
        "n_residues": n_residues,
        "exit_code": proc.returncode,
        "ok": proc.returncode == 0,
        "wall_seconds": wall_seconds,
        "cpu_user_seconds": cpu_user,
        "cpu_sys_seconds": cpu_sys,
        "peak_rss_kb": peak_rss_kb,
        "peak_rss_mb": peak_rss_kb / 1024.0,
        "output_bytes": output_bytes,
        "output_mb": output_bytes / (1024.0 * 1024.0),
        "started_at": started_iso,
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(finished)),
        "host": socket.gethostname(),
        "work_dir": str(work_dir),
    }

    duration = int(float(case.get("duration", 0)))
    if duration > 0 and wall_seconds > 0 and proc.returncode == 0:
        result["steps_per_second"] = duration / wall_seconds
        result["seconds_per_1M_steps"] = wall_seconds / (duration / 1_000_000.0)

    # Force-sweep aggregates: count sub-jobs by force × replica.
    if case["mode"] == "force_sweep":
        forces_pn = case.get("forces_pn", [])
        n_replicas = int(case.get("n_replicas", 2))
        result["sweep_subjobs"] = len(forces_pn) * n_replicas

    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--case-file", help="Path to a single-case JSON file")
    g.add_argument("--case-json", help="Inline single-case JSON")
    ap.add_argument("--output-dir", required=True, help="Directory to write result.json into")
    return ap.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    if args.case_file:
        case = json.loads(Path(args.case_file).read_text())
    else:
        case = json.loads(args.case_json)

    upside_home = _project_root_from(os.environ.get("UPSIDE_HOME"))
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    result = run_case(case, output_dir, upside_home)
    out = output_dir / case["case_id"] / "result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str))

    summary = {k: v for k, v in result.items() if k != "case"}
    print(json.dumps(summary, indent=2, default=str))
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

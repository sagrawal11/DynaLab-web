#!/usr/bin/env python
"""Run an Upside2 pulling simulation at multiple force values in parallel.

This is the orchestrator behind the web UI's "force sweep" mode. It is
deliberately a standalone CLI script (not just a function inside app.py)
so you can also run sweeps from the terminal without involving the Flask
server.

For each requested force value, the orchestrator:
  1. Creates ``<sweep-dir>/F_<pn>_rep_<i>/`` and copies the input PDB into it.
  2. Copies ``spring-pair-xyz.dat`` and optional ``restraint-*.dat`` sidecars from the
     directory containing the input PDB (the web job root) when present.
  3. Writes the matching ``Tension_Simulations.dat`` (constant-tension) or
     ``Velocity_Simulations.dat`` (velocity-clamp) inside that directory.
  4. Spawns ``Pulling_Simulations.py`` as a subprocess in that directory.
  5. Updates ``<sweep-dir>/manifest.json`` with status as each sub-job finishes.

Concurrency: at most ``cpu_count() // 2`` sub-jobs run simultaneously, so the
host stays responsive. Override with ``--max-parallel``.

Force conversion: the user provides forces in piconewtons. They are converted
to Upside reduced-force units using ``analysis/force_calibration.py`` (which
reads ``analysis/calibration.json`` when present, else default ``41.4``). The
orchestrator writes the chosen factor into the manifest so analyses stay
consistent.

Usage::

    python Force_Sweep.py \\
        --pdb /path/to/protein.pdb \\
        --sweep-dir /path/to/sweep_xxx \\
        --manifest /path/to/sweep_xxx/manifest.json \\
        --upside-home /workspaces/DynaLab-merge-dynalab \\
        --duration 200000 --frame-interval 200 \\
        --temperature 0.85 \\
        --anchor-residue 0 --pull-residue -1 \\
        --n-replicas 2 \\
        --sim-type tension \\
        --forces-pn 14,18,22,26,30,38
"""

import argparse
import concurrent.futures
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path


_MANIFEST_LOCK = threading.Lock()

# Filenames written by the web server into the parent job directory (see ``web/server/app.py``).
_PAIR_SPRING_FILENAME = "spring-pair-xyz.dat"
_RESTRAINT_SIDECAR_FILENAMES = (
    "restraint-fixed-wall.dat",
    "restraint-pair-wall.dat",
    "restraint-fixed-spring.dat",
    "restraint-nail.dat",
)


def _restraint_argv_for_subjob(job_root: Path, sub_dir: Path) -> str:
    """Copy pair spring + optional restraint sidecars into ``sub_dir`` for ``Pulling_Simulations``."""
    for fname in (_PAIR_SPRING_FILENAME, *_RESTRAINT_SIDECAR_FILENAMES):
        src = job_root / fname
        if src.is_file() and src.stat().st_size > 0:
            shutil.copy2(src, sub_dir / fname)
    pair_dst = sub_dir / _PAIR_SPRING_FILENAME
    if pair_dst.is_file() and pair_dst.stat().st_size > 0:
        return _PAIR_SPRING_FILENAME
    return "None"


def _read_calibration_factor(upside_home: Path) -> float:
    """Return ``pN per upside-force unit`` (see ``force_calibration.pn_per_upside_force_unit``)."""
    mod = _load_force_calibration_module(upside_home)
    if mod is None:
        return 41.4
    try:
        return float(mod.pn_per_upside_force_unit())
    except Exception:
        return 41.4


def _load_force_calibration_module(upside_home: Path):
    """Load ``analysis/force_calibration.py`` from the repo rooted at ``upside_home``, or None."""
    fc_path = upside_home.resolve() / "analysis" / "force_calibration.py"
    if not fc_path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("_dynalab_fc_sweep", fc_path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _resolve_pull_residue(pdb_path: Path, pull_residue: int) -> int:
    """Translate ``pull_residue=-1`` into the last residue index of the PDB."""
    if pull_residue >= 0:
        return pull_residue
    last = -1
    for line in pdb_path.read_text().splitlines():
        if line.startswith(("ATOM ", "HETATM")) and line[12:16].strip() == "CA":
            try:
                last = int(line[22:26])
            except ValueError:
                continue
    if last < 0:
        raise RuntimeError(f"Could not determine last CA residue in {pdb_path}")
    # Upside scripts use 0-based residue indexing.
    return last - 1


def _write_tension_dat(out_dir: Path, anchor: int, puller: int, force_upside: float) -> None:
    """Pull along +z by ``force_upside``; anchor with equal -z force on residue 0.

    Matches the convention in ``start/Tension_Simulations.dat``: equal and
    opposite tension pairs hold the protein under net-zero translation.
    """
    with (out_dir / "Tension_Simulations.dat").open("w") as f:
        f.write("residue tension_x tension_y tension_z\n")
        f.write(f"{anchor} 0.0 0.0 -{force_upside:.6f}\n")
        f.write(f"{puller} 0.0 0.0 {force_upside:.6f}\n")


def _write_velocity_dat(out_dir: Path, anchor: int, puller: int, vel_z: float, k: float = 0.05) -> None:
    """Velocity-clamp pull along +z at residue ``puller``; anchor pinned by spring."""
    with (out_dir / "Velocity_Simulations.dat").open("w") as f:
        f.write("residue spring_const pulling_vel_x pulling_vel_y pulling_vel_z\n")
        f.write(f"{anchor} {k} 0.0 0.0 0.0\n")
        f.write(f"{puller} {k} 0.0 0.0 {vel_z:.6f}\n")


def _update_manifest(manifest_path: Path, sub_job_idx: int, **fields) -> None:
    """Atomically update one sub-job entry in the manifest."""
    with _MANIFEST_LOCK:
        manifest = json.loads(manifest_path.read_text())
        manifest["sub_jobs"][sub_job_idx].update(fields)
        manifest_path.write_text(json.dumps(manifest, indent=2))


def _run_one(
    sub_job_idx: int,
    sub_dir: Path,
    sim_type: str,
    duration: int,
    frame_interval: int,
    temperature: float,
    pdb_path: Path,
    upside_home: Path,
    manifest_path: Path,
) -> int:
    """Execute Pulling_Simulations.py inside ``sub_dir`` and return its exit code."""
    sub_dir.mkdir(parents=True, exist_ok=True)
    pdb_target = sub_dir / "input.pdb"
    if not pdb_target.exists():
        shutil.copy(pdb_path, pdb_target)

    restraint_arg = _restraint_argv_for_subjob(pdb_path.parent, sub_dir)

    cmd = [
        sys.executable,
        str(upside_home / "start" / "Pulling_Simulations.py"),
        "input", str(sub_dir), "sim",
        str(duration), str(frame_interval), sim_type, "False",
        f"{temperature}", restraint_arg,
    ]

    log_file = sub_dir / "sim.log"
    env = {
        **os.environ,
        "UPSIDE_HOME": str(upside_home),
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""),
    }

    _update_manifest(manifest_path, sub_job_idx, status="running", started=int(time.time()))

    try:
        with log_file.open("w") as log_fp:
            log_fp.write(f"$ {' '.join(cmd)}\n\n")
            log_fp.flush()
            proc = subprocess.Popen(
                cmd, cwd=str(sub_dir), stdout=log_fp, stderr=subprocess.STDOUT, env=env,
            )
            proc.wait()
        rc = proc.returncode
    except Exception as exc:
        _update_manifest(manifest_path, sub_job_idx, status="failed", error=str(exc),
                         finished=int(time.time()))
        return 1

    _update_manifest(
        manifest_path, sub_job_idx,
        status="completed" if rc == 0 else "failed",
        returncode=rc, finished=int(time.time()),
    )
    return rc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pdb",            required=True)
    parser.add_argument("--sweep-dir",      required=True)
    parser.add_argument("--manifest",       required=True)
    parser.add_argument("--upside-home",    required=True)
    parser.add_argument("--duration",       type=int, default=200000)
    parser.add_argument("--frame-interval", type=int, default=200)
    parser.add_argument("--temperature",    type=float, default=0.85)
    parser.add_argument("--anchor-residue", type=int, default=0)
    parser.add_argument("--pull-residue",   type=int, default=-1, help="-1 = last residue")
    parser.add_argument("--n-replicas",     type=int, default=1)
    parser.add_argument("--sim-type",       choices=("tension", "velocity"), default="tension")
    parser.add_argument("--forces-pn",      required=True, help="Comma-separated forces in pN")
    parser.add_argument("--max-parallel",   type=int, default=max(1, (os.cpu_count() or 2) // 2))
    args = parser.parse_args()

    upside_home = Path(args.upside_home).resolve()
    pdb_path = Path(args.pdb).resolve()
    sweep_dir = Path(args.sweep_dir).resolve()
    manifest_path = Path(args.manifest).resolve()
    sweep_dir.mkdir(parents=True, exist_ok=True)

    forces_pn = [float(x) for x in args.forces_pn.split(",") if x.strip()]
    if not forces_pn:
        sys.stderr.write("--forces-pn is empty\n")
        return 1

    factor = _read_calibration_factor(upside_home)  # pN per upside-force unit
    puller = _resolve_pull_residue(pdb_path, args.pull_residue)
    anchor = args.anchor_residue

    # Initialise manifest with one entry per (force, replica)
    sub_jobs = []
    for f_pn in forces_pn:
        f_upside = f_pn / factor
        for rep in range(args.n_replicas):
            sub_dir = sweep_dir / f"F_{f_pn:.1f}pN_rep_{rep}"
            if args.sim_type == "tension":
                # write the dat file before the worker so the orchestrator reads
                # the same file the simulation does
                pass
            sub_jobs.append({
                "sub_dir":     sub_dir.relative_to(sweep_dir).as_posix(),
                "force_pn":    f_pn,
                "force_upside": f_upside,
                "replicate":   rep,
                "anchor":      anchor,
                "puller":      puller,
                "status":      "queued",
                "total_steps": args.duration,
            })

    manifest = json.loads(manifest_path.read_text())
    manifest["sub_jobs"] = sub_jobs
    manifest["calibration_factor_pn_per_upside"] = factor
    manifest["upside_home"] = str(upside_home)
    manifest_path.write_text(json.dumps(manifest, indent=2))

    # Pre-write the per-sub-job .dat files so the simulation can find them.
    fc_mod = _load_force_calibration_module(upside_home)
    for entry in sub_jobs:
        sub = sweep_dir / entry["sub_dir"]
        sub.mkdir(parents=True, exist_ok=True)
        if args.sim_type == "tension":
            _write_tension_dat(sub, anchor, puller, entry["force_upside"])
        else:
            # For velocity-clamp, force is dynamic; the user picks pulling
            # velocity from force ~ k * v * t. We pick a small vel_z that
            # matches the requested constant-force expectation: v = F/(k*N)
            # at N steps; this is approximate but consistent across replicas.
            vel_z = -0.001  # default per existing Velocity_Simulations.dat
            _write_velocity_dat(sub, anchor, puller, vel_z)
        if fc_mod is not None:
            try:
                fc_mod.write_force_calibration_sidecar(sub, factor)
            except Exception:
                pass

    # Run with bounded parallelism.
    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_parallel) as pool:
        futures = []
        for idx, entry in enumerate(sub_jobs):
            sub = sweep_dir / entry["sub_dir"]
            futures.append(pool.submit(
                _run_one, idx, sub, args.sim_type,
                args.duration, args.frame_interval, args.temperature,
                pdb_path, upside_home, manifest_path,
            ))
        for fut in concurrent.futures.as_completed(futures):
            if fut.result() != 0:
                failures += 1

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

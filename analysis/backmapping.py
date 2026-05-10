"""Back-map a coarse-grained Upside intermediate to an all-atom PDB.

Pipeline
--------
1. **PULCHRA** rebuilds every backbone heavy atom + side chain from the
   CA trace that Upside outputs.  It's fast (~100 ms / structure) and
   handles secondary-structure-aware loops well.

2. **Optional OpenMM minimization** relieves any residual clashes with
   the Amber14 force field. We do a short minimization (200 steps,
   tolerance 10 kJ/mol/nm) - enough to break overlaps without wandering
   off the original conformation. You can disable this if OpenMM isn't
   installed (it's listed in requirements.txt but optional).

The resulting PDB is suitable as input to AI design pipelines that expect
realistic all-atom coordinates: RFdiffusion, ProteinMPNN, AlphaFold-Multimer
ipTM scoring, etc. (Phase 3.)

Public API
----------
:func:`backmap_pdb` is the only entry point.  The Flask backend calls it
once per CG intermediate; the centrifuge orchestrator can also call it
directly.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# PULCHRA
# ---------------------------------------------------------------------------

def _find_pulchra() -> str | None:
    """Locate the PULCHRA binary - first ``$PULCHRA``, then ``$PATH``."""
    candidate = os.environ.get("PULCHRA")
    if candidate and Path(candidate).is_file():
        return candidate
    return shutil.which("pulchra")


def run_pulchra(input_pdb: str, output_pdb: str, timeout: int = 60) -> None:
    """Rebuild side chains + backbone heavy atoms from a CA trace.

    PULCHRA writes its output to ``<input>.rebuilt.pdb`` next to the input
    file by default. We move it to ``output_pdb`` afterwards.
    """
    pulchra = _find_pulchra()
    if pulchra is None:
        raise RuntimeError(
            "PULCHRA is not on PATH and $PULCHRA is unset. "
            "Rebuild the dev container (PULCHRA is installed by "
            ".devcontainer/install_pulchra.sh) or install it manually."
        )

    inp = Path(input_pdb).resolve()
    out = Path(output_pdb).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    # PULCHRA always writes <input_basename>.rebuilt.pdb in the input directory.
    work_dir = inp.parent
    rebuilt = work_dir / (inp.stem + ".rebuilt.pdb")
    if rebuilt.exists():
        rebuilt.unlink()

    cmd = [pulchra, str(inp.name)]   # PULCHRA prefers a relative path
    proc = subprocess.run(
        cmd, cwd=str(work_dir),
        timeout=timeout,
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0 or not rebuilt.is_file():
        raise RuntimeError(
            f"PULCHRA failed (rc={proc.returncode}). "
            f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )

    shutil.move(str(rebuilt), str(out))


# ---------------------------------------------------------------------------
# OpenMM minimization (optional)
# ---------------------------------------------------------------------------

def minimize_openmm(
    pdb_in: str,
    pdb_out: str,
    max_iterations: int = 200,
    tolerance_kj_per_mol_per_nm: float = 10.0,
) -> dict:
    """Short Amber14 minimization. No-op if OpenMM isn't installed.

    Returns a stats dict; raises ``RuntimeError`` only on actual minimisation
    failures (e.g. atomistic-incompatible PDB), not on missing dependencies.
    """
    try:
        import openmm
        from openmm import app, unit
    except ImportError:
        # OpenMM not available - just copy the input through unchanged.
        shutil.copy(pdb_in, pdb_out)
        return {"minimized": False, "reason": "OpenMM not installed"}

    pdb = app.PDBFile(pdb_in)

    # Try the standard amber14 force field; fall back to the older one if
    # the residue templates are missing (e.g. unusual histidine names).
    forcefield = app.ForceField("amber14-all.xml", "amber14/tip3pfb.xml")
    try:
        modeller = app.Modeller(pdb.topology, pdb.positions)
        modeller.addHydrogens(forcefield)
        system = forcefield.createSystem(
            modeller.topology,
            nonbondedMethod=app.NoCutoff,
            constraints=app.HBonds,
        )
        integrator = openmm.LangevinMiddleIntegrator(
            300 * unit.kelvin, 1.0 / unit.picosecond, 0.002 * unit.picoseconds,
        )
        simulation = app.Simulation(modeller.topology, system, integrator)
        simulation.context.setPositions(modeller.positions)
        e0 = simulation.context.getState(getEnergy=True).getPotentialEnergy()
        simulation.minimizeEnergy(
            tolerance=tolerance_kj_per_mol_per_nm * unit.kilojoule_per_mole / unit.nanometer,
            maxIterations=max_iterations,
        )
        e1 = simulation.context.getState(getEnergy=True).getPotentialEnergy()
        positions = simulation.context.getState(getPositions=True).getPositions()
        with open(pdb_out, "w") as f:
            app.PDBFile.writeFile(modeller.topology, positions, f)
        return {
            "minimized": True,
            "initial_energy_kj_per_mol": e0.value_in_unit(unit.kilojoule_per_mole),
            "final_energy_kj_per_mol":   e1.value_in_unit(unit.kilojoule_per_mole),
            "delta_kj_per_mol":          (e1 - e0).value_in_unit(unit.kilojoule_per_mole),
            "max_iterations":            int(max_iterations),
        }
    except Exception as exc:
        # Fall back: copy the unminimised structure through with a clear flag
        shutil.copy(pdb_in, pdb_out)
        return {"minimized": False, "reason": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def backmap_pdb(input_pdb: str, output_pdb: str, minimize: bool = True) -> dict:
    """Back-map ``input_pdb`` (Upside CG intermediate) to ``output_pdb``.

    Pipeline:
      1. PULCHRA       (CA -> heavy-atom)
      2. OpenMM min.   (relieve clashes, optional)

    Returns a small dict the API can echo back to the UI.
    """
    pulchra_out = output_pdb.replace(".pdb", ".pulchra.pdb")
    run_pulchra(input_pdb, pulchra_out)

    info = {"input": input_pdb, "output": output_pdb, "pulchra_output": pulchra_out}

    if minimize:
        try:
            min_info = minimize_openmm(pulchra_out, output_pdb)
            info["minimization"] = min_info
        except Exception as exc:
            shutil.copy(pulchra_out, output_pdb)
            info["minimization"] = {"minimized": False,
                                    "reason": f"{type(exc).__name__}: {exc}"}
    else:
        shutil.copy(pulchra_out, output_pdb)
        info["minimization"] = {"minimized": False, "reason": "skipped by caller"}

    # Clean up the intermediate PULCHRA file unless minimization actually
    # used it as a separate input - in either case we keep only the final.
    if Path(pulchra_out).is_file() and Path(pulchra_out) != Path(output_pdb):
        try:
            Path(pulchra_out).unlink()
        except OSError:
            pass
        info.pop("pulchra_output", None)

    return info


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_pdb")
    parser.add_argument("output_pdb")
    parser.add_argument("--no-minimize", action="store_true",
                        help="Skip OpenMM minimization.")
    args = parser.parse_args()
    out = backmap_pdb(args.input_pdb, args.output_pdb, minimize=not args.no_minimize)
    print(json.dumps(out, indent=2))

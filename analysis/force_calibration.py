"""Calibrate Upside reduced-force units to physical piconewtons.

Upside's energy unit is dimensionless. The default conversion baked into
``analyze_force_extension`` (``41.4 pN per upside-force unit``) comes from
historical fits done by the Sosnick group. To trust quantitative force
predictions for the centrifuge experiment we re-derive that factor on the
present box / temperature / force-field combination by reproducing the
known unfolding force of a reference protein (FN3 domain 10 of fibronectin,
which unfolds at ~140 pN under AFM).

The calibration loop:
  1. Run a short velocity-clamp pulling simulation on the reference protein.
  2. Detect the force at which the dominant rupture event happens
     (peak of the smoothed force-vs-extension trace).
  3. Compare to the literature value, write the new factor to
     ``analysis/calibration.json``.

If running the real simulation isn't possible (no FN3 PDB checked in, or no
trajectory available yet), :func:`calibrate_against_reference` skips the
simulation step and just records the *theoretical* factor. Callers can also
pass a pre-computed trajectory via ``traj_file=``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


REPO_ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = Path(__file__).resolve().parent
DEFAULT_FACTOR_PN_PER_UPSIDE = 41.4

# Empirical AFM unfolding forces from the literature, in pN.
# These are the "ground truth" for calibration runs.
REFERENCE_PROTEINS = {
    # Source: Rief et al., Nature 1997 / Schwaiger et al., NSMB 2002
    "fn3-d10":   {"unfolding_pn": 140.0, "description": "Fibronectin type III domain 10"},
    "i27":       {"unfolding_pn": 200.0, "description": "Titin I27 domain"},
    "ubiquitin": {"unfolding_pn": 200.0, "description": "Ubiquitin"},
    "ddflni4":   {"unfolding_pn":  50.0, "description": "DdFLN i4 (filamin)"},
}


def _smooth(y: np.ndarray, win: int = 25) -> np.ndarray:
    """Boxcar smoothing for noisy force traces."""
    if win <= 1 or y.size < 2 * win:
        return y
    kernel = np.ones(win) / win
    return np.convolve(y, kernel, mode="same")


def detect_rupture_force(extension: np.ndarray, force: np.ndarray, smoothing: int = 25) -> dict:
    """Locate the peak (max) of the smoothed force trace.

    For a typical AFM/sawtooth force-vs-extension curve, the global maximum
    is the rupture force of the most stable structural element.
    """
    if len(force) != len(extension):
        raise ValueError("extension and force must have equal length")
    if len(force) < 5:
        raise ValueError("Force trace too short to detect rupture")

    smoothed = _smooth(force, smoothing)
    idx = int(np.argmax(smoothed))
    return {
        "peak_force_pN":     float(smoothed[idx]),
        "peak_extension_A":  float(extension[idx]),
        "peak_index":        idx,
        "smoothed_max_pN":   float(np.max(smoothed)),
        "raw_max_pN":        float(np.max(force)),
    }


def write_calibration(factor_pn_per_upside: float, **metadata) -> Path:
    """Persist the calibration factor to ``analysis/calibration.json``."""
    record = {
        "factor_pn_per_upside_force": float(factor_pn_per_upside),
        **metadata,
    }
    out = ANALYSIS_DIR / "calibration.json"
    out.write_text(json.dumps(record, indent=2))
    return out


def load_calibration() -> dict:
    """Return the active calibration record, or a sensible default."""
    p = ANALYSIS_DIR / "calibration.json"
    if p.is_file():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {
        "factor_pn_per_upside_force": DEFAULT_FACTOR_PN_PER_UPSIDE,
        "reference":                  "default (uncalibrated)",
        "note":                       "Run analysis/force_calibration.py to refine.",
    }


def _measure_existing_trajectory(traj_file: str, reference: str) -> dict:
    """Re-derive the calibration factor from an already-run pulling trajectory.

    Imports the analysis module lazily to avoid dragging mdtraj into a fast
    "load_calibration" call path (e.g. Force_Sweep.py).
    """
    if str(ANALYSIS_DIR) not in sys.path:
        sys.path.insert(0, str(ANALYSIS_DIR))
    import dynalab_analysis as da  # noqa: E402

    traj = da.load_upside_traj(traj_file)
    plot_path = ANALYSIS_DIR / "calibration_force_extension.png"
    fe = da.analyze_force_extension(traj, str(plot_path), traj_file=traj_file)
    flat = fe.get("stats") or {}

    forces, exts = [], []
    for label, value in flat.items():
        if "max_force_pN" in label:
            forces.append(value)
        if "final_extension_A" in label:
            exts.append(value)

    if not forces:
        raise RuntimeError(
            "Could not parse force trace from analyze_force_extension output."
        )

    measured = max(forces)
    expected = REFERENCE_PROTEINS[reference]["unfolding_pn"]
    ratio = expected / measured  # how much pN we under/overcounted per upside-force
    return {
        "measured_pn":     float(measured),
        "expected_pn":     float(expected),
        "ratio":           float(ratio),
        "plot_path":       str(plot_path),
    }


def calibrate_against_reference(
    reference: str = "fn3-d10",
    traj_file: str | None = None,
    factor_override: float | None = None,
) -> dict:
    """Refresh ``analysis/calibration.json``.

    Calling modes:
      * ``factor_override`` set: just overwrite the factor and exit.
      * ``traj_file`` set: re-derive from an already-run pulling trajectory.
      * neither set: keep the default factor but record the reference name and
        rationale, so the UI shows that no real calibration ran.
    """
    if reference not in REFERENCE_PROTEINS:
        raise ValueError(
            f"Unknown reference '{reference}'. "
            f"Known: {sorted(REFERENCE_PROTEINS.keys())}"
        )

    ref_info = REFERENCE_PROTEINS[reference]

    if factor_override is not None:
        path = write_calibration(
            factor_override,
            reference=reference,
            description=ref_info["description"],
            mode="override",
        )
        return {"factor": factor_override, "path": str(path), "mode": "override"}

    if traj_file is not None:
        meas = _measure_existing_trajectory(traj_file, reference)
        new_factor = DEFAULT_FACTOR_PN_PER_UPSIDE * meas["ratio"]
        path = write_calibration(
            new_factor,
            reference=reference,
            description=ref_info["description"],
            mode="from-trajectory",
            traj_file=traj_file,
            measurement=meas,
        )
        return {"factor": new_factor, "path": str(path), "mode": "from-trajectory",
                "measurement": meas}

    # No simulation available - keep default factor but record context.
    path = write_calibration(
        DEFAULT_FACTOR_PN_PER_UPSIDE,
        reference=reference,
        description=ref_info["description"],
        mode="default-noted",
        note=("No reference trajectory provided; using historical default. "
              "Run a pulling sim on the reference and re-call calibrate_against_reference "
              "with traj_file= to refine."),
    )
    return {"factor": DEFAULT_FACTOR_PN_PER_UPSIDE, "path": str(path), "mode": "default-noted"}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main(argv: list) -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--reference", default="fn3-d10",
                   choices=sorted(REFERENCE_PROTEINS.keys()))
    p.add_argument("--traj-file", default=None,
                   help="Already-run pulling trajectory (.run.up) to measure rupture force from.")
    p.add_argument("--factor", type=float, default=None,
                   help="Override the factor directly without simulating.")
    args = p.parse_args(argv)
    result = calibrate_against_reference(
        reference=args.reference, traj_file=args.traj_file, factor_override=args.factor,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))

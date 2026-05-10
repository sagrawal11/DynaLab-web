"""Lightweight tests for analysis/dynalab_analysis.py.

Most analyses need an mdtraj Trajectory so we build a tiny synthetic one
in-memory rather than depending on a real Upside trajectory.
"""

import csv
from pathlib import Path

import numpy as np
import pytest

# Skip the entire module if mdtraj isn't installed (e.g. during a quick
# CI pass that only exercises the pure-Python modules).
md = pytest.importorskip("mdtraj")

import dynalab_analysis as da  # type: ignore[import-not-found]


def _build_synthetic_traj(n_residues: int = 12, n_frames: int = 50) -> "md.Trajectory":
    """Build an mdtraj.Trajectory with N, CA, C atoms per residue along a line.

    Identical topology to what ``load_upside_traj`` produces (modulo NH/CB/O
    additions), which is enough for compute_rg / md.rmsd / md.compute_phi etc.
    Side chains aren't required for any of the geometry analyses we test here.
    """
    topo = md.Topology()
    chain = topo.add_chain()
    atoms = []
    for i in range(n_residues):
        res = topo.add_residue("ALA", chain, resSeq=i + 1)
        atoms.append(topo.add_atom("N",  md.element.nitrogen, res))
        atoms.append(topo.add_atom("CA", md.element.carbon,   res))
        atoms.append(topo.add_atom("C",  md.element.carbon,   res))
    n_atoms = n_residues * 3
    xyz = np.zeros((n_frames, n_atoms, 3), dtype=np.float32)
    rng = np.random.default_rng(0)
    for f in range(n_frames):
        for r in range(n_residues):
            base = np.array([0.38 * r, 0.0, 0.0])  # 3.8 A spacing in nm
            wiggle = rng.normal(0, 0.01, 3)
            xyz[f, 3 * r + 0] = base + np.array([-0.12, 0, 0]) + wiggle
            xyz[f, 3 * r + 1] = base + wiggle
            xyz[f, 3 * r + 2] = base + np.array([0.12, 0, 0]) + wiggle
    time = np.arange(n_frames, dtype=np.float32)
    return md.Trajectory(xyz=xyz, topology=topo, time=time)


def test_analyses_dispatcher_lists_expected_keys():
    expected = {"rg", "rmsd", "rmsf", "e2e", "contacts", "hbonds",
                "salt_bridges", "shape", "cross_corr", "ss", "pca",
                "force_ext", "burial_scan", "dihedral", "intermediates"}
    assert expected.issubset(set(da.ANALYSES.keys()))


def test_sweep_analyses_dispatcher_lists_expected_keys():
    expected = {"epitope_candidates", "burial_sweep", "intermediates"}
    assert expected == set(da.SWEEP_ANALYSES.keys())


def test_analyze_rg_smoke(tmp_path):
    traj = _build_synthetic_traj()
    out = da.analyze_rg(traj, str(tmp_path / "rg.png"))
    assert out["name"] == "Radius of Gyration"
    assert (tmp_path / "rg.png").is_file()
    assert out["stats"]["mean_A"] > 0


def test_analyze_rmsd_smoke(tmp_path):
    traj = _build_synthetic_traj()
    out = da.analyze_rmsd(traj, str(tmp_path / "rmsd.png"))
    assert out["stats"]["mean_A"] >= 0


def test_analyze_e2e_smoke(tmp_path):
    traj = _build_synthetic_traj()
    out = da.analyze_e2e(traj, str(tmp_path / "e2e.png"))
    # 12 residues, 3.8 A spacing -> ~42 A
    assert out["stats"]["mean_A"] > 30
    assert out["stats"]["mean_A"] < 60


def test_analyze_force_binding_comparison(tmp_path):
    csv_file = tmp_path / "wetlab.csv"
    rows = [
        ("force_pN", "fluorescence", "replicate", "condition"),
        (10, 5, 1, "primary"),
        (15, 8, 1, "primary"),
        (20, 25, 1, "primary"),
        (25, 80, 1, "primary"),
        (30, 92, 1, "primary"),
        (10, 4, 1, "scrambled-cdr"),
        (30, 6, 1, "scrambled-cdr"),
        (0,  3, 1, "no-spin"),
    ]
    with csv_file.open("w", newline="") as f:
        w = csv.writer(f); w.writerows(rows)
    out = da.analyze_force_binding_comparison(
        str(csv_file), str(tmp_path / "comp.png"), predicted_threshold_pn=22.0,
    )
    assert (tmp_path / "comp.png").is_file()
    # Should infer threshold around 25 pN (where primary crosses half-max)
    assert out["stats"]["experimental_threshold_pn"] is not None
    assert 15 <= out["stats"]["experimental_threshold_pn"] <= 30
    assert out["stats"]["predicted_threshold_pn"] == 22.0

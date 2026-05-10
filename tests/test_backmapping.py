"""Tests for analysis/backmapping.py.

Doesn't actually run PULCHRA -- monkey-patches it so we exercise the
control flow without needing the binary. The ``run_pulchra`` test that
*does* hit the binary is gated on PULCHRA being on PATH.
"""

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import backmapping  # type: ignore[import-not-found]


def test_find_pulchra_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("PULCHRA", raising=False)
    monkeypatch.setattr("shutil.which", lambda _: None)
    assert backmapping._find_pulchra() is None


def test_run_pulchra_raises_without_binary(monkeypatch, tmp_path):
    monkeypatch.delenv("PULCHRA", raising=False)
    monkeypatch.setattr("shutil.which", lambda _: None)
    src = tmp_path / "in.pdb"
    src.write_text("ATOM\n")
    with pytest.raises(RuntimeError, match="PULCHRA"):
        backmapping.run_pulchra(str(src), str(tmp_path / "out.pdb"))


def test_minimize_openmm_no_op_when_openmm_missing(monkeypatch, tmp_path):
    pdb_in = tmp_path / "in.pdb"
    pdb_in.write_text("ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00  0.00\n")
    pdb_out = tmp_path / "out.pdb"

    # Force the OpenMM import to fail
    real_import = __import__

    def _fake_import(name, *a, **kw):
        if name == "openmm":
            raise ImportError("nope")
        return real_import(name, *a, **kw)

    monkeypatch.setattr("builtins.__import__", _fake_import)
    out = backmapping.minimize_openmm(str(pdb_in), str(pdb_out))
    assert out["minimized"] is False
    assert pdb_out.read_text() == pdb_in.read_text()


def test_backmap_pdb_calls_pulchra_then_minimize(monkeypatch, tmp_path):
    pdb_in = tmp_path / "intermediate.pdb"
    pdb_in.write_text("ATOM\n")
    pdb_out = tmp_path / "intermediate_aa.pdb"

    def _fake_pulchra(src, dst, timeout=60):
        Path(dst).write_text("REMARK fake-pulchra-output\n")

    def _fake_minimize(src, dst, **_):
        shutil.copy(src, dst)
        return {"minimized": True}

    monkeypatch.setattr(backmapping, "run_pulchra", _fake_pulchra)
    monkeypatch.setattr(backmapping, "minimize_openmm", _fake_minimize)
    info = backmapping.backmap_pdb(str(pdb_in), str(pdb_out), minimize=True)
    assert pdb_out.is_file()
    assert info["minimization"]["minimized"] is True


def test_backmap_pdb_skip_minimize(monkeypatch, tmp_path):
    pdb_in = tmp_path / "in.pdb"
    pdb_in.write_text("ATOM\n")
    pdb_out = tmp_path / "out.pdb"

    def _fake_pulchra(src, dst, timeout=60):
        Path(dst).write_text("REMARK\n")

    monkeypatch.setattr(backmapping, "run_pulchra", _fake_pulchra)
    info = backmapping.backmap_pdb(str(pdb_in), str(pdb_out), minimize=False)
    assert info["minimization"]["minimized"] is False
    assert "skipped" in info["minimization"]["reason"]

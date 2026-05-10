"""Unit tests for analysis/force_calibration.py.

These tests don't run any actual Upside simulations - they exercise the
pure-Python helpers (rupture detection, file IO, default-noted writes).
"""

import json
from pathlib import Path

import numpy as np
import pytest

from force_calibration import (  # type: ignore[import-not-found]
    DEFAULT_FACTOR_PN_PER_UPSIDE,
    REFERENCE_PROTEINS,
    calibrate_against_reference,
    detect_rupture_force,
    load_calibration,
    write_calibration,
)


def test_detect_rupture_finds_clear_peak():
    """A synthetic sawtooth: the smoother should find the true peak."""
    n = 500
    extension = np.linspace(0.0, 200.0, n)
    force = np.zeros(n)
    force[:300] = np.linspace(0, 80, 300)
    force[300:330] = 140                  # the rupture peak
    force[330:] = np.linspace(40, 0, n - 330)
    force += np.random.default_rng(0).normal(0, 5, n)

    out = detect_rupture_force(extension, force, smoothing=15)
    assert 100 < out["peak_force_pN"] < 160, out


def test_detect_rupture_rejects_too_short_input():
    with pytest.raises(ValueError):
        detect_rupture_force(np.zeros(2), np.zeros(2))


def test_default_calibration_when_no_traj(tmp_path, monkeypatch):
    monkeypatch.setattr("force_calibration.ANALYSIS_DIR", tmp_path)
    out = calibrate_against_reference(reference="fn3-d10")
    assert out["factor"] == DEFAULT_FACTOR_PN_PER_UPSIDE
    cal = json.loads((tmp_path / "calibration.json").read_text())
    assert cal["mode"] == "default-noted"
    assert cal["reference"] == "fn3-d10"


def test_factor_override(tmp_path, monkeypatch):
    monkeypatch.setattr("force_calibration.ANALYSIS_DIR", tmp_path)
    out = calibrate_against_reference(reference="i27", factor_override=37.5)
    assert out["factor"] == 37.5
    cal = json.loads((tmp_path / "calibration.json").read_text())
    assert cal["factor_pn_per_upside_force"] == 37.5
    assert cal["mode"] == "override"


def test_unknown_reference_rejected():
    with pytest.raises(ValueError):
        calibrate_against_reference(reference="not-a-real-protein")


def test_load_calibration_default_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("force_calibration.ANALYSIS_DIR", tmp_path)
    cal = load_calibration()
    assert cal["factor_pn_per_upside_force"] == DEFAULT_FACTOR_PN_PER_UPSIDE
    assert "default" in cal["reference"].lower()


def test_write_calibration_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("force_calibration.ANALYSIS_DIR", tmp_path)
    p = write_calibration(42.0, reference="fn3-d10", mode="test")
    assert Path(p).is_file()
    cal = load_calibration()
    assert cal["factor_pn_per_upside_force"] == 42.0
    assert cal["mode"] == "test"


def test_known_references_have_unfolding_force():
    for name, info in REFERENCE_PROTEINS.items():
        assert info["unfolding_pn"] > 0, name
        assert info["description"]

"""Unit tests for analysis/centrifuge_design.py."""

import math
from pathlib import Path

import pytest

from centrifuge_design import (  # type: ignore[import-not-found]
    DEFAULT_BEAD_MASS_KG, DEFAULT_RPM,
    compute_zone_forces, design_centrifuge_experiment, pick_zone_radii,
)


def test_force_at_radius_matches_formula():
    """F = m * omega^2 * r should match the helper output exactly."""
    r = 0.05  # 50 mm
    rpm = 14000
    omega = 2 * math.pi * rpm / 60
    expected = DEFAULT_BEAD_MASS_KG * omega ** 2 * r * 1e12
    [actual] = compute_zone_forces([r], rpm=rpm)
    assert actual == pytest.approx(expected, rel=1e-6)


def test_pick_zone_radii_spans_target_range():
    radii = pick_zone_radii(n_zones=10, target_force_range=(14, 38))
    forces = compute_zone_forces(radii)
    assert forces[0] == pytest.approx(14.0, rel=0.02)
    assert forces[-1] == pytest.approx(38.0, rel=0.02)
    # Linear in force, so the spacing should be constant.
    diffs = [forces[i + 1] - forces[i] for i in range(len(forces) - 1)]
    assert max(diffs) - min(diffs) < 0.1


def test_pick_zone_radii_rejects_bad_range():
    with pytest.raises(ValueError):
        pick_zone_radii(n_zones=5, target_force_range=(0.0, 10.0))
    with pytest.raises(ValueError):
        pick_zone_radii(n_zones=5, target_force_range=(20.0, 10.0))


def test_design_centrifuge_experiment_smoke(tmp_path):
    pdb = tmp_path / "fake.pdb"
    pdb.write_text(
        "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00  0.00           C\n"
        "ATOM      2  CA  GLY A   2       3.800   0.000   0.000  1.00  0.00           C\n"
    )
    plan = design_centrifuge_experiment(
        target_pdb=str(pdb),
        predicted_thresholds_pn=[18.5, 26.4],
        n_zones=10,
        target_force_range=(14, 38),
    )
    assert plan["n_zones"] == 10
    assert len(plan["radii_m"]) == 10
    assert len(plan["forces_pn"]) == 10
    md = plan["markdown"]
    assert "Centrifuge Force-Sweep" in md
    assert "14.0 - 38.0 pN" in md or "14.0" in md
    assert "His-tag / Ni-NTA" in md
    assert "Controls" in md


@pytest.mark.parametrize("attachment,expected_substr", [
    ("his-tag",             "His-tag"),
    ("biotin-streptavidin", "Biotin"),
    ("click",               "SpyTag"),
    ("custom-foo",          "Custom"),
])
def test_attachment_chemistries_render(tmp_path, attachment, expected_substr):
    pdb = tmp_path / "x.pdb"
    pdb.write_text("ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00  0.00\n")
    plan = design_centrifuge_experiment(
        target_pdb=str(pdb),
        predicted_thresholds_pn=[],
        n_zones=3,
        target_force_range=(14, 38),
        attachment=attachment,
    )
    assert expected_substr in plan["markdown"]

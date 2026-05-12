"""Tests for ``web/server/app.py`` single-job config validation."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "web" / "server"))

import app as flask_app  # noqa: E402


MIN_PDB = """\
ATOM      1  N   GLY A   1      11.104  13.207   2.100  1.00  0.00           N
ATOM      2  CA  GLY A   1      12.560  13.207   2.100  1.00  0.00           C
ATOM      3  N   GLY A   2      13.000  14.500   2.100  1.00  0.00           N
ATOM      4  CA  GLY A   2      14.200  14.500   2.100  1.00  0.00           C
ATOM      5  N   GLY A   3      14.600  15.800   2.100  1.00  0.00           N
ATOM      6  CA  GLY A   3      15.900  15.800   2.100  1.00  0.00           C
TER
END
"""


@pytest.fixture
def job_dir(tmp_path):
    d = tmp_path / "job"
    d.mkdir()
    (d / "input.pdb").write_text(MIN_PDB)
    return d


def test_rejects_locks_plus_manual_pair_spring(job_dir):
    cfg = {
        "distanceLockPairs": [{"res1": 0, "res2": 1}],
        "enablePairSpringText": True,
        "pairSpringText": "0 2 5.0 4.0\n",
    }
    with pytest.raises(ValueError, match="Cannot combine"):
        flask_app._validate_single_job_config(job_dir, cfg)


def test_rejects_duplicate_distance_lock_pair(job_dir):
    cfg = {
        "distanceLockPairs": [
            {"res1": 0, "res2": 2},
            {"res1": 2, "res2": 0},
        ],
    }
    with pytest.raises(ValueError, match="Duplicate distance-lock"):
        flask_app._validate_single_job_config(job_dir, cfg)


def test_rejects_distance_lock_out_of_range(job_dir):
    cfg = {"distanceLockPairs": [{"res1": 0, "res2": 9}]}
    with pytest.raises(ValueError, match="out of range"):
        flask_app._validate_single_job_config(job_dir, cfg)


def test_accepts_valid_locks(job_dir):
    cfg = {"distanceLockPairs": [{"res1": 0, "res2": 2}]}
    flask_app._validate_single_job_config(job_dir, cfg)


def test_rejects_duplicate_manual_pair_lines(job_dir):
    cfg = {
        "enablePairSpringText": True,
        "pairSpringText": "0 1 5.0 4\n1 0 5.0 4\n",
    }
    with pytest.raises(ValueError, match="Duplicate manual"):
        flask_app._validate_single_job_config(job_dir, cfg)


def test_rejects_duplicate_afm_residues(job_dir):
    cfg = {
        "enablePulling": True,
        "pullingMode": "velocity",
        "afmEntries": [
            {"residue": 0, "spring": 0.05, "velX": 0, "velY": 0, "velZ": -0.001},
            {"residue": 0, "spring": 0.05, "velX": 0, "velY": 0, "velZ": -0.001},
        ],
    }
    with pytest.raises(ValueError, match="at most once"):
        flask_app._validate_single_job_config(job_dir, cfg)


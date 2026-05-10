"""Tests for the AI design pipeline.

We use the deterministic mock client (``design/tamarind_mock.py``) so the
tests run offline and don't require a Tamarind API key.
"""

import json
from pathlib import Path

import pytest

import pipeline  # type: ignore[import-not-found]
from tamarind_mock import MockTamarindClient  # type: ignore[import-not-found]


@pytest.fixture
def fake_job_dir(tmp_path):
    """Build a minimal job_dir with a fake back-mapped PDB."""
    job = tmp_path / "job"
    bm = job / "backmapped"
    bm.mkdir(parents=True)
    pdb = bm / "intermediate_03_aa.pdb"
    pdb.write_text(
        "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00  0.00\n"
        "ATOM      2  CA  GLY A   2       3.800   0.000   0.000  1.00  0.00\n"
    )
    (job / "design").mkdir()
    return job


def test_mock_client_rfdiffusion_deterministic():
    c = MockTamarindClient()
    a = c.run_rfdiffusion("ATOM ...", hotspots=[1, 2, 3], n_designs=4, binder_length=80)
    b = c.run_rfdiffusion("ATOM ...", hotspots=[1, 2, 3], n_designs=4, binder_length=80)
    assert a == b


def test_mock_client_protein_mpnn_returns_sequences():
    c = MockTamarindClient()
    out = c.run_protein_mpnn(["mock://x.pdb", "mock://y.pdb"], n_seqs=2)
    seqs = out["sequences"]
    assert len(seqs) == 4   # 2 backbones x 2 seqs
    assert all("sequence" in s for s in seqs)


def test_mock_client_af_multimer_sorts_iptm_descending():
    c = MockTamarindClient()
    out = c.run_af_multimer("MTGAA", ["AAAA", "BBBB", "CCCC", "DDDD"])
    iptms = [r["iptm"] for r in out["scores"]]
    assert iptms == sorted(iptms, reverse=True)


def test_pipeline_end_to_end_with_mock(fake_job_dir):
    design_dir = fake_job_dir / "design" / "test_run"
    out = pipeline.run_design_pipeline(
        job_dir=fake_job_dir,
        design_dir=design_dir,
        request_body={
            "intermediate_state": "intermediate_03",
            "hotspots": [1, 2],
            "n_designs": 3,
            "binder_length": 60,
            "n_seqs_per_design": 2,
            "use_mock": True,
        },
    )
    assert out["client_kind"] == "mock"
    assert out["n_designs"] == 3
    assert out["n_sequences"] == 6
    assert out["n_scored"] > 0
    # Candidates were saved to disk
    assert (design_dir / "candidates" / "rank_001.pdb").is_file()
    assert (design_dir / "scores.json").is_file()


def test_pipeline_falls_back_to_mock_without_api_key(fake_job_dir, monkeypatch):
    monkeypatch.delenv("TAMARIND_API_KEY", raising=False)
    out = pipeline.run_design_pipeline(
        job_dir=fake_job_dir,
        design_dir=fake_job_dir / "design" / "auto",
        request_body={
            "intermediate_state": "intermediate_03",
            "hotspots": [],
            "n_designs": 2,
            "n_seqs_per_design": 1,
        },
    )
    assert out["client_kind"] in ("mock-fallback", "mock")
    if out["client_kind"] == "mock-fallback":
        assert out["fallback_reason"]


def test_pipeline_resolves_intermediate_with_short_form(fake_job_dir):
    out = pipeline.run_design_pipeline(
        job_dir=fake_job_dir,
        design_dir=fake_job_dir / "design" / "short",
        request_body={
            "intermediate_state": "3",            # short form
            "hotspots": [],
            "n_designs": 2,
            "n_seqs_per_design": 1,
            "use_mock": True,
        },
    )
    assert out["intermediate_pdb"].endswith("intermediate_03_aa.pdb")


def test_pipeline_rejects_missing_intermediate(fake_job_dir):
    with pytest.raises(FileNotFoundError):
        pipeline.run_design_pipeline(
            job_dir=fake_job_dir,
            design_dir=fake_job_dir / "design" / "missing",
            request_body={
                "intermediate_state": "999",
                "hotspots": [],
                "n_designs": 2,
                "use_mock": True,
            },
        )

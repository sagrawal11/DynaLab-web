"""Standalone Upside2 trajectory analysis module.

Extracted from analysis/Dynalab_Analysis_Final (2).ipynb so the Flask
backend (web/server/app.py) can call analyses as a post-processing step
without spinning up Jupyter or Colab.

Each ``analyze_*`` function takes a pre-loaded mdtraj.Trajectory plus an
output PNG path, writes the figure, and returns a metadata dict shaped
like ``{"name": ..., "image": <path>, "stats": {...}}``.

The CLI form is:

    python dynalab_analysis.py <traj.run.up> <output_dir> rg rmsd rmsf e2e contacts

It writes one PNG per requested analysis plus ``results.json``.
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

import mdtraj as md
import mdtraj.core.element as el
import tables as tb


# Distances inside the .run.up file are in angstroms; mdtraj expects nm.
ANGSTROM_TO_NM = 0.1

AA_THREE = {
    "A": "ALA", "R": "ARG", "N": "ASN", "D": "ASP", "C": "CYS", "E": "GLU",
    "Q": "GLN", "G": "GLY", "H": "HIS", "I": "ILE", "L": "LEU", "K": "LYS",
    "M": "MET", "F": "PHE", "P": "PRO", "S": "SER", "T": "THR", "W": "TRP",
    "Y": "TYR", "V": "VAL",
}


# ---------------------------------------------------------------------------
# Trajectory loading (faithful port of load_upside_traj from the notebook)
# ---------------------------------------------------------------------------

def _vmag(x):
    return np.sqrt(x[..., 0] ** 2 + x[..., 1] ** 2 + x[..., 2] ** 2)


def _vhat(x):
    return x / _vmag(x)[..., None]


def _output_groups(t):
    i = 0
    while f"output_previous_{i}" in t.root:
        yield t.get_node(f"/output_previous_{i}")
        i += 1
    if "output" in t.root:
        yield t.get_node("/output")


def _traj_from_upside(seq, time, pos, chain_first_residue, chain_counts):
    """Reconstruct an mdtraj.Trajectory from Upside coarse-grained N/CA/C
    positions, filling in NH/CB/O so contact and DSSP analyses make sense."""
    H_bond_length = 0.88
    O_bond_length = 1.24

    n_frame = len(pos)
    n_res = len(seq)

    try:
        seq = [str(seq[nr], "utf-8") for nr in range(n_res)]
    except TypeError:
        pass

    seq = np.array([("PRO" if x == "CPR" else x) for x in seq])

    ch_first = chain_first_residue[:]
    chain_first_residue = set(chain_first_residue).union({0, n_res})
    assert all(x <= n_res for x in chain_first_residue)
    assert 0 in chain_first_residue
    assert pos.shape == (n_frame, 3 * n_res, 3)
    assert seq.shape == (n_res,)

    topo = md.Topology()
    expanded_pos_columns = []
    last_C = None
    atom_num = 0

    for ch_real, _ in enumerate(chain_counts):
        current_chain = topo.add_chain()
        culm_idx = sum(chain_counts[: ch_real + 1])
        culm_idx_prev = sum(chain_counts[:ch_real])
        res_min = ch_first[culm_idx_prev]
        res_upper = ch_first[culm_idx] if culm_idx < len(ch_first) else n_res

        for nr in range(res_min, res_upper):
            seq_r = str(seq[nr])
            res = topo.add_residue(seq_r, current_chain, resSeq=nr)

            N = topo.add_atom("N", el.nitrogen, res, atom_num); atom_num += 1
            CA = topo.add_atom("CA", el.carbon, res, atom_num); atom_num += 1
            C = topo.add_atom("C", el.carbon, res, atom_num); atom_num += 1

            expanded_pos_columns.append(pos[:, 3 * nr : 3 * (nr + 1)])
            N_pos = expanded_pos_columns[-1][:, 0]
            CA_pos = expanded_pos_columns[-1][:, 1]
            C_pos = expanded_pos_columns[-1][:, 2]

            if nr not in chain_first_residue:
                topo.add_bond(last_C, N)
            topo.add_bond(N, CA)
            topo.add_bond(CA, C)

            if nr not in chain_first_residue and seq[nr] != "PRO":
                H = topo.add_atom("NH", el.hydrogen, res, atom_num); atom_num += 1
                topo.add_bond(N, H)
                last_C_pos = pos[:, 3 * nr - 1]
                H_pos = N_pos - H_bond_length * _vhat(
                    _vhat(last_C_pos - N_pos) + _vhat(CA_pos - N_pos)
                )
                expanded_pos_columns.append(H_pos[:, None].astype("f4"))

            if seq[nr] != "GLY":
                CB = topo.add_atom("CB", el.carbon, res, atom_num); atom_num += 1
                topo.add_bond(CA, CB)
                extend_dir = _vhat(_vhat(CA_pos - N_pos) + _vhat(CA_pos - C_pos))
                cross_dir = np.cross(N_pos - CA_pos, C_pos - CA_pos)
                CB_pos = CA_pos + 0.94375626 * extend_dir + 0.5796686718421049 * cross_dir
                expanded_pos_columns.append(CB_pos[:, None].astype("f4"))

            O = topo.add_atom("O", el.oxygen, res, atom_num); atom_num += 1
            topo.add_bond(C, O)
            if nr + 1 not in chain_first_residue:
                next_N_pos = pos[:, 3 * nr + 3]
                O_pos = C_pos - O_bond_length * _vhat(
                    _vhat(CA_pos - C_pos) + _vhat(next_N_pos - C_pos)
                )
            else:
                O_pos = C_pos - O_bond_length * _vhat(
                    _vhat(CA_pos - C_pos) + _vhat(CA_pos - N_pos)
                )
            expanded_pos_columns.append(O_pos[:, None].astype("f4"))

            last_C = C

    xyz = np.concatenate(expanded_pos_columns, axis=1)
    topo = topo.copy()
    return md.Trajectory(xyz=xyz * ANGSTROM_TO_NM, topology=topo, time=time)


def load_upside_traj(fname: str, stride: int = 1) -> md.Trajectory:
    """Load an Upside2 ``.run.up`` HDF5 trajectory file as an mdtraj
    Trajectory. Concatenates all ``output*`` groups so restarts are
    handled transparently."""
    last_time = 0.0
    start_frame = 0
    total_frames_produced = 0
    xyz: list = []
    time: list = []
    chain_first_residue = np.array([0], dtype="int32")
    chain_counts = np.array([1], dtype="int32")

    with tb.open_file(fname) as t:
        for g_no, g in enumerate(_output_groups(t)):
            sl = slice(start_frame, None, stride)
            xyz.append(g.pos[sl, 0])
            time.append(g.time[sl] + last_time)
            last_time = g.time[-1] + last_time
            total_frames_produced += g.pos.shape[0] - (1 if g_no else 0)
            start_frame = (
                1 + stride * (total_frames_produced % stride > 0)
                - total_frames_produced % stride
            )

    with tb.open_file(fname) as ref:
        seq = ref.root.input.sequence[:]
        if "chain_break" in ref.root.input:
            chain_first_residue = np.append(
                chain_first_residue, ref.root.input.chain_break.chain_first_residue[:]
            )
            if "chain_counts" in ref.root.input.chain_break:
                chain_counts = ref.root.input.chain_break.chain_counts[:]
            else:
                chain_counts = np.array([1 for _ in chain_first_residue])

    if not xyz:
        raise RuntimeError(f"No output frames found in {fname}")

    xyz = np.concatenate(xyz, axis=0)
    time = np.concatenate(time, axis=0)
    return _traj_from_upside(seq, time, xyz, chain_first_residue, chain_counts)


# ---------------------------------------------------------------------------
# Per-analysis functions
# ---------------------------------------------------------------------------

def analyze_rg(traj: md.Trajectory, output_path: str, **_kwargs) -> dict:
    """Radius of gyration (compactness) over time."""
    rg = md.compute_rg(traj) * 10.0  # nm -> Å

    plt.figure(figsize=(10, 6))
    plt.plot(rg, "b-", linewidth=1.5)
    plt.xlabel("Frame")
    plt.ylabel("Radius of Gyration (Å)")
    plt.title("Radius of Gyration vs Frame")
    plt.grid(True, alpha=0.3)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    return {
        "name": "Radius of Gyration",
        "description": "Compactness of the protein over time. Increases when the protein expands or unfolds.",
        "image": output_path,
        "stats": {
            "mean_A": float(np.mean(rg)),
            "std_A": float(np.std(rg)),
            "min_A": float(np.min(rg)),
            "max_A": float(np.max(rg)),
        },
    }


def analyze_rmsd(traj: md.Trajectory, output_path: str, **_kwargs) -> dict:
    """RMSD relative to the starting structure (frame 0)."""
    rmsd = md.rmsd(traj, traj, 0) * 10.0

    plt.figure(figsize=(10, 6))
    plt.plot(rmsd, "r-", linewidth=1.5)
    plt.xlabel("Frame")
    plt.ylabel("RMSD (Å)")
    plt.title("RMSD vs Frame (relative to initial structure)")
    plt.grid(True, alpha=0.3)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    return {
        "name": "RMSD",
        "description": "Average atomic deviation from the starting structure. Plateaus when equilibrated; rises during unfolding.",
        "image": output_path,
        "stats": {
            "mean_A": float(np.mean(rmsd)),
            "std_A": float(np.std(rmsd)),
            "final_A": float(rmsd[-1]),
            "max_A": float(np.max(rmsd)),
        },
    }


def analyze_rmsf(traj: md.Trajectory, output_path: str, **_kwargs) -> dict:
    """Root mean-square fluctuation per residue (CA atoms)."""
    avg_struct = traj.slice(0)
    avg_struct.xyz[0] = np.mean(traj.xyz, axis=0)

    ca_indices = traj.topology.select("name CA")
    if len(ca_indices) == 0:
        raise ValueError("No CA atoms found in trajectory")

    rmsf = md.rmsf(traj, avg_struct, atom_indices=ca_indices) * 10.0
    residue_numbers = [traj.topology.atom(int(i)).residue.resSeq for i in ca_indices]

    plt.figure(figsize=(12, 6))
    plt.plot(residue_numbers, rmsf, "b-", linewidth=2, marker="o", markersize=4)
    plt.xlabel("Residue Number")
    plt.ylabel("RMSF (Å)")
    plt.title("Per-Residue Flexibility (RMSF)")
    plt.grid(True, alpha=0.3)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    most_flexible = int(np.argmax(rmsf))
    return {
        "name": "Per-Residue RMSF",
        "description": "Per-residue mobility around the average structure. High peaks mark flexible loops or regions exposed by tension.",
        "image": output_path,
        "stats": {
            "mean_A": float(np.mean(rmsf)),
            "most_flexible_residue": int(residue_numbers[most_flexible]),
            "most_flexible_rmsf_A": float(rmsf[most_flexible]),
        },
    }


def analyze_e2e(traj: md.Trajectory, output_path: str, **_kwargs) -> dict:
    """End-to-end distance between the first and last CA atoms."""
    ca_indices = traj.topology.select("name CA")
    if len(ca_indices) < 2:
        raise ValueError("Need at least 2 CA atoms to compute end-to-end distance")

    pair = [[int(ca_indices[0]), int(ca_indices[-1])]]
    e2e = md.compute_distances(traj, pair)[:, 0] * 10.0

    plt.figure(figsize=(12, 6))
    plt.plot(e2e, "g-", linewidth=1.5)
    plt.xlabel("Frame")
    plt.ylabel("End-to-End Distance (Å)")
    plt.title("End-to-End Distance vs Frame")
    plt.grid(True, alpha=0.3)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    return {
        "name": "End-to-End Distance",
        "description": "Distance between the first and last CA. Useful for pulling simulations - watch it grow as tension stretches the chain.",
        "image": output_path,
        "stats": {
            "initial_A": float(e2e[0]),
            "final_A": float(e2e[-1]),
            "mean_A": float(np.mean(e2e)),
            "max_A": float(np.max(e2e)),
        },
    }


def analyze_contacts(
    traj: md.Trajectory,
    output_path: str,
    cutoff_nm: float = 0.45,
    n_neighbors_ignored: int = 2,
    **_kwargs,
) -> dict:
    """Map of how often each pair of residues is in contact (CA-CA <= cutoff)."""
    ca_indices = traj.topology.select("name CA")
    if len(ca_indices) < 2:
        raise ValueError("Need at least 2 CA atoms for contact map")

    n_residues = len(ca_indices)
    pairs = [
        [int(ca_indices[i]), int(ca_indices[j])]
        for i in range(n_residues)
        for j in range(i + n_neighbors_ignored + 1, n_residues)
    ]
    pairs = np.array(pairs)
    distances = md.compute_distances(traj, pairs)
    freqs = np.mean((distances < cutoff_nm).astype(float), axis=0)

    matrix = np.zeros((n_residues, n_residues))
    for idx, (i, j) in enumerate(pairs):
        i_res = int(np.where(ca_indices == i)[0][0])
        j_res = int(np.where(ca_indices == j)[0][0])
        matrix[i_res, j_res] = freqs[idx]
        matrix[j_res, i_res] = freqs[idx]

    plt.figure(figsize=(10, 8))
    im = plt.imshow(matrix, cmap="hot", interpolation="nearest", origin="lower")
    plt.colorbar(im, label="Contact Frequency")
    plt.xlabel("Residue Index")
    plt.ylabel("Residue Index")
    plt.title(f"Contact Frequency Map (cutoff = {cutoff_nm * 10:.1f} Å)")
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    stable = int(np.sum(matrix > 0.8) // 2)
    return {
        "name": "Contact Map",
        "description": "Fraction of frames each residue pair is within 4.5 Å. Stable contacts (>80%) outline the folded core; contacts that disappear under tension reveal cryptic regions.",
        "image": output_path,
        "stats": {
            "n_residues": int(n_residues),
            "stable_contacts": stable,
            "avg_frequency": float(np.mean(matrix)),
        },
    }


def analyze_hbonds(traj: md.Trajectory, output_path: str, **_kwargs) -> dict:
    """Backbone hydrogen-bond count per frame.

    Uses mdtraj's Baker-Hubbard criterion frame-by-frame. Only backbone
    N-H...O=C bonds are detectable here because the Upside coarse-grained
    topology contains N, NH, and O atoms (no side chain donors/acceptors).
    """
    counts = np.array(
        [len(md.baker_hubbard(traj[i], periodic=False)) for i in range(traj.n_frames)],
        dtype=int,
    )

    plt.figure(figsize=(10, 6))
    plt.plot(counts, "g-", linewidth=1.5)
    plt.xlabel("Frame")
    plt.ylabel("Number of Backbone H-Bonds")
    plt.title("Backbone Hydrogen Bonds vs Frame")
    plt.grid(True, alpha=0.3)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    return {
        "name": "Hydrogen Bonds",
        "description": "Backbone hydrogen bonds per frame (Baker-Hubbard). Watch this drop when secondary structure breaks under tension.",
        "image": output_path,
        "stats": {
            "mean": float(np.mean(counts)),
            "std": float(np.std(counts)),
            "initial": int(counts[0]),
            "final": int(counts[-1]),
        },
    }


def analyze_salt_bridges(
    traj: md.Trajectory,
    output_path: str,
    cutoff_A: float = 8.0,
    **_kwargs,
) -> dict:
    """Approximate ionic contacts using CB-CB distances between charged residues.

    The Upside coarse-grained topology has no side-chain heavy atoms beyond
    CB, so true side chain salt bridges (NZ...OD1 etc.) cannot be measured
    directly. We approximate by counting pairs of oppositely charged
    residues whose CB atoms are within ``cutoff_A`` (default 8 Å), which is
    a standard CB-based ionic-contact proxy in coarse-grained MD.
    """
    POSITIVE = {"ARG", "LYS", "HIS"}
    NEGATIVE = {"ASP", "GLU"}

    pos_cb = []
    pos_label = []
    neg_cb = []
    neg_label = []
    for residue in traj.topology.residues:
        cb = next((a for a in residue.atoms if a.name == "CB"), None)
        if cb is None:
            continue
        if residue.name in POSITIVE:
            pos_cb.append(cb.index)
            pos_label.append(f"{residue.name}{residue.resSeq}")
        elif residue.name in NEGATIVE:
            neg_cb.append(cb.index)
            neg_label.append(f"{residue.name}{residue.resSeq}")

    if not pos_cb or not neg_cb:
        raise ValueError(
            "No oppositely-charged residue pairs with CB found "
            "(needed: ARG/LYS/HIS and ASP/GLU)"
        )

    pairs = np.array([[p, n] for p in pos_cb for n in neg_cb])
    distances_A = md.compute_distances(traj, pairs) * 10.0
    cutoff_nm_eq = cutoff_A
    in_contact = distances_A <= cutoff_nm_eq
    counts_per_frame = in_contact.sum(axis=1)

    formation_pct = in_contact.mean(axis=0) * 100
    pair_labels = [f"{pos_label[i]}-{neg_label[j]}"
                   for i in range(len(pos_cb)) for j in range(len(neg_cb))]
    top_idx = np.argsort(formation_pct)[::-1][:10]

    plt.figure(figsize=(10, 6))
    plt.plot(counts_per_frame, color="purple", linewidth=1.5)
    plt.xlabel("Frame")
    plt.ylabel(f"# Charged CB-CB contacts (≤ {cutoff_A:.1f} Å)")
    plt.title("Coarse-Grained Salt-Bridge Proxy")
    plt.grid(True, alpha=0.3)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    return {
        "name": "Salt Bridges (CG approx.)",
        "description": (
            "CB-CB ionic-contact proxy for charged residue pairs (cutoff "
            f"{cutoff_A:.1f} Å). Upside is coarse-grained, so this is an "
            "approximation - true atomistic salt bridges require backmapping."
        ),
        "image": output_path,
        "stats": {
            "n_charged_pairs": int(len(pairs)),
            "mean_contacts": float(np.mean(counts_per_frame)),
            "initial_contacts": int(counts_per_frame[0]),
            "final_contacts": int(counts_per_frame[-1]),
            "top_persistent_pair": pair_labels[int(top_idx[0])] if len(top_idx) else None,
            "top_persistent_pct": float(formation_pct[int(top_idx[0])]) if len(top_idx) else None,
        },
    }


def analyze_shape(traj: md.Trajectory, output_path: str, **_kwargs) -> dict:
    """Gyration-tensor shape descriptors over time.

    Diagonalising the gyration tensor gives three principal moments
    ``L1 >= L2 >= L3``. From these we derive:
      - asphericity   b  = L1 - 0.5 (L2 + L3)
      - acylindricity c  = L2 - L3
      - anisotropy    k2 = (b^2 + 0.75 c^2) / Rg^4

    Spherical objects -> b, c, k2 -> 0.  Stretched/elongated states have
    higher anisotropy, so this is a sensitive shape metric for pulling.
    """
    ca_indices = traj.topology.select("name CA")
    if len(ca_indices) < 3:
        raise ValueError("Need at least 3 CA atoms for shape analysis")

    coords_A = traj.xyz[:, ca_indices, :] * 10.0  # nm -> Å
    centered = coords_A - coords_A.mean(axis=1, keepdims=True)
    n_frames, n_res, _ = centered.shape

    # Gyration tensor S_ab = (1/N) sum_i r_i,a r_i,b (per frame)
    S = np.einsum("fia,fib->fab", centered, centered) / n_res
    eigvals = np.linalg.eigvalsh(S)              # ascending order
    eigvals = np.sort(eigvals, axis=1)[:, ::-1]  # descending: L1 >= L2 >= L3

    L1, L2, L3 = eigvals[:, 0], eigvals[:, 1], eigvals[:, 2]
    rg2 = L1 + L2 + L3
    asph = L1 - 0.5 * (L2 + L3)
    acyl = L2 - L3
    aniso = (asph ** 2 + 0.75 * acyl ** 2) / np.maximum(rg2 ** 2, 1e-12)

    fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    axes[0].plot(asph, "C0-", linewidth=1.5, label="Asphericity (Å²)")
    axes[0].plot(acyl, "C1-", linewidth=1.5, label="Acylindricity (Å²)")
    axes[0].set_ylabel("Å²")
    axes[0].legend(); axes[0].grid(True, alpha=0.3)
    axes[1].plot(aniso, "C2-", linewidth=1.5)
    axes[1].set_ylabel("Anisotropy κ²")
    axes[1].set_xlabel("Frame")
    axes[1].grid(True, alpha=0.3)
    fig.suptitle("Gyration-Tensor Shape Descriptors")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    return {
        "name": "Shape (gyration tensor)",
        "description": "Decomposes the gyration tensor into asphericity, acylindricity, and anisotropy. Rises sharply when the protein elongates under tension.",
        "image": output_path,
        "stats": {
            "asphericity_initial_A2": float(asph[0]),
            "asphericity_final_A2":   float(asph[-1]),
            "anisotropy_initial":     float(aniso[0]),
            "anisotropy_final":       float(aniso[-1]),
            "anisotropy_max":         float(np.max(aniso)),
        },
    }


def analyze_cross_correlation(traj: md.Trajectory, output_path: str, **_kwargs) -> dict:
    """Dynamic cross-correlation matrix of CA displacement directions.

    Vectorised port of the notebook formula:
    ``C_ij = mean_t( (d_i . d_j) / (|d_i| |d_j|) )`` where ``d`` is each
    CA's displacement from its mean position. Values near +1 mean
    correlated motion, near -1 mean anti-correlated.
    """
    ca_indices = traj.topology.select("name CA")
    if len(ca_indices) < 2:
        raise ValueError("Need at least 2 CA atoms for cross-correlation")

    coords = traj.xyz[:, ca_indices, :]                       # (T, N, 3)
    disp = coords - coords.mean(axis=0, keepdims=True)        # (T, N, 3)
    mag = np.linalg.norm(disp, axis=2)                        # (T, N)
    safe = np.where(mag > 1e-10, mag, 1.0)
    norm_disp = disp / safe[..., None]                        # (T, N, 3)
    norm_disp[mag <= 1e-10] = 0.0
    # einsum: per-frame dot product of unit displacements, averaged over T
    corr = np.einsum("tid,tjd->ij", norm_disp, norm_disp) / traj.n_frames

    residue_numbers = [traj.topology.atom(int(i)).residue.resSeq for i in ca_indices]

    plt.figure(figsize=(10, 8))
    im = plt.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1, origin="lower")
    plt.colorbar(im, label="Cross-Correlation")
    plt.xlabel("Residue index")
    plt.ylabel("Residue index")
    plt.title("Dynamic Cross-Correlation Map")
    stride = max(1, len(residue_numbers) // 10)
    ticks = list(range(0, len(residue_numbers), stride))
    labels = [residue_numbers[t] for t in ticks]
    plt.xticks(ticks, labels)
    plt.yticks(ticks, labels)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    off_diag = corr[~np.eye(corr.shape[0], dtype=bool)]
    return {
        "name": "Cross-Correlation",
        "description": "Pairwise correlation of residue motions. Coupled regions move together (red); anti-correlated regions move oppositely (blue).",
        "image": output_path,
        "stats": {
            "n_residues": int(len(ca_indices)),
            "mean_off_diag": float(np.mean(off_diag)),
            "max_correlation":    float(np.max(off_diag)),
            "min_correlation":    float(np.min(off_diag)),
        },
    }


def _simplified_ss_from_hbonds(traj: md.Trajectory) -> np.ndarray:
    """Pure-Python helix/sheet/coil assignment from backbone H-bond energies.

    Uses mdtraj's ``kabsch_sander`` (which implements the DSSP electrostatic
    H-bond energy formula in pure Python — no external binary) and applies
    the simplified DSSP rules:

    * **H** (helix): residue ``i`` has an N-H...O=C bond to residue ``i+4``,
      and so does residue ``i-1`` (i.e. two consecutive turn-4 H-bonds, the
      DSSP definition of an alpha helix).
    * **E** (sheet): residue ``i`` has an H-bond to some residue ``j`` with
      ``|i - j| > 5`` (long-range, characteristic of beta sheets).
    * **C** (coil): everything else.

    This is less precise than the canonical ``mkdssp`` binary (no 3_10 helix,
    pi-helix, turn, or bend assignments) but doesn't require any system
    packages and runs on linux-aarch64 / macOS-arm64 just fine.
    """
    HBOND_ENERGY_CUTOFF = -0.5  # kcal/mol, DSSP threshold
    n_res = traj.topology.n_residues

    energy_matrices = md.kabsch_sander(traj)
    ss = np.full((traj.n_frames, n_res), "C", dtype="<U1")

    seq_dist = np.abs(np.arange(n_res)[:, None] - np.arange(n_res)[None, :])

    for f, e_csr in enumerate(energy_matrices):
        e = e_csr.toarray()
        hbond = e < HBOND_ENERGY_CUTOFF

        turn4 = np.zeros(n_res, dtype=bool)
        if n_res >= 5:
            turn4[: n_res - 4] = hbond[np.arange(n_res - 4), np.arange(4, n_res)]

        helix_residue = np.zeros(n_res, dtype=bool)
        if n_res >= 6:
            for i in range(1, n_res - 4):
                if turn4[i] and turn4[i - 1]:
                    helix_residue[i : i + 4] = True
        ss[f, helix_residue] = "H"

        distant_hbond = hbond & (seq_dist > 5)
        sheet_residue = np.any(distant_hbond, axis=1) & ~helix_residue
        ss[f, sheet_residue] = "E"

    return ss


def analyze_secondary_structure(traj: md.Trajectory, output_path: str, **_kwargs) -> dict:
    """Per-residue helix/sheet/coil percentages.

    Tries the canonical DSSP via ``md.compute_dssp`` first (requires the
    ``mkdssp`` binary). If that fails — typically because mkdssp isn't
    installed, which is common on linux-aarch64 — falls back to a pure-Python
    H/E/C assignment computed from backbone H-bond energies via
    ``md.kabsch_sander``. The fallback approximates DSSP and is flagged in
    the description.
    """
    used_fallback = False
    try:
        ss = md.compute_dssp(traj, simplified=True)
    except Exception as exc:
        msg = str(exc).lower()
        if "dssp" in msg or "mkdssp" in msg or "no such file" in msg:
            ss = _simplified_ss_from_hbonds(traj)
            used_fallback = True
        else:
            raise

    n_frames, n_res = ss.shape
    helix = (ss == "H").sum(axis=0) / n_frames * 100.0
    sheet = (ss == "E").sum(axis=0) / n_frames * 100.0
    coil = 100.0 - helix - sheet

    residues = list(traj.topology.residues)
    residue_numbers = [r.resSeq for r in residues][:n_res]
    x = np.arange(n_res)

    fig, axes = plt.subplots(2, 1, figsize=(14, 9), gridspec_kw={"height_ratios": [2, 1]})

    axes[0].bar(x, helix,         label="Helix", color="#e53e3e", alpha=0.8)
    axes[0].bar(x, sheet, bottom=helix,         label="Sheet", color="#3182ce", alpha=0.8)
    axes[0].bar(x, coil,  bottom=helix + sheet, label="Coil",  color="#48bb78", alpha=0.8)
    axes[0].set_ylabel("Percentage (%)")
    axes[0].set_title("Secondary Structure Content per Residue")
    axes[0].legend(loc="upper right")
    axes[0].set_ylim(0, 100)
    stride = max(1, n_res // 20)
    axes[0].set_xticks(x[::stride])
    axes[0].set_xticklabels([residue_numbers[i] for i in x[::stride]])

    ss_numeric = np.zeros_like(ss, dtype=int)
    ss_numeric[ss == "H"] = 2
    ss_numeric[ss == "E"] = 1
    axes[1].imshow(ss_numeric.T, cmap="RdYlGn_r", aspect="auto", interpolation="nearest")
    axes[1].set_xlabel("Frame")
    axes[1].set_ylabel("Residue")
    axes[1].set_title("Secondary Structure Timeline (red=helix, yellow=sheet, green=coil)")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    name = "Secondary Structure (H-bond approx.)" if used_fallback else "Secondary Structure (DSSP)"
    if used_fallback:
        description = (
            "H-bond-based simplified DSSP (no mkdssp binary needed). "
            "Helix = consecutive turn-4 H-bonds; Sheet = long-range H-bonds. "
            "Less precise than canonical DSSP, but captures the helix/sheet/coil signal needed to track unfolding."
        )
    else:
        description = "Per-residue helix/sheet/coil content over the trajectory. The timeline shows when structure breaks down."

    return {
        "name": name,
        "description": description,
        "image": output_path,
        "stats": {
            "method":         "kabsch_sander_fallback" if used_fallback else "mkdssp",
            "mean_helix_pct": float(np.mean(helix)),
            "mean_sheet_pct": float(np.mean(sheet)),
            "mean_coil_pct":  float(np.mean(coil)),
            "n_residues":     int(n_res),
        },
    }


def analyze_pca(
    traj: md.Trajectory,
    output_path: str,
    n_components: int = 2,
    **_kwargs,
) -> dict:
    """PCA on CA atom coordinates.

    Plots a PC1-vs-PC2 scatter (frames coloured by time) plus a scree bar
    showing the explained variance of the first ``n_components`` modes.
    The user can crank ``n_components`` up to capture as much variance as
    they need; we always show PC1/PC2 in the scatter for compact display.
    """
    try:
        from sklearn.decomposition import PCA
    except ImportError as exc:
        raise RuntimeError(
            "PCA needs scikit-learn. Install with `pip install scikit-learn` "
            "or `conda install scikit-learn`."
        ) from exc

    n_components = max(1, int(n_components))
    ca_indices = traj.topology.select("name CA")
    if len(ca_indices) < 2:
        raise ValueError("Need at least 2 CA atoms for PCA")
    if traj.n_frames < n_components + 1:
        raise ValueError(
            f"Need at least {n_components + 1} frames to fit {n_components} PCs "
            f"(have {traj.n_frames})"
        )

    flat = traj.xyz[:, ca_indices, :].reshape(traj.n_frames, len(ca_indices) * 3)
    pca = PCA(n_components=n_components)
    proj = pca.fit_transform(flat)
    var = pca.explained_variance_ratio_

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    if n_components >= 2:
        sc = axes[0].scatter(
            proj[:, 0], proj[:, 1],
            c=np.arange(traj.n_frames), cmap="viridis", alpha=0.7,
        )
        axes[0].plot(proj[:, 0], proj[:, 1], color="gray", alpha=0.25)
        axes[0].set_xlabel("PC1")
        axes[0].set_ylabel("PC2")
        cbar = plt.colorbar(sc, ax=axes[0])
        cbar.set_label("Frame")
        axes[0].set_title("PC1 vs PC2 (frames coloured by time)")
    else:
        axes[0].plot(proj[:, 0], "C0-", linewidth=1.5)
        axes[0].set_xlabel("Frame")
        axes[0].set_ylabel("PC1")
        axes[0].set_title("PC1 over time")
    axes[0].grid(True, alpha=0.3)

    axes[1].bar(np.arange(1, n_components + 1), var * 100, color="C0", alpha=0.85)
    axes[1].set_xticks(np.arange(1, n_components + 1))
    axes[1].set_xlabel("Principal component")
    axes[1].set_ylabel("Explained variance (%)")
    axes[1].set_title(f"Scree plot (cumulative: {np.sum(var) * 100:.1f}%)")
    axes[1].grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    stats = {
        "n_components":          n_components,
        "cumulative_variance_pct": float(np.sum(var) * 100),
    }
    for i, v in enumerate(var):
        stats[f"PC{i + 1}_variance_pct"] = float(v * 100)
    return {
        "name": f"PCA ({n_components} component{'s' if n_components != 1 else ''})",
        "description": "Principal component analysis on CA coordinates. PC1 vs PC2 reveals dominant collective motions; the scree plot shows how much each PC contributes.",
        "image": output_path,
        "stats": stats,
    }


def analyze_force_extension(
    traj: md.Trajectory,
    output_path: str,
    traj_file: str | None = None,
    **_kwargs,
) -> dict:
    """Force vs extension curves for pulling simulations.

    Reconstructs force from the spring positions stored in the .run.up
    HDF5 file and the AFM/Tension config table that lives next to the
    trajectory in the job directory. Mirrors ``start/Pulling_Simulation_Force.py``
    so we don't need to invoke that script as a subprocess.
    """
    if not traj_file:
        raise ValueError("force_extension needs the path to the .run.up file")

    UPSIDE_TO_PN = 41.4

    afm_path = None
    traj_path = Path(traj_file).resolve()
    search_dirs = [traj_path.parent, traj_path.parent.parent, traj_path.parent.parent.parent]
    for d in search_dirs:
        for candidate in ("Velocity_Simulations.dat", "Tension_Simulations.dat"):
            p = d / candidate
            if p.is_file():
                afm_path = p
                break
        if afm_path:
            break
    if afm_path is None:
        raise FileNotFoundError(
            "No Velocity_Simulations.dat or Tension_Simulations.dat found near the trajectory; "
            "run a pulling simulation to enable this analysis."
        )

    fields = [ln.split() for ln in open(afm_path)]
    if len(fields) < 2:
        raise ValueError(f"AFM table {afm_path} is empty or malformed")
    rows = fields[1:]

    springs = []
    DIM_NAME = ("x", "y", "z")
    for spring_idx, row in enumerate(rows):
        residue = int(row[0])
        atom_idx = residue * 3 + 1  # CA atom in upside layout
        k = float(row[1])
        if len(row) == 8:
            vx, vy, vz = float(row[5]), float(row[6]), float(row[7])
        else:
            vx, vy, vz = float(row[2]), float(row[3]), float(row[4])
        for dim, v in enumerate([vx, vy, vz]):
            if v != 0:
                springs.append({
                    "spring_idx": spring_idx,
                    "residue":    residue,
                    "atom_idx":   atom_idx,
                    "dim":        dim,
                    "dim_name":   DIM_NAME[dim],
                    "k":          k,
                })

    if not springs:
        raise ValueError(
            f"AFM table {afm_path.name} has no rows with non-zero pulling velocity"
        )

    pos_by_atom = {}
    tip_pos = None
    with tb.open_file(traj_file) as t:
        if "tip_pos" not in t.root.output:
            raise RuntimeError(
                "Trajectory has no /output/tip_pos dataset - this isn't a pulling run."
            )
        for g_no, g in enumerate(_output_groups(t)):
            sl = slice(0, None) if g_no == 0 else slice(1, None)
            tip_chunk = g.tip_pos[sl]
            tip_pos = tip_chunk if tip_pos is None else np.concatenate([tip_pos, tip_chunk])
            for s in springs:
                pos_chunk = g.pos[sl, 0, s["atom_idx"], s["dim"]]
                key = (s["atom_idx"], s["dim"])
                pos_by_atom[key] = (
                    pos_chunk if key not in pos_by_atom
                    else np.concatenate([pos_by_atom[key], pos_chunk])
                )

    plt.figure(figsize=(10, 6))
    summary_stats = {}
    for s in springs:
        pos = pos_by_atom[(s["atom_idx"], s["dim"])]
        tip = tip_pos[:, s["spring_idx"], s["dim"]]
        force = s["k"] * (tip - pos) * UPSIDE_TO_PN
        extension = pos - pos[0]
        label = f"Res {s['residue']} ({s['dim_name']})"
        plt.plot(extension, force, linewidth=1.5, label=label)
        summary_stats[label] = {
            "max_force_pN":     float(np.max(force)),
            "mean_force_pN":    float(np.mean(force)),
            "final_extension_A": float(extension[-1]),
        }

    plt.xlabel("Extension (Å)")
    plt.ylabel("Force (pN)")
    plt.title("Force vs Extension")
    plt.grid(True, alpha=0.3)
    plt.legend(fontsize="small")
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    flat_stats = {}
    for label, s in summary_stats.items():
        for k, v in s.items():
            flat_stats[f"{label}__{k}"] = v
    flat_stats["n_pulling_springs"] = len(springs)

    return {
        "name": "Force vs Extension",
        "description": "Force on each pulling spring vs the residue's displacement from its starting position. Sawtooth peaks mark unfolding events.",
        "image": output_path,
        "stats": flat_stats,
    }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

ANALYSES = {
    "rg":           ("Rg.png",                analyze_rg),
    "rmsd":         ("RMSD.png",              analyze_rmsd),
    "rmsf":         ("RMSF.png",              analyze_rmsf),
    "e2e":          ("EndToEnd.png",          analyze_e2e),
    "contacts":     ("ContactMap.png",        analyze_contacts),
    "hbonds":       ("HBonds.png",            analyze_hbonds),
    "salt_bridges": ("SaltBridges.png",       analyze_salt_bridges),
    "shape":        ("Shape.png",             analyze_shape),
    "cross_corr":   ("CrossCorrelation.png",  analyze_cross_correlation),
    "ss":           ("SecondaryStructure.png", analyze_secondary_structure),
    "pca":          ("PCA.png",               analyze_pca),
    "force_ext":    ("ForceExtension.png",    analyze_force_extension),
}


def run_analyses(
    traj_file: str,
    output_dir: str,
    analyses: list,
    params: dict | None = None,
) -> dict:
    """Load ``traj_file`` once, run each requested analysis, return a
    dict keyed by analysis id with image paths and stats.

    ``params`` is an optional ``{analysis_key: {kwarg: value, ...}}`` map
    of per-analysis overrides (e.g. ``{"pca": {"n_components": 5}}``).
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    params = params or {}

    traj = load_upside_traj(traj_file)
    results = {}
    for key in analyses:
        if key not in ANALYSES:
            results[key] = {"error": f"Unknown analysis '{key}'"}
            continue
        filename, func = ANALYSES[key]
        try:
            kwargs = dict(params.get(key, {}))
            kwargs.setdefault("traj_file", traj_file)
            results[key] = func(traj, str(out / filename), **kwargs)
        except Exception as exc:
            results[key] = {"error": f"{type(exc).__name__}: {exc}"}
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main(argv: list) -> int:
    if len(argv) < 4:
        sys.stderr.write(
            "Usage: python dynalab_analysis.py <traj.run.up> <output_dir> "
            "<analysis>[:k=v,...] [<analysis>[:k=v,...] ...]\n"
            f"Available analyses: {', '.join(ANALYSES)}\n"
            "Per-analysis params (PCA only): pca:n_components=4\n"
        )
        return 1

    traj_file = argv[1]
    output_dir = argv[2]
    raw_args = argv[3:]

    if not os.path.isfile(traj_file):
        sys.stderr.write(f"Trajectory file not found: {traj_file}\n")
        return 1

    analyses = []
    params: dict = {}
    for arg in raw_args:
        if ":" in arg:
            key, _, kvs = arg.partition(":")
            analyses.append(key)
            for kv in kvs.split(","):
                if "=" in kv:
                    k, _, v = kv.partition("=")
                    try:
                        v_cast: object = int(v)
                    except ValueError:
                        try:
                            v_cast = float(v)
                        except ValueError:
                            v_cast = v
                    params.setdefault(key, {})[k] = v_cast
        else:
            analyses.append(arg)

    results = run_analyses(traj_file, output_dir, analyses, params=params)
    (Path(output_dir) / "results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))

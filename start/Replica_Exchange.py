#!/usr/bin/env python
"""Replica-exchange (REMD) driver for web jobs — mirrors example/02.ReplicaExchangeSimulation/run.py
without SLURM: runs ``obj/upside`` locally under the job directory.

Expected argv:
  1 pdb_id (e.g. ``input``)
  2 pdb_dir (job directory; must contain ``<pdb_id>.pdb``)
  3 duration (integration steps)
  4 frame_interval
  5 continue_sim (``False`` / ``True``; web only supports ``False`` for now)
  6 n_rep (number of temperature replicas, >= 2)
  7 T_low  8 T_high (reduced units, same convention as Single_Replica)
  9 replica_interval (steps between exchange attempts)
 10 restraints (pair spring filename in job dir, or ``None``)

Writes ``outputs/remd/<pdb_id>.run.<j>.up`` and a single ``<pdb_id>.run.log`` under ``outputs/remd/``.
"""

from __future__ import annotations

import os
import shutil
import subprocess as sp
import sys
from math import sqrt

import numpy as np

upside_path = os.environ["UPSIDE_HOME"]
upside_utils_dir = os.path.expanduser(upside_path + "/py")
sys.path.insert(0, upside_utils_dir)
import run_upside as ru  # noqa: E402

# ----------------------------------------------------------------------
# argv
# ----------------------------------------------------------------------
if len(sys.argv) < 11:
    print(
        "Usage: Replica_Exchange.py <pdb_id> <pdb_dir> <duration> <frame_interval> "
        "<continue> <n_rep> <T_low> <T_high> <replica_interval> <restraints>",
        file=sys.stderr,
    )
    sys.exit(2)

pdb_id = sys.argv[1]
pdb_dir = sys.argv[2]
is_native = True
ff = "ff_2.1"

duration = sys.argv[3]
frame_interval = sys.argv[4]
continue_sim = sys.argv[5]

try:
    n_rep = int(float(sys.argv[6]))
except ValueError:
    n_rep = 8
n_rep = max(2, min(int(n_rep), 32))

try:
    T_low = float(sys.argv[7])
    T_high = float(sys.argv[8])
except ValueError:
    T_low, T_high = 0.80, 0.94
if T_high < T_low:
    T_low, T_high = T_high, T_low

try:
    replica_interval = int(float(sys.argv[9]))
except ValueError:
    replica_interval = 10
replica_interval = max(1, min(replica_interval, 100_000))

restraints = sys.argv[10]

is_continue = str(continue_sim).lower() in ("true", "1")
if is_continue:
    print("Replica_Exchange.py: continue_sim is not supported for web REMD yet; exiting.", file=sys.stderr)
    sys.exit(1)

randomseed = np.random.randint(0, 100_000)

# ----------------------------------------------------------------------
# Paths (cwd is the job directory)
# ----------------------------------------------------------------------
base_dir = "./"
input_dir = "{}/inputs".format(base_dir)
output_dir = "{}/outputs".format(base_dir)
run_dir = "{}/remd".format(output_dir)

for direc in (input_dir, output_dir, run_dir):
    if not os.path.exists(direc):
        os.makedirs(direc)

h5_files = []
for j in range(n_rep):
    h5_files.append("{}/{}.run.{}.up".format(run_dir, pdb_id, j))
h5_files_str = " ".join(h5_files)
log_file = "{}/{}.run.log".format(run_dir, pdb_id)

# ----------------------------------------------------------------------
# Initial structure
# ----------------------------------------------------------------------
print("Initial structure gen...")
cmd = (
    "python {0}/PDB_to_initial_structure.py "
    "{1}/{2}.pdb "
    "{3}/{2} "
    "--record-chain-breaks "
    "--disable-recentering "
).format(upside_utils_dir, pdb_dir, pdb_id, input_dir)
print(cmd)
sp.check_output(cmd.split())

# ----------------------------------------------------------------------
# Configure (same base physics as Single_Replica.py; no membrane kwargs)
# ----------------------------------------------------------------------
param_dir_base = os.path.expanduser(upside_path + "/parameters/")
param_dir_common = param_dir_base + "common/"
param_dir_ff = param_dir_base + "{}/".format(ff)

fasta = "{}/{}.fasta".format(input_dir, pdb_id)
kwargs = dict(
    rama_library=param_dir_common + "rama.dat",
    rama_sheet_mix_energy=param_dir_ff + "sheet",
    reference_state_rama=param_dir_common + "rama_reference.pkl",
    hbond_energy=param_dir_ff + "hbond.h5",
    rotamer_placement=param_dir_ff + "sidechain.h5",
    dynamic_rotamer_1body=True,
    rotamer_interaction=param_dir_ff + "sidechain.h5",
    environment_potential=param_dir_ff + "environment.h5",
    bb_environment_potential=param_dir_ff + "bb_env.dat",
    chain_break_from_file="{}/{}.chain_breaks".format(input_dir, pdb_id),
)
if is_native:
    kwargs["initial_structure"] = "{}/{}.initial.npy".format(input_dir, pdb_id)

config_base = "{}/{}.up".format(input_dir, pdb_id)
print("Configuring...")
config_stdout = ru.upside_config(fasta, config_base, **kwargs)
print("Config commandline options:")
print(config_stdout)

adv_kwargs: dict = {}
if restraints and str(restraints).lower() not in ("none", ""):
    adv_kwargs["pair_spring"] = restraints
config_stdout = ru.advanced_config(config_base, **adv_kwargs)
print("Advanced Config commandline options:")
print(config_stdout)

# ----------------------------------------------------------------------
# Run (replica exchange)
# ----------------------------------------------------------------------
upside_opts = (
    "--duration {} "
    "--frame-interval {} "
    "--temperature {} "
    "--seed {} "
    "--disable-recentering "
    "--record-momentum "
)

tempers = np.linspace(sqrt(T_low), sqrt(T_high), n_rep) ** 2
tempers_str = ",".join(str(t) for t in tempers)

swap_sets = ru.swap_table2d(1, len(tempers))
upside_opts += "--replica-interval {} --swap-set {} --swap-set {} "
upside_opts = upside_opts.format(
    duration,
    frame_interval,
    tempers_str,
    randomseed,
    replica_interval,
    swap_sets[0],
    swap_sets[1],
)

for fn in h5_files:
    shutil.copyfile(config_base, fn)

print("Running REMD ({} replicas)...".format(n_rep))
cmd_run = "{}/obj/upside {} {} | tee {}".format(upside_path, upside_opts, h5_files_str, log_file)
sp.check_call(cmd_run, shell=True)
print("Replica exchange finished.")

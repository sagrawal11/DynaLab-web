#!/usr/bin/env python

import os
import sys
import shutil
import subprocess as sp
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import tables as tb

upside_path = os.environ['UPSIDE_HOME']
upside_utils_dir = os.path.expanduser(upside_path+"/py")
sys.path.insert(0, upside_utils_dir)
import run_upside as ru

#----------------------------------------------------------------------
## General Settings and Path
#----------------------------------------------------------------------

pdb_id         = sys.argv[1] # switch to 1dfn for multi-chain showing
pdb_dir        = sys.argv[2]
sim_id         = sys.argv[3]
is_native      = True
ff             = 'ff_2.1'
T              = sys.argv[7]
duration       = sys.argv[4]
frame_interval = sys.argv[5]
base_dir       = './'

continue_sim   = sys.argv[6]  # when you run a new simulation, set it as "False"
                         # "True" means restarting the simulation from the last frame
                         # of the previous trajectories (they should have the same
                         # pdb_id and sim_id as the new simulation, and exist in the
                         # corresponding path)

restraints = sys.argv[8]

n_rep = 1
if len(sys.argv) > 9:
    try:
        n_rep = int(sys.argv[9])
    except ValueError:
        n_rep = 1
n_rep = max(1, min(int(n_rep), 32))

is_continue = str(continue_sim).lower() in ('true', '1')
if is_continue and n_rep > 1:
    print('Warning: continue_sim with multiple replicas is not supported; using 1 replica.')
    n_rep = 1

#----------------------------------------------------------------------
## Initialization
#----------------------------------------------------------------------

input_dir  = "{}/inputs".format(base_dir)
output_dir = "{}/outputs".format(base_dir)

def replica_paths(index):
    """Return (slot_sim_id, run_dir, h5_file, log_file) for replica index ``index``."""
    if n_rep == 1:
        sid = sim_id
    else:
        sid = "{}_r{}".format(sim_id, index)
    run_j = "{}/{}".format(output_dir, sid)
    h5_j = "{}/{}.run.up".format(run_j, sid)
    log_j = "{}/{}.run.log".format(run_j, sid)
    return sid, run_j, h5_j, log_j

_, run_dir, h5_file, log_file = replica_paths(0)

make_dirs = [input_dir, output_dir]
for direc in make_dirs:
    if not os.path.exists(direc):
        os.makedirs(direc)

for j in range(n_rep):
    _, rj, _, _ = replica_paths(j)
    if not os.path.exists(rj):
        os.makedirs(rj)

#----------------------------------------------------------------------
## Check the previous trajectories if you set continue_sim = True
#----------------------------------------------------------------------

if is_continue:
    exist = os.path.exists(h5_file)
    if not exist:
        print('Warning: no previous trajectory file {}!'.format(h5_file))
        print('set "continue_sim = False" and start a new simulation')
        is_continue = False
    else:
        exist = os.path.exists(log_file)
        if not exist:
            print('Warning: no previous log file {}!'.format(log_file))

#----------------------------------------------------------------------
## Generate Upside readable initial structure (and fasta) from PDB
#----------------------------------------------------------------------

if not is_continue:
    print ("Initial structure gen...")
    cmd = (
           "python {0}/PDB_to_initial_structure.py "
           "{1}/{2}.pdb "
           "{3}/{2} "
           "--record-chain-breaks "
           "--disable-recentering "
          ).format(upside_utils_dir, pdb_dir, pdb_id, input_dir )
    print (cmd)
    sp.check_output(cmd.split())


#----------------------------------------------------------------------
## Configure
#----------------------------------------------------------------------

# parameters
param_dir_base = os.path.expanduser(upside_path+"/parameters/")
param_dir_common = param_dir_base + "common/"
param_dir_ff = param_dir_base + '{}/'.format(ff)

_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
import web_membrane as _wm  # noqa: E402
import web_restraints as _wr  # noqa: E402

_job_cfg = _wm.find_dynalab_config(pdb_dir)
_rc_flags = _wm.upside_recentering_flags(_job_cfg)

# options
print ("Configuring...")
fasta = "{}/{}.fasta".format(input_dir, pdb_id)
kwargs = dict(
               rama_library              = param_dir_common + "rama.dat",
               rama_sheet_mix_energy     = param_dir_ff + "sheet",
               reference_state_rama      = param_dir_common + "rama_reference.pkl",
               hbond_energy              = param_dir_ff + "hbond.h5",
               rotamer_placement         = param_dir_ff + "sidechain.h5",
               dynamic_rotamer_1body     = True,
               rotamer_interaction       = param_dir_ff + "sidechain.h5",
               environment_potential     = param_dir_ff + "environment.h5",
               bb_environment_potential  = param_dir_ff + "bb_env.dat",
               chain_break_from_file     = "{}/{}.chain_breaks".format(input_dir, pdb_id),
            )
kwargs.update(
    _wm.membrane_kwargs_for_upside(
        _job_cfg, param_dir_ff=param_dir_ff, legacy_pulling_default=False,
    )
)

if is_native:
    kwargs['initial_structure'] =  "{}/{}.initial.npy".format(input_dir, pdb_id)

config_base = "{}/{}.up".format( input_dir, pdb_id)
if not is_continue:
    print ("Configuring...")
    config_stdout = ru.upside_config(fasta, config_base, **kwargs)
    print ("Config commandline options:")
    print (config_stdout)

if not is_continue:

    kwargs = {}
    kwargs.update(_wr.extra_restraint_kwargs(pdb_dir))
    if restraints and str(restraints).lower() not in ("none", ""):
        kwargs["pair_spring"] = restraints

    config_stdout = ru.advanced_config(config_base, **kwargs)
    print ("Advanced Config commandline options:")
    print (config_stdout)

#----------------------------------------------------------------------
## Run Settings
#----------------------------------------------------------------------

upside_opts_tmpl = (
                 "--duration {} "
                 "--frame-interval {} "
                 "--temperature {} "
                 "--seed {} "
                 "{}"
                 "--record-momentum "
                 "{}"
              )

restart_str = "--restart-using-momentum" if is_continue else ""


def _replica_pool_max_workers(num_replicas: int) -> int:
    """Cap concurrent Upside processes for independent replicas (default: ``cpu_count``)."""
    cpu = os.cpu_count() or 1
    raw = os.environ.get("DYNALAB_REPLICA_MAX_PARALLEL", "").strip()
    if raw:
        try:
            cap = int(raw)
        except ValueError:
            cap = cpu
        cap = max(1, cap)
    else:
        cap = cpu
    return max(1, min(int(num_replicas), cap))


def _run_upside_subprocess(j_index: int, randomseed: int) -> None:
    """Launch one Upside integration (assumes ``h5_j`` already prepared for this replica)."""
    _, _run_j, h5_j, log_j = replica_paths(j_index)
    upside_opts = upside_opts_tmpl.format(
        duration, frame_interval, T, randomseed, _rc_flags, restart_str
    )
    print("Running replica {} / {} ...".format(j_index + 1, n_rep))
    cmd = "{}/obj/upside {} {} | tee {}".format(upside_path, upside_opts, h5_j, log_j)
    sp.check_call(cmd, shell=True)


if is_continue:
    # Restart path: single replica only (see warning above); keep strictly sequential.
    for j in range(n_rep):
        _, run_j, h5_j, log_j = replica_paths(j)
        randomseed = np.random.randint(0, 100000)
        upside_opts = upside_opts_tmpl.format(
            duration, frame_interval, T, randomseed, _rc_flags, restart_str
        )

        if j > 0:
            break
        print("Archiving prev output...")

        localtime = time.asctime(time.localtime(time.time()))
        localtime = localtime.replace("  ", " ")
        localtime = localtime.replace(" ", "_")
        localtime = localtime.replace(":", "-")

        if os.path.exists(log_j):
            shutil.move(log_j, "{}.bck_{}".format(log_j, localtime))
        else:
            print("Warning: no previous log file {}!".format(log_j))

        with tb.open_file(h5_j, "a") as t:
            i = 0
            while "output_previous_%i" % i in t.root:
                i += 1
            new_name = "output_previous_%i" % i
            if "output" in t.root:
                n = t.root.output
            else:
                n = t.get_node("/output_previous_%i" % (i - 1))

            t.root.input.pos[:, :, 0] = n.pos[-1, 0]
            mom = n.mom[-1, 0]
            new_mom = mom.reshape(mom.shape[0], mom.shape[1], 1)

            if "/input/mom" in t:
                t.remove_node(t.root.input, "mom", recursive=True)

            t.create_earray(
                t.root.input,
                "mom",
                obj=new_mom,
                filters=tb.Filters(complib="zlib", complevel=5, fletcher32=True),
            )

            if "output" in t.root:
                t.root.output._f_rename(new_name)

        print("Running replica {} / {} ...".format(j + 1, n_rep))
        cmd = "{}/obj/upside {} {} | tee {}".format(upside_path, upside_opts, h5_j, log_j)
        sp.check_call(cmd, shell=True)

elif n_rep <= 1:
    j = 0
    _, run_j, h5_j, log_j = replica_paths(j)
    randomseed = np.random.randint(0, 100000)
    upside_opts = upside_opts_tmpl.format(
        duration, frame_interval, T, randomseed, _rc_flags, restart_str
    )
    shutil.copyfile(config_base, h5_j)
    print("Running replica {} / {} ...".format(j + 1, n_rep))
    cmd = "{}/obj/upside {} {} | tee {}".format(upside_path, upside_opts, h5_j, log_j)
    sp.check_call(cmd, shell=True)

else:
    # Independent replicas: same seed draw order as the old sequential loop, then
    # run up to min(n_rep, cpu_count) Upside processes concurrently.
    replica_seeds = [np.random.randint(0, 100000) for _ in range(n_rep)]
    for j in range(n_rep):
        _, _rj, h5_j, _log_j = replica_paths(j)
        shutil.copyfile(config_base, h5_j)

    max_workers = _replica_pool_max_workers(n_rep)
    print(
        "Running {} independent replicas with up to {} concurrent Upside processes ...".format(
            n_rep, max_workers
        )
    )
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [
            pool.submit(_run_upside_subprocess, j, replica_seeds[j])
            for j in range(n_rep)
        ]
        for fut in as_completed(futures):
            fut.result()

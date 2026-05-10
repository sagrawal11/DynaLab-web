# Upside2 Simulation Cookbook

A reference of ~100 ready-to-run commands covering every common scenario. All commands assume you are inside the Dev Container (or Codespaces / Docker shell) with `$UPSIDE_HOME` set and you are working from the `start/` directory unless noted otherwise.

---

## How to Read This Document

Every simulation follows the same three-step pattern:

```
Step 1 — Convert PDB to Upside format  (run once per protein)
Step 2 — Configure the simulation      (run once per experiment type)
Step 3 — Run the engine                (the actual simulation)
```

The `start/Single_Replica.py` and `start/Pulling_Simulations.py` scripts wrap all three steps into one command. The raw commands below show what those scripts are doing under the hood, so you understand what's happening and can customise anything.

**Argument quick-reference for the start/ scripts:**

| Position | Name | Example | Meaning |
|---|---|---|---|
| 1 | `pdb_id` | `1dfn` | PDB filename without `.pdb` |
| 2 | `pdb_dir` | `../example/01.GettingStarted/pdb` | Folder containing the PDB file |
| 3 | `sim_id` | `my_run` | Output folder name (you choose) |
| 4 | `duration` | `1e7` | Simulation steps (1e7 = 10 million) |
| 5 | `frame_interval` | `100` | Save a snapshot every N steps |
| 6 | `sim_type` | `tension` | Pulling sims only: `tension` or `velocity` |
| 7 | `continue_sim` | `False` | `True` = extend a previous run |
| 8 | `temperature` | `0.85` | Thermostat temperature (reduced units; ~0.8–1.0 ≈ physiological range) |
| 9 | `restraints` | `None` | Restraint file path, or `None` |

**Temperature guide (reduced units):**

| Value | Rough meaning |
|---|---|
| 0.70 | Very cold — protein nearly frozen |
| 0.80 | Low end physiological — near folding temperature for stable proteins |
| 0.85 | Standard "room temperature" for most runs |
| 0.90 | Warm — starting to sample partially unfolded states |
| 0.94 | Hot — heavy unfolding, used as upper limit in REMD |
| 1.00 | Very hot — mostly unfolded |
| 1.20 | Denaturing — fully unfolded baseline |

---

## Part 1 — Single-Replica Equilibrium Simulations (No Pulling)

Basic simulations where the protein just evolves freely at a fixed temperature. Good for equilibration, folding studies, and baseline behaviour.

### 1. Quickest possible test run (defensin, 1 million steps)
```bash
cd start
python Single_Replica.py 1dfn ../example/01.GettingStarted/pdb quick_test 1e6 100 False 0.85 None
```

### 2. Standard production run (10 million steps, save every 100)
```bash
python Single_Replica.py 1dfn ../example/01.GettingStarted/pdb prod_run 1e7 100 False 0.85 None
```

### 3. Long production run (100 million steps — overnight)
```bash
python Single_Replica.py 1dfn ../example/01.GettingStarted/pdb long_run 1e8 1000 False 0.85 None
```

### 4. Low temperature — stable, near-native structure
```bash
python Single_Replica.py 1dfn ../example/01.GettingStarted/pdb cold_run 1e7 100 False 0.70 None
```

### 5. Physiological lower bound temperature
```bash
python Single_Replica.py 1dfn ../example/01.GettingStarted/pdb physio_low 1e7 100 False 0.80 None
```

### 6. Standard physiological temperature
```bash
python Single_Replica.py 1dfn ../example/01.GettingStarted/pdb physio_std 1e7 100 False 0.85 None
```

### 7. Warm temperature — sample partially unfolded states
```bash
python Single_Replica.py 1dfn ../example/01.GettingStarted/pdb warm_run 1e7 100 False 0.90 None
```

### 8. Hot temperature — heavily sample unfolded ensemble
```bash
python Single_Replica.py 1dfn ../example/01.GettingStarted/pdb hot_run 1e7 100 False 0.94 None
```

### 9. Denaturing temperature — fully unfolded baseline
```bash
python Single_Replica.py 1dfn ../example/01.GettingStarted/pdb denat_run 1e7 100 False 1.20 None
```

### 10. Save frames more frequently (every 10 steps — large file, fine-grained)
```bash
python Single_Replica.py 1dfn ../example/01.GettingStarted/pdb fine_traj 1e6 10 False 0.85 None
```

### 11. Save frames less frequently (every 1000 steps — small file, coarse)
```bash
python Single_Replica.py 1dfn ../example/01.GettingStarted/pdb coarse_traj 1e8 1000 False 0.85 None
```

### 12. Different protein: chignolin (tiny 10-residue beta hairpin)
```bash
python Single_Replica.py chig ../example/02.ReplicaExchangeSimulation/pdb chig_run 1e7 100 False 0.85 None
```

### 13. Different protein: 1aie
```bash
python Single_Replica.py 1aie ../example/01.GettingStarted/pdb 1aie_run 1e7 100 False 0.85 None
```

### 14. Different protein: 1tup (p53 DNA-binding domain)
```bash
python Single_Replica.py 1tup ../example/01.GettingStarted/pdb 1tup_run 1e7 100 False 0.85 None
```

### 15. Continue (extend) a previous run from where it left off
```bash
python Single_Replica.py 1dfn ../example/01.GettingStarted/pdb prod_run 1e7 100 True 0.85 None
```
> `True` in position 7 tells Upside to load the last frame of `outputs/prod_run/prod_run.run.up` and keep going. The old trajectory is archived inside the same file.

### 16. Your own protein — point to any PDB directory
```bash
python Single_Replica.py myprotein /path/to/my/pdb/folder my_protein_run 1e7 100 False 0.85 None
```

---

## Part 2 — Constant-Tension Pulling Simulations

These are the core experiments for your research — applying a constant force to both ends of a protein to reveal cryptic epitopes. Think of it like stretching a rubber band at a fixed tension and watching what unfolds.

The force is defined in `Tension_Simulations.dat`. Each line specifies a residue and the force vector (x, y, z) applied to it.

**Default Tension_Simulations.dat (pull N and C terminus apart along z-axis):**
```
residue tension_x tension_y tension_z
0       0.0       0.0       -0.2
227     0.0       0.0        0.2
```
> Force is in reduced units. 1 reduced unit ≈ 41.4 pN. So 0.2 ≈ 8.3 pN, 1.0 ≈ 41.4 pN.

### 17. Standard constant-tension pull (default ~8 pN)
```bash
python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb tension_std 1e7 100 tension False 0.85 None
```

### 18. Light tension (~4 pN, force = 0.1 units) — edit Tension_Simulations.dat first
Edit `start/Tension_Simulations.dat`:
```
residue tension_x tension_y tension_z
0       0.0       0.0       -0.1
227     0.0       0.0        0.1
```
Then run:
```bash
python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb tension_4pN 1e7 100 tension False 0.85 None
```

### 19. Medium tension (~12 pN, force = 0.3 units)
Edit `Tension_Simulations.dat`: forces ±0.3, then:
```bash
python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb tension_12pN 1e7 100 tension False 0.85 None
```

### 20. Strong tension (~20 pN, force = 0.5 units)
Edit `Tension_Simulations.dat`: forces ±0.5, then:
```bash
python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb tension_20pN 1e7 100 tension False 0.85 None
```

### 21. Very strong tension (~41 pN, force = 1.0 units)
Edit `Tension_Simulations.dat`: forces ±1.0, then:
```bash
python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb tension_41pN 1e7 100 tension False 0.85 None
```

### 22. Constant tension, warm temperature (sample more conformations under force)
```bash
python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb tension_warm 1e7 100 tension False 0.90 None
```

### 23. Constant tension, cold temperature (more stable pulled state)
```bash
python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb tension_cold 1e7 100 tension False 0.80 None
```

### 24. Pull along x-axis instead of z-axis
Edit `Tension_Simulations.dat`:
```
residue tension_x tension_y tension_z
0      -0.2       0.0       0.0
227     0.2       0.0       0.0
```
```bash
python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb tension_xaxis 1e7 100 tension False 0.85 None
```

### 25. Pull collagen-like protein (your fibrosis target — replace with your PDB)
```bash
python Pulling_Simulations.py collagen1_frag /path/to/pdb tension_collagen 1e7 100 tension False 0.85 None
```

### 26. Pull fibronectin fragment
```bash
python Pulling_Simulations.py fibronectin_fn3 /path/to/pdb tension_fn3 1e7 100 tension False 0.85 None
```

### 27. Continue a tension run (extend trajectory)
```bash
python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb tension_std 1e7 100 tension True 0.85 None
```

---

## Part 3 — Velocity-Clamp (AFM-Mode) Pulling Simulations

Instead of a fixed force, you pull at a fixed speed — like an AFM cantilever moving at constant velocity. This mimics the most common single-molecule force spectroscopy experiment and generates force-extension curves.

The spring and velocity are defined in `Velocity_Simulations.dat`.

**Default Velocity_Simulations.dat:**
```
residue spring_const pulling_vel_x pulling_vel_y pulling_vel_z
0       0.05         0.0           0.0           0.0
227     0.05         0.0           0.0           -0.001
```
> Residue 0 is anchored (velocity = 0). Residue 227 is pulled along -z at speed 0.001 per step.

### 28. Standard AFM velocity pull
```bash
python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb afm_std 1e7 100 velocity False 0.85 None
```

### 29. Slow pull velocity (0.0001 per step — closer to equilibrium)
Edit `Velocity_Simulations.dat` velocity to `-0.0001`, then:
```bash
python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb afm_slow 1e7 100 velocity False 0.85 None
```

### 30. Fast pull velocity (0.01 per step — rapid extension)
Edit `Velocity_Simulations.dat` velocity to `-0.01`, then:
```bash
python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb afm_fast 1e7 100 velocity False 0.85 None
```

### 31. Stiffer spring constant (k=0.5 — sharper force resolution)
Edit `Velocity_Simulations.dat` spring to `0.5`, then:
```bash
python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb afm_stiff 1e7 100 velocity False 0.85 None
```

### 32. Softer spring constant (k=0.01 — more compliant cantilever)
Edit `Velocity_Simulations.dat` spring to `0.01`, then:
```bash
python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb afm_soft 1e7 100 velocity False 0.85 None
```

### 33. Pull from a middle residue (not terminus)
Edit `Velocity_Simulations.dat`:
```
residue spring_const pulling_vel_x pulling_vel_y pulling_vel_z
0       0.05         0.0           0.0            0.0
113     0.05         0.0           0.0           -0.001
```
```bash
python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb afm_mid 1e7 100 velocity False 0.85 None
```

### 34. Extract force-extension data from a velocity run
```bash
python Pulling_Simulation_Force.py Velocity_Simulations.dat 1dfn afm_std
```
> Writes `.dat` files to `start/results/` with columns: extension (nm), force (pN), tip position (nm).

---

## Part 4 — Replica Exchange MD (REMD)

Run N copies of the same protein simultaneously at different temperatures. Periodically, adjacent replicas can swap configurations. This is the gold standard for sampling rare unfolding events — it's much more efficient than just running one long simulation.

These use the REMD example script directly (not the `start/` wrappers, which don't expose REMD).

### 35. 8-replica REMD, T = 0.80–0.94, chignolin (the canonical test)
```bash
cd ../example/02.ReplicaExchangeSimulation
python run.py
```
> Runs 8 replicas: T = 0.80, 0.82, 0.84, 0.86, 0.88, 0.90, 0.92, 0.94 (sqrt-spaced). Outputs to `outputs/REMD/chig.run.0.up` through `chig.run.7.up`.

### 36. Modify REMD for your own protein — edit run.py parameters
Edit `example/02.ReplicaExchangeSimulation/run.py` (or copy it):
```python
pdb_id         = 'myprotein'
pdb_dir        = './pdb'
sim_id         = 'REMD_myprotein'
n_rep          = 8
T_low          = 0.80
T_high         = 0.94
duration       = 1e7
frame_interval = 100
```
```bash
python run.py
```

### 37. 4-replica REMD (faster, less coverage)
```python
n_rep = 4
T_low = 0.80
T_high = 0.94
```

### 38. 16-replica REMD (thorough sampling)
```python
n_rep = 16
T_low = 0.75
T_high = 1.00
```

### 39. Narrow temperature range REMD (near folding transition only)
```python
n_rep = 8
T_low = 0.82
T_high = 0.90
```

### 40. Wide temperature range REMD (folded to denatured)
```python
n_rep = 12
T_low = 0.70
T_high = 1.20
```

### 41. REMD with more frequent exchange attempts (better mixing)
```python
replica_interval = 5    # try exchange every 5 steps instead of 10
```

### 42. REMD with less frequent exchange attempts (lower overhead)
```python
replica_interval = 50
```

### 43. Very long REMD (100 million steps per replica)
```python
duration = 1e8
frame_interval = 1000
```

---

## Part 5 — Multiple Replicas of the Same Protein (Statistical Ensemble)

Run the same simulation multiple independent times with different random seeds. This gives you an ensemble of trajectories — better statistics, and you can average over stochastic variation.

### 44. Run 3 independent replicas of the same simulation
```bash
cd start

python Single_Replica.py 1dfn ../example/01.GettingStarted/pdb 1dfn_rep1 1e7 100 False 0.85 None
python Single_Replica.py 1dfn ../example/01.GettingStarted/pdb 1dfn_rep2 1e7 100 False 0.85 None
python Single_Replica.py 1dfn ../example/01.GettingStarted/pdb 1dfn_rep3 1e7 100 False 0.85 None
```
> Each call picks a different random seed automatically (line 36 of `Single_Replica.py`). The outputs go to separate folders.

### 45. 5 independent pulling replicas (ensemble of force-extension curves)
```bash
python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb pull_rep1 1e7 100 tension False 0.85 None
python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb pull_rep2 1e7 100 tension False 0.85 None
python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb pull_rep3 1e7 100 tension False 0.85 None
python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb pull_rep4 1e7 100 tension False 0.85 None
python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb pull_rep5 1e7 100 tension False 0.85 None
```

### 46. Bash loop: run 10 replicas automatically
```bash
for i in $(seq 1 10); do
    python Single_Replica.py 1dfn ../example/01.GettingStarted/pdb 1dfn_rep${i} 1e7 100 False 0.85 None
done
```

### 47. Bash loop: 10 pulling replicas at different tensions (simulate your centrifuge assay)
```bash
for tension in 0.1 0.15 0.2 0.25 0.3 0.35 0.4 0.45 0.5 0.6; do
    # Update Tension_Simulations.dat with this force level, then:
    python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb tension_${tension} 1e7 100 tension False 0.85 None
done
```

### 48. Run the sequential replica manager script
```bash
python Run_Replicas_Sequential.py Single_Replica 5
```
> Runs `Single_Replica.py` five times in sequence.

---

## Part 6 — Multiple Different Proteins in One Session

### 49. Compare folding of two proteins at the same temperature
```bash
python Single_Replica.py 1dfn ../example/01.GettingStarted/pdb 1dfn_compare 1e7 100 False 0.85 None
python Single_Replica.py 1aie ../example/01.GettingStarted/pdb 1aie_compare 1e7 100 False 0.85 None
```

### 50. Pull three proteins at the same force, compare unfolding pathways
```bash
python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb pull_1dfn 1e7 100 tension False 0.85 None
python Pulling_Simulations.py 1aie ../example/01.GettingStarted/pdb pull_1aie 1e7 100 tension False 0.85 None
python Pulling_Simulations.py 1tup ../example/01.GettingStarted/pdb pull_1tup 1e7 100 tension False 0.85 None
```

### 51. Pull same protein domain in different constructs (e.g. isolated vs. in context)
```bash
python Pulling_Simulations.py collagen_isolated /path/to/pdb pull_isolated 1e7 100 tension False 0.85 None
python Pulling_Simulations.py collagen_full /path/to/pdb pull_full 1e7 100 tension False 0.85 None
```

### 52. Scan the same protein across a temperature series
```bash
for T in 0.75 0.80 0.85 0.90 0.94 1.00; do
    python Single_Replica.py 1dfn ../example/01.GettingStarted/pdb 1dfn_T${T} 1e7 100 False ${T} None
done
```

### 53. Force-temperature phase diagram (vary both force and temperature)
```bash
for T in 0.80 0.85 0.90; do
    for force_label in low mid high; do
        # Update Tension_Simulations.dat for each force level, then:
        python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb pull_T${T}_${force_label} 1e7 100 tension False ${T} None
    done
done
```

---

## Part 7 — Restraints (Fixing Parts of the Protein)

Restraints let you hold specific residues in place, confine them to a region, or pin them to a point. Useful for studying a specific region while keeping the rest fixed, or for setting up complex pulling geometries.

All restraint files go in `start/` and are passed as the last argument (replacing `None`).

### Fixed-point wall restraint — keep a residue inside a sphere of radius r

**wall-const.dat:**
```
residue radius spring_const wall_type x0 y0 z0
0        5.0     4.0           1       0  0  0
```
> `wall_type 1` = sphere (soft wall). The residue is repelled if it moves more than `radius` Å from `(x0,y0,z0)`.

### 54. Run with a fixed wall restraint on residue 0
```bash
python Single_Replica.py 1dfn ../example/01.GettingStarted/pdb wall_run 1e7 100 False 0.85 wall-const.dat
```

### Pair wall restraint — keep two residues within r of each other

**wall-pair.dat:**
```
residue1 residue2 radius spring_const
4        26        8.0     4.0
```

### 55. Run with a pair wall (keep residues 4 and 26 within 8 Å)
```bash
python Single_Replica.py 1dfn ../example/01.GettingStarted/pdb pairwall_run 1e7 100 False 0.85 wall-pair.dat
```

### Fixed spring restraint — tether a residue to a point with a harmonic spring

**spring-const.dat:**
```
residue radius spring_const x0 y0 z0
0        5.0     4.0         0  0  0
```

### 56. Run with a harmonic anchor on residue 0
```bash
python Single_Replica.py 1dfn ../example/01.GettingStarted/pdb spring_run 1e7 100 False 0.85 spring-const.dat
```

### Pair spring restraint — harmonic spring between two residues

**spring-pair.dat:**
```
residue1 residue2 radius spring_const
4        26        8.0     4.0
```

### 57. Run with a harmonic pair spring
```bash
python Single_Replica.py 1dfn ../example/01.GettingStarted/pdb pairspring_run 1e7 100 False 0.85 spring-pair.dat
```

### Nail restraint — freeze a residue completely (infinite spring to its starting position)

**nail.dat:**
```
residue spring_const
0  4.0
```

### 58. Run with residue 0 nailed to its starting position
```bash
python Single_Replica.py 1dfn ../example/01.GettingStarted/pdb nail_run 1e7 100 False 0.85 nail.dat
```

### 59. Nail both termini, then pull a middle residue (simulate surface attachment + bead pull)
```bash
# nail.dat:
#   0   4.0
#   227 4.0
# Velocity_Simulations.dat:
#   113 0.05 0.0 0.0 -0.001
python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb nail_pull 1e7 100 velocity False 0.85 nail.dat
```

### 60. Confine a protein to a cavity (cavity radius = 30 Å)
This requires editing the Python script's `advanced_config` call directly to add `cavity_radius=30`. See `start/Single_Replica.py` lines 126–138.

### 61. Use restraint groups to define domains
Restraint groups let you assign residues to labelled sets and apply different forces to each. Specify as `'0-50'`, `'51-100'`, etc. in the `advanced_config` call.

---

## Part 8 — Membrane Protein Simulations

For proteins that live in a lipid bilayer (ion channels, GPCRs, transporters). The membrane potential confines the protein to the bilayer and applies the correct hydrophobic matching.

These are run from the membrane example directory.

### 62. Normal membrane simulation (OmpA outer membrane protein)
```bash
cd ../example/08.MembraneSimulation
python 0.normal.run.py
```

### 63. Membrane simulation with lateral pressure profile
```bash
python 2.lateral_pressure.run.py
```

### 64. Membrane simulation with fixed curvature
```bash
python 3.fixed_curvature.run.py
```

### 65. Membrane simulation with dynamic curvature (stage 1)
```bash
python 4.curvature_dynamics1.run.py
```

### 66. Membrane simulation with dynamic curvature (stage 2, after stage 1 finishes)
```bash
python 5.curvature_dynamics2.run.py
```

### 67. Membrane protein at higher temperature
Edit `0.normal.run.py`: set `T_low = T_high = 0.90`, then:
```bash
python 0.normal.run.py
```

### 68. Membrane simulation with z-recentering disabled (for transmembrane proteins)
The script already sets `--disable-z-recentering`. This is the correct flag whenever your protein spans the membrane.

### 69. Thick membrane (e.g. cholesterol-rich raft, ~40 Å bilayer half-width)
Edit `0.normal.run.py`: set `thickness = 40.0`.

### 70. Thin membrane (e.g. PE-rich, ~25 Å bilayer half-width)
Edit `0.normal.run.py`: set `thickness = 25.0`.

---

## Part 9 — Large Protein Systems

For proteins with thousands of residues, or multi-chain complexes. The big-system scripts use the `intensive_memory` flag to reduce RAM usage for very large systems.

### 71. Large protein from FASTA only (no PDB structure — starts from extended chain)
```bash
cd ../example/11.BigSystem
python 0.run.py
```
> Uses FASTA sequence only — Upside builds an extended (unfolded) starting conformation and folds it during the simulation.

### 72. Large protein with memory-efficient mode
Edit `0.run.py`: set `intensive_memory = True`.

### 73. Multi-chain complex (two copies of 1rkl — already in the pdb directory)
The PDB files `three_1rkl_a.pdb` and `three_1rkl_b.pdb` in `08.MembraneSimulation/pdb/` are examples of multi-chain systems. Run them through any of the standard scripts above, pointing `pdb_dir` at that folder.
```bash
cd start
python Single_Replica.py three_1rkl_a ../example/08.MembraneSimulation/pdb multichain_run 1e7 100 False 0.85 None
```

### 74. Two-protein complex — pull apart
Edit `Tension_Simulations.dat` to apply forces on residues at the interface of each chain (you need to know the residue numbers of the interface), then:
```bash
python Pulling_Simulations.py mycomplex /path/to/pdb complex_pull 1e7 100 tension False 0.85 None
```

---

## Part 10 — Hydrogen-Deuterium Exchange (HDX) Prediction

HDX exchange rates report on which backbone amide groups are solvent-exposed vs. buried. Upside can predict these from simulations. The HDX example has a full pipeline.

### 75. Run HDX prediction pipeline (all steps)
```bash
cd ../example/04.HDX
python 0.run.py        # run simulation
python 1.config.py     # generate HDX config
bash 2.traj_ana.sh     # analyse trajectory
bash 3.get_protaction_states.sh   # extract protection states
python 4.calc_HDX.py   # compute exchange rates
```

### 76. Run only the simulation part of HDX
```bash
cd ../example/04.HDX
python 0.run.py
```

---

## Part 11 — Restart / Continue Simulations

Upside preserves full trajectory history when restarting. Old data is stored as `output_previous_0`, `output_previous_1`, etc. inside the same `.up` file.

### 77. Continue any simulation from its last frame
Replace `False` with `True` in position 7:
```bash
python Single_Replica.py 1dfn ../example/01.GettingStarted/pdb my_run 1e7 100 True 0.85 None
```

### 78. Continue a pulling simulation
```bash
python Pulling_Simulations.py 1dfn ../example/01.GettingStarted/pdb tension_std 1e7 100 tension True 0.85 None
```

### 79. Use the dedicated restart example
```bash
cd ../example/13.RestartSimulation
python 0.run.py       # initial run
python 0.continue.py  # continuation
```

### 80. Read all trajectory segments (original + continuations) in analysis
```python
import tables as tb

def all_output_groups(t):
    i = 0
    while f'output_previous_{i}' in t.root:
        yield t.get_node(f'/output_previous_{i}')
        i += 1
    if 'output' in t.root:
        yield t.root.output

with tb.open_file('outputs/my_run/my_run.run.up', 'r') as t:
    import numpy as np
    all_pos = np.concatenate([g.pos[:] for g in all_output_groups(t)], axis=0)
```

---

## Part 12 — Direct Engine Commands (Advanced / No Python Wrapper)

The raw `upside` binary is at `$UPSIDE_HOME/obj/upside`. The Python scripts are just wrappers that generate an HDF5 config file and then call this binary. You can call it directly once you have a `.up` config file.

### 81. Minimum viable engine call
```bash
$UPSIDE_HOME/obj/upside \
  --duration 1000000 \
  --frame-interval 100 \
  --temperature 0.85 \
  --seed 42 \
  inputs/1dfn.up | tee outputs/test/test.run.log
```

### 82. Engine call with momentum recording (needed for restarts)
```bash
$UPSIDE_HOME/obj/upside \
  --duration 1000000 \
  --frame-interval 100 \
  --temperature 0.85 \
  --seed 42 \
  --record-momentum \
  inputs/1dfn.up | tee outputs/test/test.run.log
```

### 83. Engine call with recentering disabled (use for pulling sims)
```bash
$UPSIDE_HOME/obj/upside \
  --duration 1000000 \
  --frame-interval 100 \
  --temperature 0.85 \
  --seed 42 \
  --disable-recentering \
  inputs/1dfn.up | tee outputs/test/test.run.log
```

### 84. Engine call with z-recentering disabled (use for membrane sims)
```bash
$UPSIDE_HOME/obj/upside \
  --duration 1000000 \
  --frame-interval 100 \
  --temperature 0.85 \
  --seed 42 \
  --disable-z-recentering \
  inputs/1dfn.up | tee outputs/test/test.run.log
```

### 85. Engine call: 8-replica REMD (all replicas in one command, space-separated files)
```bash
$UPSIDE_HOME/obj/upside \
  --duration 5000 \
  --frame-interval 50 \
  --temperature 0.800,0.823,0.846,0.870,0.894,0.918,0.920,0.940 \
  --seed 1 \
  --replica-interval 10 \
  --swap-set 0,2,4,6 \
  --swap-set 1,3,5,7 \
  outputs/REMD/chig.run.0.up outputs/REMD/chig.run.1.up \
  outputs/REMD/chig.run.2.up outputs/REMD/chig.run.3.up \
  outputs/REMD/chig.run.4.up outputs/REMD/chig.run.5.up \
  outputs/REMD/chig.run.6.up outputs/REMD/chig.run.7.up \
  | tee outputs/REMD/chig.run.log
```

### 86. Restart engine from previous run (continue with momentum)
```bash
$UPSIDE_HOME/obj/upside \
  --duration 1000000 \
  --frame-interval 100 \
  --temperature 0.85 \
  --seed 99 \
  --restart-using-momentum \
  outputs/test/test.run.up | tee outputs/test/test_continued.run.log
```

---

## Part 13 — Configuration Only (No Simulation — Generate the .up File)

Sometimes you want to pre-generate a config file once and then run the engine separately (e.g., run on a cluster). Here is the Python needed to generate a config without running.

### 87. Convert PDB to initial structure files
```bash
python $UPSIDE_HOME/py/PDB_to_initial_structure.py \
  /path/to/myprotein.pdb \
  start/inputs/myprotein \
  --record-chain-breaks \
  --disable-recentering
```
> Creates `start/inputs/myprotein.fasta`, `myprotein.initial.npy`, `myprotein.chain_breaks`.

### 88. Generate base config from FASTA
```python
import sys
sys.path.insert(0, '$UPSIDE_HOME/py')
import run_upside as ru

ru.upside_config(
    fasta       = 'start/inputs/myprotein.fasta',
    output      = 'start/inputs/myprotein.up',
    rama_library              = '$UPSIDE_HOME/parameters/common/rama.dat',
    rama_sheet_mix_energy     = '$UPSIDE_HOME/parameters/ff_2.1/sheet',
    reference_state_rama      = '$UPSIDE_HOME/parameters/common/rama_reference.pkl',
    hbond_energy              = '$UPSIDE_HOME/parameters/ff_2.1/hbond.h5',
    rotamer_placement         = '$UPSIDE_HOME/parameters/ff_2.1/sidechain.h5',
    dynamic_rotamer_1body     = True,
    rotamer_interaction       = '$UPSIDE_HOME/parameters/ff_2.1/sidechain.h5',
    environment_potential     = '$UPSIDE_HOME/parameters/ff_2.1/environment.h5',
    bb_environment_potential  = '$UPSIDE_HOME/parameters/ff_2.1/bb_env.dat',
    initial_structure         = 'start/inputs/myprotein.initial.npy',
    chain_break_from_file     = 'start/inputs/myprotein.chain_breaks',
)
```

### 89. Add tension pulling to an existing config
```python
ru.advanced_config('start/inputs/myprotein.up', tension='Tension_Simulations.dat')
```

### 90. Add velocity (AFM) pulling to an existing config
```python
ru.advanced_config('start/inputs/myprotein.up', ask_before_using_AFM='Velocity_Simulations.dat')
```

### 91. Add a nail restraint to an existing config
```python
ru.advanced_config('start/inputs/myprotein.up', nail='nail.dat')
```

### 92. Add a cavity confinement
```python
ru.advanced_config('start/inputs/myprotein.up', cavity_radius=30)
```

### 93. Add membrane potential to base config
```python
ru.upside_config(
    fasta   = 'start/inputs/myprotein.fasta',
    output  = 'start/inputs/myprotein.up',
    # ... (all standard kwargs) ...,
    membrane_potential  = '$UPSIDE_HOME/parameters/ff_2.1/membrane.h5',
    membrane_thickness  = 31.8,
)
```

---

## Part 14 — Analysis After the Simulation

### 94. Read trajectory positions into Python
```python
import tables as tb
import numpy as np

with tb.open_file('start/outputs/my_run/my_run.run.up', 'r') as f:
    pos    = f.root.output.pos[:]       # shape: (n_frames, n_replicas, n_atoms, 3)
    energy = f.root.output.potential[:] # shape: (n_frames,)
    time   = f.root.output.time[:]      # shape: (n_frames,)

print(f'{len(time)} frames, final energy = {energy[-1]:.2f} kT')
```

### 95. Compute end-to-end distance over time (for pulling sims)
```python
import tables as tb
import numpy as np

with tb.open_file('start/outputs/tension_std/tension_std.run.up', 'r') as f:
    pos = f.root.output.pos[:,0,:,:]    # replica 0, shape (n_frames, n_atoms, 3)

# Upside stores N, CA, C for each residue; CA of residue i is at atom index 3*i+1
ca_first = pos[:, 1,  :]   # CA of residue 0
ca_last  = pos[:, -2, :]   # CA of last residue (check your residue count)
distance = np.linalg.norm(ca_last - ca_first, axis=1)  # Å

print(f'Initial end-to-end: {distance[0]:.1f} Å')
print(f'Final end-to-end:   {distance[-1]:.1f} Å')
```

### 96. Read force from a pulling simulation
```python
import tables as tb
import numpy as np

upside_to_pN = 41.4   # conversion factor

with tb.open_file('start/outputs/afm_std/afm_std.run.up', 'r') as f:
    pos     = f.root.output.pos[:,0,:,:]    # (n_frames, n_atoms, 3)
    tip_pos = f.root.output.tip_pos[:]      # (n_frames, n_springs, 3)

k = 0.05   # spring constant from your Velocity_Simulations.dat
pulled_atom = 3 * 227 + 1   # CA of residue 227

extension = tip_pos[:, 0, 2] - pos[:, pulled_atom, 2]   # z component
force_pN  = k * extension * upside_to_pN
print(f'Peak force: {force_pN.max():.1f} pN')
```

### 97. Extract a VTF trajectory for visualisation in VMD
```bash
cd start
python extract_vtf.py outputs/my_run/my_run.run.up outputs/my_run/my_run.vtf
```
> Opens in VMD: `vmd outputs/my_run/my_run.vtf`

### 98. Compute RMSD from native structure
```bash
cd ../example/03.TrajectoryAnalysis
python calc_rmsd.py
```

### 99. Analyse HDX output
```bash
cd ../example/04.HDX
python 4.calc_HDX.py
```

---

## Part 15 — Your Cryptic Epitope Discovery Workflow

The full pipeline for your fibrosis research, from start to nanobody candidate validation.

### 100. Full cryptic epitope discovery: pull collagen-I fragment at five force levels
```bash
cd start

# Generate the input structure once (only needed once per protein)
python $UPSIDE_HOME/py/PDB_to_initial_structure.py \
  /path/to/collagen_frag.pdb \
  inputs/collagen_frag \
  --record-chain-breaks --disable-recentering

# Step 1: Equilibrate (no force — establish baseline)
python Single_Replica.py collagen_frag /path/to/pdb col_equil 1e7 100 False 0.85 None

# Step 2: Low tension (~4 pN) — minimal stretching
# Edit Tension_Simulations.dat: forces ±0.1
python Pulling_Simulations.py collagen_frag /path/to/pdb col_4pN 1e7 100 tension False 0.85 None

# Step 3: Medium-low tension (~8 pN)
# Edit Tension_Simulations.dat: forces ±0.2
python Pulling_Simulations.py collagen_frag /path/to/pdb col_8pN 1e7 100 tension False 0.85 None

# Step 4: Medium tension (~15 pN) — below your centrifuge threshold
# Edit Tension_Simulations.dat: forces ±0.36
python Pulling_Simulations.py collagen_frag /path/to/pdb col_15pN 1e7 100 tension False 0.85 None

# Step 5: Medium-high tension (~20 pN) — inside your centrifuge window
# Edit Tension_Simulations.dat: forces ±0.48
python Pulling_Simulations.py collagen_frag /path/to/pdb col_20pN 1e7 100 tension False 0.85 None

# Step 6: High tension (~38 pN) — upper end of your centrifuge window
# Edit Tension_Simulations.dat: forces ±0.92
python Pulling_Simulations.py collagen_frag /path/to/pdb col_38pN 1e7 100 tension False 0.85 None
```

After these runs:
1. Compare structures from `col_equil` (native) vs. `col_20pN` / `col_38pN` (stretched) to identify exposed regions.
2. Those exposed surfaces are your **cryptic epitope candidates** — feed them to RFdiffusion / ProteinMPNN for nanobody design.
3. Validate candidate binders computationally with AlphaFold-Multimer (check ipTM > 0.7).
4. Experimentally: apply your centrifuge assay at 15 pN (no binding expected) and 20+ pN (binding expected). Fluorescent signal proves force-dependent binding = cryptic epitope confirmed.

---

## Quick Reference: Force Unit Conversions

| Reduced units | picoNewtons (pN) | Approximate context |
|---|---|---|
| 0.05 | 2.1 pN | Thermal fluctuation range |
| 0.10 | 4.1 pN | Light biological tension |
| 0.20 | 8.3 pN | Moderate cytoskeletal tension |
| 0.36 | 14.9 pN | Lower bound of your centrifuge assay |
| 0.48 | 19.9 pN | Middle of your centrifuge assay |
| 0.72 | 29.8 pN | Upper-middle of your centrifuge assay |
| 0.92 | 38.1 pN | Upper bound of your centrifuge assay |
| 1.00 | 41.4 pN | ~1 Upside force unit |
| 2.00 | 82.8 pN | Strong unfolding force |

> Formula: `force_pN = force_reduced × 41.4`

---

*All commands assume `$UPSIDE_HOME` is set (it is automatically set inside the Dev Container), you are running from `start/` unless otherwise noted, and the required input PDB files exist. Parameter files are in `$UPSIDE_HOME/parameters/`.*

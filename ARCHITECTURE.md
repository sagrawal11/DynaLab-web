# Upside2 MD — Architecture Reference

> **Upside2 MD** is a protein simulation engine from the Sosnick lab at the University of Chicago.  
> Authors: John Jumper (co-creator of AlphaFold, the AI that solved protein structure prediction), Xiangda Peng, Nabil Faruk.  
> Force field version: **ff_2.1** · Core language: **C++11** (fast, compiled) + **Python 3** (scripting, analysis) · File format: **HDF5** (a structured binary file format, like a database in a single file)

---

## Table of Contents

1. [What Is This?](#1-what-is-this)
2. [Repository Layout](#2-repository-layout)
3. [Three-Layer Architecture](#3-three-layer-architecture)
4. [The C++ Engine — DerivEngine](#4-the-c-engine--derivengine)
   - [Node Types](#node-types)
   - [The Computation Graph](#the-computation-graph)
   - [Execution Order](#execution-order)
   - [Node Registration](#node-registration)
   - [Built-in Node Catalogue](#built-in-node-catalogue)
   - [The C API](#the-c-api-engine_c_libraryh)
5. [The Simulation Loop](#5-the-simulation-loop-maincpp)
   - [Startup Sequence](#startup-sequence)
   - [The Main Loop](#the-main-loop)
   - [Replica Exchange](#replica-exchange)
   - [Integrators](#integrators)
   - [Thermostat](#thermostat)
6. [The Python Layer](#6-the-python-layer)
   - [upside_config.py](#upside_configpy--system-builder)
   - [upside_nodes.py](#upside_nodespy--node-builder-library)
   - [upside_engine.py](#upside_enginepy--python-upside-class)
   - [advanced_config.py](#advanced_configpy--restraints-and-special-forces)
7. [The HDF5 Contract](#7-the-hdf5-contract)
8. [The Force Field (ff_2.1)](#8-the-force-field-ff_21)
9. [Two Build Targets, One Codebase](#9-two-build-targets-one-codebase)
10. [End-to-End Data Flow](#10-end-to-end-data-flow)
11. [Tech Stack](#11-tech-stack)
12. [Key Design Decisions](#12-key-design-decisions)
13. [Upside2 vs. Standard MD Codes](#13-upside2-vs-standard-md-codes)
14. [How to Actually Run Simulations](#14-how-to-actually-run-simulations)
15. [Notes for This Checkout](#15-notes-for-this-checkout)

---

## 1. What Is This?

### Background: what is molecular dynamics?

Molecular dynamics (MD) is a computer simulation technique that models how atoms and molecules move over time. You start with a 3D structure, give every atom an initial velocity, and then repeatedly calculate the forces between atoms and update their positions — like running physics in a video game, but for molecules. The result is a **trajectory**: a movie of the molecule wiggling, folding, stretching, or falling apart.

The problem is that proteins have thousands of atoms, and the forces need to be recalculated millions of times per second of simulated time. A typical protein folding event takes microseconds to milliseconds in the real world, but the simulation time step is femtoseconds (10⁻¹⁵ seconds) — so you need to run billions of steps to observe folding. This is why MD is computationally expensive.

### What Upside2 does differently: coarse-graining

**Upside2 MD** is a **coarse-grained** simulator, meaning it deliberately discards atomic-level detail in exchange for speed. Rather than modelling every single atom in a protein, it represents each **amino acid residue** (the repeating chemical unit that proteins are built from — there are 20 types, and a typical protein has 100–500 of them) using only 3–4 "bead" positions:

- **N** — the nitrogen atom at the start of each residue's backbone
- **Cα** (alpha carbon) — the central carbon of each residue
- **C** — the carbonyl carbon at the end of each residue's backbone
- One sidechain pseudo-atom representing the rest of the residue (its unique chemical group)


### How the physics works: statistical potentials

In standard MD, forces between atoms are modelled using classical physics equations — the Lennard-Jones potential (which handles van der Waals attraction and steric repulsion between atoms), Coulomb's law (electrostatics between charged atoms), and bonded terms for bond stretching and bending. This is accurate but slow.

Upside2 takes a completely different approach. Instead of computing physics from first principles, it uses **statistical potentials** — energy functions derived entirely from statistics over the **Protein Data Bank (PDB)**, which is a public database of ~200,000 experimentally determined protein structures. The idea is: if a particular geometric configuration appears frequently in known protein structures, it must be energetically favourable, so give it a low energy. If it's rare or never seen, give it a high energy.

This lets the simulation encode what we know about protein behaviour without deriving it from atomic interactions. The energy of any configuration is, roughly, `−log P(configuration)` relative to a reference state — negative log probability, so common configurations have low energy and rare ones have high energy.

### The central design novelty: a programmable potential graph

The most important technical feature of Upside2 is that the force field (the complete mathematical description of all the energies in the simulation) is not hardcoded. It is a **composable, differentiable computation graph** — a network of interconnected calculation steps, where each step takes some inputs, computes a value, and passes it to the next step.

**Python** writes the specification of this graph into an HDF5 file (a structured binary file format used in scientific computing — think of it like a ZIP file containing labeled arrays of numbers). **C++** reads that file, builds the graph in memory, and runs it at high speed. This separation means a researcher can add a completely new type of energy term — say, a force that pulls on a specific part of the protein — by writing a few lines of Python, without touching or recompiling any C++ code.

The graph also supports **automatic differentiation** — the ability to automatically compute forces (the derivative of energy with respect to position) without manually deriving any formulas. This is the same mathematical technique used in neural network training (backpropagation), applied here to molecular simulation.

---

## 2. Repository Layout

```
upside2-md/
├── src/                    C++ engine — the compiled simulation executable and shared library
│   ├── main.cpp            Entry point: simulation loop, replica exchange, command-line parsing
│   ├── deriv_engine.h/.cpp The computation graph engine (DerivEngine), all node types, integrator
│   ├── engine_c_library.h  The C-language interface exposed by libupside.so (callable from Python)
│   ├── thermostat.h        Temperature control — Ornstein-Uhlenbeck (Langevin) thermostat
│   ├── monte_carlo_sampler.h  Random backbone moves (pivot and jump) for enhanced sampling
│   ├── state_logger.h      Buffered HDF5 trajectory writer — saves simulation frames to disk
│   ├── h5_support.h        Helper functions for reading/writing HDF5 files from C++
│   ├── CMakeLists.txt      Build system config — dispatches to x86 or ARM variant
│   ├── CMakeLists_x86.txt  Builds upside binary + libupside.so (with gradient support)
│   └── CMakeLists_arm.txt  ARM/Apple Silicon variant (uses sse2neon for SIMD compatibility)
│
├── py/                     Python library — everything above the raw simulation engine
│   ├── upside_config.py    Main system builder — takes a PDB file → writes a .up HDF5 config
│   ├── upside_nodes.py     Library of functions, each adding one energy term to the HDF5 config
│   ├── upside_engine.py    Python interface to libupside.so — lets Python call C++ functions
│   ├── advanced_config.py  Advanced restraints — pulling forces, RMSD anchoring, walls, membranes
│   ├── run_upside.py       Job orchestration helpers for running many simulations
│   ├── PDB_to_initial_structure.py  Parses a PDB structure file → extracts sequence and coordinates
│   ├── mdtraj_upside.py    Connects Upside trajectories to MDTraj (a trajectory analysis library)
│   └── tensorflow_upside.py  Optional path: use TensorFlow + MPI for large-scale force-field training
│
├── parameters/
│   └── ff_2.1/             Force-field data files — the statistical tables the simulation reads
│       ├── sheet/          β-sheet (a type of protein secondary structure) potential parameters
│       └── bb_env.dat      Backbone environment statistics (how buried each residue type tends to be)
│
├── obj/                    Build output directory (compiled binaries land here after install.sh)
├── cmake/                  CMake helper — FindEigen3.cmake locates the Eigen linear algebra library
├── example/                ~10 worked example scenarios (folding, replica exchange, pulling, …)
├── tutorial/               Smaller tutorials with run.py scripts + example PDB files
├── start/                  Turnkey workflow scripts for common simulation types
├── web/                    Static HTML/JS/CSS demo pages (no server, no backend — standalone)
├── .devcontainer/          Docker + conda environment for VS Code Dev Containers / GitHub Codespaces
├── install.sh              Build script — sets environment variables, compiles via CMake
├── README.md               Quick-start guide (Docker, Codespaces, start/ scripts)
├── Release_note            Changelog listing what changed between Upside versions
└── Doxyfile                Configuration for Doxygen, a tool that auto-generates C++ API documentation
```

---

## 3. Three-Layer Architecture

The entire system is built around a clean separation between three layers. Each layer can be changed independently as long as the shared file format (HDF5) stays compatible between them.

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 3 — Python (py/)                                     │
│  Prepares structures, builds energy terms, runs jobs,       │
│  analyses results, and trains force-field parameters        │
│  Communicates with C++ only through the HDF5 file          │
└────────────────────────┬────────────────────────────────────┘
                         │ writes / reads HDF5 files
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 2 — HDF5 Contract (*.up files)                       │
│  /input/pos          — starting 3D atom coordinates        │
│  /input/sequence     — amino acid type per atom             │
│  /input/potential/*  — the computation graph specification  │
│  /output/*           — trajectory frames, energies, etc.   │
└────────────────────────┬────────────────────────────────────┘
                         │ reads at startup, writes trajectory
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1 — C++ Engine (src/)                                │
│  Builds and evaluates the computation graph, moves atoms,   │
│  controls temperature, handles replica exchange,            │
│  and writes output frames to the HDF5 file                 │
└─────────────────────────────────────────────────────────────┘
```

**Why use HDF5 as the only interface?** HDF5 (Hierarchical Data Format version 5) is a binary file format that stores arrays of numbers in a structured, labeled hierarchy — like a file system inside a file. Using it as the interface means: the simulation specification is fully self-contained and reproducible. One `.up` file holds everything needed to run, restart, or audit a simulation, plus all the output it ever produced. Python and C++ can evolve completely independently as long as they agree on the file schema.

---

## 4. The C++ Engine — DerivEngine

### Node Types

The C++ engine is built around a **computation graph** — a network of interconnected calculation units called **nodes**, where each node takes the output of earlier nodes as its input and produces a new output. Think of it like a flowchart or a circuit diagram, where data flows in one direction from raw atom positions toward a final energy value. (The technical term for this kind of one-directional network is a **directed acyclic graph**, or DAG — "acyclic" meaning there are no loops.)

Every node in the graph inherits from a base class called `DerivComputation` and must implement two methods:

```cpp
// Forward pass: read this node's inputs and compute its output
virtual void compute_value(ComputeMode mode) = 0;

// Backward pass: given how much the total energy depends on this node's output,
// figure out how much it depends on each of this node's inputs
virtual void propagate_deriv() = 0;
```

This two-method structure implements **reverse-mode automatic differentiation** — the same mathematical technique used in neural network training (where it's called backpropagation). The idea is: once you've computed the total energy by running the graph forward, you can automatically compute the force on every atom by running the graph backward, propagating "how much did this value contribute to the final energy?" from the energy back to the positions. You never have to manually derive a force formula for any energy term — the graph computes it for you.

There are two concrete node types:

**`CoordNode`** — a node that transforms coordinates into new coordinates:
- `output` (a `VecArrayStorage` array) — the values this node computed (e.g., a list of distances, or a list of angles)
- `sens` (a `VecArrayStorage` array) — during the backward pass, this accumulates the incoming signal: "how much does the total energy depend on each of my output values?"
- `n_elem`, `elem_width` — the shape of the output (number of elements × dimensions per element)

**`PotentialNode`** — a node that consumes coordinates and outputs a single scalar energy value:
- `potential` (a `float`) — the energy this term contributes
- `propagate_deriv()` does nothing for these nodes — they are always the final leaves in the backward pass. The backward pass is seeded by giving each `PotentialNode` a starting sensitivity of 1.0 (meaning: each unit of this energy contributes one unit to the total).

The special **`Pos`** node (always the first node in the graph, `nodes[0]`) holds the raw 3D atom positions. After the full backward pass completes, its `sens` field accumulates the total force vector on every atom — the derivative of total energy with respect to each atom's x, y, and z coordinates.

### The Computation Graph

The `DerivEngine` class owns the entire graph as a list of `Node` objects. Each `Node` records:
- `name` — the HDF5 group name that specifies this node (used as the lookup key)
- `computation` — a pointer to the actual node object (the C++ class that does the math)
- `parents` / `children` — which other nodes feed into this one, and which nodes consume its output
- `germ_exec_level` / `deriv_exec_level` — topological heights used to determine the correct execution order

A complete energy + force calculation (one per MD time step) works like this:

```
compute(PotentialAndDerivMode)
  │
  ├── FORWARD PASS (evaluate nodes in dependency order, shallowest first):
  │     Pos:          positions already set by the integrator
  │     Dihedral:     reads atom positions → computes φ,ψ backbone torsion angles
  │     rama_map:     reads those angles → evaluates the 2D spline energy → stores potential
  │     hbond_energy: reads positions → computes H-bond geometry → stores potential
  │     ...           (all nodes evaluated in order)
  │
  └── BACKWARD PASS (propagate sensitivities in reverse order, deepest first):
        PotentialNodes seed their parent nodes with 1.0 × (how energy changes with their input)
        CoordNodes add to parent sensitivities: parent.sens += this.sens × (how my output
                                                                  changes with parent's output)
        ... continues until Pos.sens has accumulated ∂(total energy)/∂(each atom position)
            which is exactly the negative of the force on each atom
```

### Execution Order

When the simulation starts, `build_exec_levels()` assigns a topological height — essentially a "layer number" — to every node in the graph. Nodes at the same layer have no dependencies between them, meaning they can be calculated in parallel. The simulation uses **OpenMP** (a standard way to run C++ code across multiple CPU cores simultaneously) to parallelise nodes at the same layer. This is why Upside2 gets faster on machines with more CPU cores.

For the multi-step Verlet integrator (described later), `build_integrator_levels()` additionally partitions the graph into "slow" and "fast" sub-graphs, allowing different energy terms to be evaluated at different frequencies.

### Node Registration

When new C++ node types are added to the codebase, they register themselves into a global lookup table at **static initialisation time** — meaning the registration happens automatically when the program loads, before `main()` even runs:

```cpp
static RegisterNodeType<MyNewNode, 2> reg("MyNewNode");
// n_args = 2 means this node expects exactly 2 parent CoordNodes as input
```

This writes a factory function (a function that creates instances of the node) into a global map from name-prefix strings to creation functions. When the simulation starts and reads the HDF5 file, it looks up each group's name in this map, calls the factory to create the node object, connects it to its parents using the `arguments` attribute stored in the HDF5 group, and adds it to the graph. This is how the graph defined in Python/HDF5 becomes live C++ objects.

### Built-in Node Catalogue

| Node name | Type | Description |
|-----------|------|-------------|
| `Pos` | CoordNode | Root node — holds raw 3D atom positions; always the first node in the graph |
| `Distance3D` | CoordNode | Straight-line (Euclidean) distance between pairs of atoms |
| `Distance2D` | CoordNode | Distance measured only in 2 of the 3 spatial dimensions |
| `Distance1D` | CoordNode | Signed distance along one spatial axis |
| `Dihedral` | CoordNode | Torsion (dihedral) angle — the angle of rotation around a bond, defined by 4 atoms. Used for backbone φ (phi) and ψ (psi) angles |
| `Angle` | CoordNode | Bond angle — the angle formed at an atom between two bonds, defined by 3 atoms |
| `COMCoord` | CoordNode | Centre-of-mass position of a group of atoms |
| `Const3D` | CoordNode | A fixed constant coordinate that doesn't change — e.g. the centre of a membrane |
| `rama_map` | PotentialNode | Ramachandran potential — 2D spline energy from (φ, ψ) angles, per residue type |
| `hbond_energy` | PotentialNode | Geometry-dependent hydrogen bond energy |
| `rotamer` | PotentialNode | Sidechain rotamer (discrete side-chain conformation) preference conditioned on backbone angles |
| `environment` | PotentialNode | Residue burial / solvation — rewards hydrophobic residues for being buried |
| `Harmonic` | PotentialNode | Harmonic spring restraint: energy = ½k(x−x₀)². Pulls any coordinate toward a target value |
| `FlatBottom` | PotentialNode | Zero energy within a range [lo,hi], harmonic spring outside — a soft wall |
| `Linear` | PotentialNode | Constant-force pulling: energy = −F·x. Applies a steady directional force to any coordinate |
| `membrane_potential` | PotentialNode | Lipid bilayer slab energy for membrane protein simulations |
| `AFM` / `tension` | PotentialNode | Velocity-clamp pulling (like an atomic force microscope) or constant-tension pulling |
| `cavity_radial` / `spherical_well` | PotentialNode | Radial confinement potentials — keep the protein inside a sphere |

### The C API (`engine_c_library.h`)

When compiled as `libupside.so` (a **shared library** — a compiled code file that other programs can load and call at runtime), Upside2 exposes a minimal **C-language API** (a set of callable functions with a C-compatible interface). This makes the engine callable from virtually any programming language via **FFI** (Foreign Function Interface — a mechanism that lets one language call functions written in another). Python uses **ctypes**, which is Python's built-in library for loading and calling C functions from shared libraries without writing any glue code.

```c
// Create and destroy a simulation engine loaded from an HDF5 config file
DerivEngine* construct_deriv_engine(int n_atom, const char* potential_file, bool quiet);
void         free_deriv_engine(DerivEngine* engine);

// Run a forward pass (energy only) or forward+backward pass (energy + forces)
int evaluate_energy(float* energy, DerivEngine* engine, const float* pos);
int evaluate_deriv (float* deriv,  DerivEngine* engine, const float* pos);

// Read and write force-field parameters (for training/optimisation)
int set_param      (int n, const float* param, DerivEngine* engine, const char* node_name);
int get_param      (int n,       float* param, DerivEngine* engine, const char* node_name);
int get_param_deriv(int n,       float* deriv, DerivEngine* engine, const char* node_name);

// Inspect the internal state of any node in the graph
int get_output_dims(int* n_elem, int* elem_width, DerivEngine* engine, const char* node_name);
int get_output     (int n, float* output, DerivEngine* engine, const char* node_name);
int get_sens       (int n, float* output, DerivEngine* engine, const char* node_name);
int get_value_by_name(int n, float* output, DerivEngine* engine,
                      const char* node_name, const char* log_name);

// Utility functions for fitting and evaluating B-spline curves (used in force-field tables)
int clamped_spline_solve       (int N, float* coeff,  const float* values);
int clamped_spline_value       (int N, float* result, const float* coeff, int nx, float* x);
int get_clamped_value_and_deriv(int N, float* result, const float* coeff, int nx, float* x);
```

All functions return 0 on success and a non-zero error code on failure.

---

## 5. The Simulation Loop (`main.cpp`)

### Startup Sequence

The main entry point is `upside_main()`, which is called both when you run `obj/upside` from the command line and when Python calls it in-process via `in_process_upside()`. Before the simulation loop starts, it does:

1. **Parse command-line arguments** using TCLAP (a header-only C++ library for parsing command-line flags). There are ~25 named parameters including:
   - `--duration`, `--time-step`, `--frame-interval` — how long to run and how often to save frames
   - `--temperature` — thermostat temperature; comma-separated list for multi-replica runs
   - `--thermostat-interval`, `--thermostat-timescale` — how often and how strongly to apply the thermostat
   - `--replica-interval`, `--swap-set` — parameters for replica exchange (explained below)
   - `--anneal-factor`, `--anneal-start`, `--anneal-end` — simulated annealing schedule
   - `--integrator` (`v` = standard Verlet, `mv` = multi-step Verlet), `--inner-step` — which integration algorithm to use
   - `--monte-carlo-interval` — how often to attempt Monte Carlo backbone moves
   - `--log-level` (`basic`, `detailed`, `extensive`) — how much data to save per frame
   - `--input`/`--output` — separate HDF5 files for input positions and output trajectory, or in-place (same `.up` file)
   - `--record-momentum`, `--restart-using-momentum` — for exactly reproducible restarts
   - `--disable-recentering`, `--disable-z-recentering` — controls whether the protein is re-centred at each frame

2. **Initialise each system** (one system per config file, wrapped in an OpenMP critical section to prevent parallel file I/O conflicts):
   - Open the `.up` HDF5 config file
   - Call `initialize_engine_from_hdf5()` which reads the `/input/potential/` tree and builds the `DerivEngine` graph
   - Load the starting atom positions from `/input/pos` into the graph's `Pos` node
   - Create an `OrnsteinUhlenbeckThermostat` (explained below) with a unique random seed per system
   - Initialise all atom momenta (velocities × mass) to zero, then thermalise them (randomise them to match the target temperature); or reload saved momenta from a previous run
   - Register data loggers — callbacks that will write position, kinetic energy, potential energy, and temperature to HDF5 at each frame interval
   - Check for incompatible flag combinations (e.g. z-axis re-centering is not allowed with membrane potentials, since the membrane position depends on z)

3. **Set up replica exchange** if `--replica-interval > 0` (explained below)

4. **Install signal handlers** — installs handlers for SIGINT (Ctrl-C) and SIGTERM (kill signal from the OS or a cluster scheduler). These handlers only set a single flag variable; they don't do any real work. A **RAII** (Resource Acquisition Is Initialisation) wrapper called `SignalHandlerHandler` ensures that the original signal handlers are automatically restored when the simulation ends, which is important when running Upside in-process from Python (so Python's own Ctrl-C handling works again afterward).

### The Main Loop

```
for each time step nr (OpenMP runs all replicas in parallel):
  ├── if (nr % mc_interval == 0):
  │     Execute Monte Carlo backbone moves (pivot and jump)
  │     These make large random changes to the backbone to help escape
  │     local energy minima that gradient-based dynamics might get stuck in
  │
  ├── if (nr % frame_interval == 0):
  │     Re-centre the protein at the origin (optionally xy-only for membrane sims)
  │     engine.compute(PotentialAndDerivMode) — run forward + backward pass
  │     logger.collect_samples() — write this frame to the HDF5 output buffer
  │     Print progress to the console: time, temperature, H-bond count, Rg (radius of gyration,
  │     a measure of how compact the protein is), potential energy
  │
  ├── if (nr % thermostat_interval == 0):
  │     If simulated annealing is on, update the target temperature
  │     thermostat.apply(mom, n_atom) — apply random kicks to momenta to
  │     maintain the target temperature
  │
  └── engine.integration_cycle(mom, dt) — move all atoms one time step forward

(back in serial, every replica_interval steps):
  replex.attempt_swaps(...) — try to swap conformations between replicas
```

### Replica Exchange

**Replica exchange** (also called parallel tempering) is a technique for exploring protein conformational space more efficiently than a single long simulation. The idea: run many identical copies of the same protein simultaneously, each at a different temperature. At regular intervals, propose swapping the conformations (atom positions) between two adjacent-temperature copies and accept or reject the swap using a probabilistic criterion. The hot copies explore broadly (they have enough thermal energy to escape local traps); the cold copies settle into low-energy states. By occasionally swapping, the cold copies benefit from the exploration done by the hot ones.

In this codebase, the `ReplicaExchange` struct manages this. At each `replica_interval`, for each active pair `(sys1, sys2)`:

- **Criterion 0** (standard parallel tempering): Calculate the log-Boltzmann weight (`−β·E` where β = 1/temperature and E = energy) for both systems. Tentatively swap their coordinates. Recalculate. Accept the swap if the Boltzmann probability of the new arrangement is higher than the old one, or with probability `exp(Δlog P)` otherwise — this is the **Metropolis criterion**, a standard acceptance rule that ensures the simulation converges to the correct statistical ensemble.
- **Criterion 1** (asymmetric): Calculate weights only once and accept based on the energy difference directly.

Multiple swap-set groups stagger their attempts so that with two swap sets and `--replica-interval 5`, set-0 tries at t=5,15,25,… and set-1 at t=10,20,30,… . This doubles the effective exchange frequency without increasing the synchronisation cost.

### Integrators

The **integrator** is the algorithm that moves atoms from their current positions to their positions one time step later, given the forces (computed by the DerivEngine). There are two options:

**Velocity Verlet** (default, `--integrator v`): A standard 3-stage integration scheme used throughout classical MD:
1. Half-kick: update momenta by half a time step using current forces
2. Full step: update positions using the updated momenta
3. Recompute forces at the new positions
4. Second half-kick: finish updating momenta

This scheme is **symplectic** (it conserves a slightly modified total energy, preventing artificial energy drift over long simulations) and **time-reversible** (running the simulation backward gives the exact same trajectory). Default time step is 0.009 Upside reduced units, roughly equivalent to ~50 femtoseconds for typical proteins.

**Multi-step Verlet** (`--integrator mv`): A **RESPA-style** integrator, where RESPA stands for "reference system propagator algorithm." The idea is that different forces in the system change at different speeds — bonded terms (bond lengths, angles) fluctuate quickly, while non-bonded terms (burial, electrostatics) change slowly. The multi-step Verlet evaluates slow outer forces once per outer step and fast inner forces `inner_step` times (default 3) per outer step. This means you can use a larger effective time step for the cheap-to-evaluate slow forces without destabilising the simulation. The DerivEngine graph is partitioned into slow and fast sub-graphs at startup via `build_integrator_levels()`.

### Thermostat

Real proteins exist in solution at body temperature. An MD simulation in vacuum has no way to regulate its temperature — energy can accumulate or be lost. A **thermostat** is a simulation technique that couples the system to a virtual heat bath at a target temperature `T`.

Upside2 uses an **Ornstein-Uhlenbeck (Langevin) thermostat** (also called a stochastic thermostat). At each `thermostat_interval`, it modifies the atomic momenta (velocities) by:
1. Multiplying them by a friction factor `α < 1` (slightly slowing everything down)
2. Adding random Gaussian noise with a strength set by `σ` (injecting random thermal energy)

The balance between friction and noise is set by the `thermostat_timescale` parameter (default 5 time units) and the target temperature. If the system gets too hot, friction wins; if too cold, noise wins. Over time the system equilibrates to the target temperature.

**Simulated annealing** gradually lowers the temperature during the simulation to help the protein settle into its lowest-energy configuration. The temperature schedule uses a sqrt-interpolation:
```
T(t) = ( √T₀ · (1 − f) + √T₁ · f )²
```
where `f = (t − anneal_start) / anneal_duration` and T₀, T₁ are the start and end temperatures. The square-root form spaces temperatures more densely at low values, where the protein's fluctuations are small and the energy landscape is more sensitive to small temperature changes. This works better than a simple linear ramp.

---

## 6. The Python Layer

### `upside_config.py` — System Builder

This is the largest Python file (~2500 lines) and the primary user-facing interface for setting up a simulation. It takes a protein structure and produces a complete, runnable `.up` HDF5 config. Its key responsibilities:

- **Structure parsing**: Reads the backbone heavy-atom coordinates (N, Cα, C) for each residue from the output of `PDB_to_initial_structure.py`. Handles proteins with multiple chains (separate polypeptide chains in the same structure) — chain breaks are detected and encoded so that energy terms that should only apply within a chain don't accidentally span chains. Cis-proline (`CPR` — a rare variant of the amino acid proline with an unusual backbone geometry) is distinguished from trans-proline (`PRO`).

- **Initial structure writing**: Writes `/input/pos` (a 3D array of shape `n_atom × 3 × 1`, stored as 32-bit floats) and `/input/sequence` (the amino acid type of each atom). The trailing `1` dimension allows the schema to support multi-copy configs for enhanced sampling methods.

- **Backbone geometry nodes**: Calls functions in `upside_nodes.py` to write the chain of HDF5 groups representing the backbone energy terms: `Pos → Dihedral_phi + Dihedral_psi → rama_map`, plus additional nodes for virtual bond length and angle geometry that keeps the coarse-grained chain geometrically reasonable.

- **Force-field table generation**: Reads the binary parameter files from `parameters/ff_2.1/` and assembles per-residue arrays of B-spline coefficients (compact mathematical representations of smooth energy curves, described in Section 8). For example, for the Ramachandran potential it creates an array of shape `(n_residue, n_rama_type, n_phi_knots, n_psi_knots)` and writes it into the `rama_map` HDF5 group.

- **Sidechain / rotamer**: The sidechain model uses a probabilistic graph over discrete **rotamer states** — the small number of preferred side-chain conformations that each amino acid tends to adopt. `upside_config.py` reads the rotamer library from `sidechain.h5`, builds lists of which residues are close enough to interact, and writes the full specification into HDF5.

- **Environment / burial**: Reads `bb_env.dat` and writes per-residue-type burial statistics. The C++ engine uses this to compute, at each time step, how many neighbours each residue has (a measure of how buried or surface-exposed it is), and then looks up the associated energy cost.

### `upside_nodes.py` — Node Builder Library

Each function in this file corresponds to one C++ node type. The pattern is always the same: create an HDF5 group under `/input/potential/` with a name like `Distance3D_<your_name>`, set a `arguments` attribute on the group that names its parent nodes, write any parameter arrays as datasets, and return the group name so it can be referenced by downstream nodes.

| Python function | HDF5 group name prefix | What it does |
|-----------------|------------------------|--------------|
| `DistanceCoord()` | `Distance3D_` | Euclidean distance between pairs of atoms. Takes atom id pairs as input. |
| `Distance2DCoord()` | `Distance2D_` | Distance measured in 2 user-specified dimensions (e.g. just x and y, ignoring z) |
| `Distance1DCoord()` | `Distance1D_` | Signed projection of a pairwise distance onto one spatial axis |
| `TorsionCoord()` | `Dihedral_` | Dihedral (torsion) angle from 4 atom ids. Used for backbone φ and ψ angles. |
| `AngleCoord()` | `Angle_` | Bond angle from 3 atom ids |
| `COMCoord()` | `COMCoord_` | Centre-of-mass of a group of atoms, optionally projected to 1, 2, or 3 dimensions |
| `HarmonicPotential()` | `Harmonic_` | Harmonic spring: ½k(x−x₀)². Pulls any coordinate toward a target value. |
| `FlatBottomPotential()` | `FlatBottom_` | Zero energy within a range [lo, hi]; harmonic spring outside — a "soft wall" |
| `LinearPotential()` | `Linear_` | Constant-force pull: energy = −F·x. Force does not depend on position. |
| `RMSDCoord()` | `RMSD_` | RMSD (root-mean-square deviation) of atom positions relative to a reference structure — a measure of how far the protein has drifted from a reference |

### `upside_engine.py` — Python `Upside` Class

This file loads `obj/libupside.so` (the shared library version of the C++ engine) at import time using **ctypes** — Python's built-in mechanism for calling C functions from a compiled `.so`/`.dll` file without writing any C code. It registers every C function's argument types and return type so Python can call them safely.

The `Upside` Python class wraps the engine in a clean interface:

```python
engine = Upside('protein.up')  # load the HDF5 config, build the C++ graph

# Compute the total potential energy for a given set of atom positions
E = engine.energy(pos)         # pos: NumPy array of shape (n_atom, 3), dtype float32
                                # returns a single float — the total energy

# Compute the force on every atom (= −gradient of energy w.r.t. position)
F = engine.deriv(pos)          # returns NumPy array of shape (n_atom, 3)

# Force-field parameter access (used during training)
theta = engine.get_param(shape, 'rama_map')          # read current spline coefficients
engine.set_param(theta_new, 'rama_map')              # overwrite them
grad  = engine.get_param_deriv(shape, 'rama_map')    # ∂(energy)/∂(spline coefficients)
                                                      # only available in PARAM_DERIV build

# Inspect any node's computed values
output = engine.get_output('Dihedral_phi')   # read the forward-pass output of the φ-angle node
sens   = engine.get_sens('Dihedral_phi')     # read the backward-pass sensitivity signal
```

`in_process_upside(args)` calls `upside_main()` directly via ctypes with the same arguments you'd pass on the command line, running a complete simulation inside the Python process without spawning a subprocess.

`freeze_nodes()` is a training utility: it evaluates the engine on a starting structure, saves the output of specified nodes (e.g. an expensive rotamer computation) as fixed constant arrays, and rewrites the HDF5 config replacing those nodes with `constant_*` nodes that just return the saved values. This lets you "bake in" expensive intermediate computations that won't change during a training run, dramatically speeding up gradient calculations.

### `advanced_config.py` — Restraints and Special Forces

Handles simulation setups that go beyond the basic force field:
- **RMSD restraints** — a harmonic energy penalty proportional to how much the protein has moved from a reference structure. Used to keep the protein near a target conformation.
- **Pulling simulations** — sets up velocity-clamp or constant-force pulling using the `AFM`, `tension`, or `Linear` PotentialNodes. The `Linear` node applies a constant directional force on a group of atoms' centre-of-mass, not just a single atom.
- **Rotation restraints** — applies a torque to a group of atoms, restraining rotation around an axis.
- **Wall potentials** — `FlatBottom` nodes that confine any coordinate to a half-space (one side of a plane).
- **Membrane setup** — writes the slab geometry, curvature radius, and insertion restraints needed for membrane protein simulations.

---

## 7. The HDF5 Contract

The `.up` file is the complete, standalone interface between Python and C++. Its internal structure:

```
/                                                    ← root of the HDF5 file
├── input/
│   ├── pos            float32[n_atom, 3, 1]        starting x,y,z coordinates for every atom
│   ├── sequence       str[n_atom]                  amino acid type label for every atom
│   ├── mom            float32[n_atom, 3, 1]        (optional) starting momenta for exact restart
│   └── potential/                                  ← the computation graph specification
│       ├── pos                                     always present — the root Pos node
│       ├── Dihedral_phi                            a torsion-angle node for φ backbone angles
│       │     arguments: ['pos']                   ← this node reads from 'pos'
│       │     id:        int32[n_phi, 4]            ← the 4 atom ids defining each φ angle
│       ├── Dihedral_psi                            a torsion-angle node for ψ backbone angles
│       │     arguments: ['pos']
│       │     id:        int32[n_psi, 4]
│       ├── rama_map                                the Ramachandran potential node
│       │     arguments: ['Dihedral_phi',           ← reads from both angle nodes
│       │                 'Dihedral_psi']
│       │     coeff:     float32[n_residue,         ← B-spline coefficients per residue type
│       │                        n_rama_type,
│       │                        n_phi_knots,
│       │                        n_psi_knots]
│       ├── hbond_energy
│       │     arguments: ['pos']
│       ├── rotamer
│       │     arguments: ['pos', 'Dihedral_phi', 'Dihedral_psi']
│       └── ... (as many nodes as the force field or restraints require)
│
└── output/                                         ← written during and after simulation
    ├── pos            float32[n_frame, n_atom, 3]  atom positions at each saved frame
    ├── potential      float64[n_frame, 1]           total potential energy at each frame
    ├── kinetic        float64[n_frame, 1]           total kinetic energy at each frame
    ├── time           float64[n_frame]              simulation time at each frame
    ├── temperature    float64[n_frame, 1]           thermostat temperature at each frame
    ├── replica_index  int32[n_frame, 1]             which replica this frame came from (replica exchange only)
    └── invocation     str                           the exact command used to run this simulation
```

Every group under `/input/potential/` follows the same three-part convention:
- The **group name** determines which C++ node class handles it — it is looked up in the node factory map at startup
- The **`arguments` attribute** (an array of byte-strings) names the parent `CoordNode`(s) by their group names, defining the data-flow edges in the graph
- **Datasets within the group** (like `id`, `coeff`, etc.) are the constructor parameters that the C++ node reads to initialise itself

---

## 8. The Force Field (ff_2.1)

A **force field** is the complete set of mathematical rules that determine the energy of any configuration of atoms. In Upside2, all energy terms are **statistical potentials** — the energy `E = −kT log P(feature)` where `P(feature)` is the probability of observing that feature in high-resolution structures from the Protein Data Bank. Common configurations in real proteins have high probability → low energy. Rare or impossible configurations have low probability → high energy.

### Ramachandran Potential

**What it models:** Each amino acid residue has two backbone torsion angles, φ (phi) and ψ (psi), which define how the backbone chain rotates at that residue. The vast majority of possible (φ, ψ) combinations are geometrically impossible due to steric clashes (atoms colliding), so real proteins cluster into a few allowed regions of (φ, ψ) space — α-helical, β-strand, and turn conformations — known as the Ramachandran map.

**How it's encoded:** A 2D cubic B-spline (a smooth mathematical curve fit to data, described below) over the full (φ, ψ) angular space, fit separately for ~20 groups of amino acid types. The B-spline represents `−log P(φ,ψ)` for each residue type. The Ramachandran potential is the primary short-range backbone term — it alone enforces the correct secondary structure preferences (α-helix vs. β-strand).

**In the graph:** `Pos → Dihedral_phi + Dihedral_psi → rama_map`  
Parameter file: `parameters/ff_2.1/rama.dat`

### Hydrogen Bond Potential

**What it models:** A backbone **hydrogen bond** forms when a N−H group on one residue donates its hydrogen to the C=O (carbonyl) oxygen of another residue. These bonds are the dominant stabilising force for α-helices (where residue i bonds to residue i+4) and β-sheets (where bonds form between parallel or antiparallel strands). Without this term, the simulation would not form secondary structure.

**How it's encoded:** Energy depends on three geometric descriptors: the H···O distance, the N−H···O angle (the more linear the better — ideal ≈180°), and the H···O=C angle (ideal ≈120° due to the geometry of the sp² carbonyl). Each descriptor is encoded as a 1D B-spline. Their product gives a geometry-dependent energy that is near zero only when all three criteria are simultaneously satisfied — a genuine H-bond.

Parameter file: `parameters/ff_2.1/hbond.h5`

### Rotamer Potential

**What it models:** Sidechain conformation. Each amino acid's sidechain (the unique chemical group that distinguishes one amino acid from another) can rotate around its bonds, but strongly prefers a small number of discrete **rotamer states** — the low-energy configurations seen frequently in PDB structures. The rotamer potential captures both the backbone-dependent preference for each rotamer state and the pairwise steric and chemical interactions between neighbouring sidechains.

**How it's encoded:** A probabilistic graphical model (similar to a Boltzmann machine) over discrete rotamer states. Each residue has a rotamer prior probability conditioned on its (φ, ψ) angles, plus pairwise interaction terms between neighbouring residues. At each energy evaluation, a **belief propagation** algorithm (a standard message-passing algorithm for computing marginal probabilities in graphical models) runs over the residue connectivity graph to compute the partition function and the total rotamer energy.

Parameter file: `parameters/ff_2.1/sidechain.h5`

### Environment / Burial Potential

**What it models:** The hydrophobic effect — the tendency of water-fearing (hydrophobic) residues to cluster in the protein interior, away from water, while water-loving (hydrophilic) and charged residues prefer the surface. This is the primary driver of **hydrophobic collapse** — the initial compaction that starts the folding process.

**How it's encoded:** For each residue, the simulation counts how many Cβ atoms (the first sidechain carbon, present in all amino acids except glycine) are within a cutoff radius. This count is the **burial** number. A 1D B-spline maps burial count to energy, conditioned on residue type. Hydrophobic residues (phenylalanine, leucine, isoleucine, valine, etc.) have a negative-slope energy curve — more burial = lower energy. Charged residues (aspartate, glutamate, lysine, arginine) have a positive-slope curve — more burial = higher energy.

Parameter file: `parameters/ff_2.1/bb_env.dat`

### Sheet Potential

**What it models:** Additional β-sheet-specific geometry — the precise spacing and hydrogen-bonding geometry of parallel and antiparallel strands.

Parameter files: `parameters/ff_2.1/sheet/`

### Membrane Potential

**What it models:** The free energy of inserting a protein residue into a lipid bilayer membrane. Different residue types have very different preferences: hydrophobic residues are stabilised in the membrane core; charged residues are strongly penalised.

**How it's encoded:** A slab potential — each residue pays an insertion energy that depends on its z-coordinate (depth relative to the membrane centre) and its residue type. A separate `CurvatureChange` Monte Carlo mover in `main.cpp` proposes moves that change the membrane curvature radius (how bent the membrane is), accepted/rejected by the same Metropolis criterion as regular MC moves. Requires `--disable-z-recentering` at runtime because z-coordinate matters absolutely here.

### B-Splines

All the energy curves described above are represented as **clamped cubic B-splines** — a class of smooth mathematical curves that:
- Are smooth everywhere (**C² continuity** — continuous first and second derivatives), which means the forces derived from them are also smooth and continuous
- Have a compact parameterisation — a 1D angular term covering the full −180° to +180° range needs only ~30 **knot** values (control points) rather than a lookup table with thousands of entries
- Support analytic first derivatives — `get_clamped_value_and_deriv()` returns both the energy value and its derivative (which is the force) in a single pass
- Are differentiable with respect to their own parameters — `get_clamped_coeff_deriv()` gives ∂E/∂(spline coefficients), enabling gradient-based optimisation of the force-field parameters themselves

Python utilities in `upside_engine.py` expose `clamped_spline_solve()` (fit a new spline to a set of measured energy values) and `clamped_spline_value()` (evaluate a spline at arbitrary x) for use in notebooks and training scripts.

---

## 9. Two Build Targets, One Codebase

CMake (the build system) compiles the exact same C++ source files twice with different compilation flags:

| Target | Compilation flag | Purpose |
|--------|-----------------|---------|
| `obj/upside` | *(no `PARAM_DERIV`)* | Standalone MD executable. Maximum speed. No overhead for storing or computing parameter gradients. Used for all production simulations. |
| `obj/libupside.so` | `-DPARAM_DERIV` | Shared library. Activates the `get_param_deriv()` method on every node. Used by Python for interactive analysis and force-field training. |

When `PARAM_DERIV` is defined during compilation, every node can additionally implement `get_param_deriv()` to return the derivative of the total energy with respect to that node's learnable parameters (e.g. the spline coefficients). This enables a complete **gradient descent** loop (an iterative optimisation algorithm that repeatedly nudges parameters in the direction that reduces the error) entirely from Python:

```python
engine = Upside('config.up')
for step in range(n_steps):
    E         = engine.energy(pos)                  # forward pass: compute energy
    dE_dpos   = engine.deriv(pos)                   # backward pass: compute forces
    dE_dtheta = engine.get_param_deriv(shape, node) # ∂E/∂θ: how does energy change with params?
    theta    -= lr * dE_dtheta                       # take a gradient step
    engine.set_param(theta, node)                    # update the C++ engine's parameters
```

This is how force-field parameters are optimised — by running many proteins, computing how the energy differs from what you'd expect, and adjusting the parameters to reduce that difference.

---

## 10. End-to-End Data Flow

```
1. INPUT PREPARATION
   ─────────────────
   PDB file (a text file describing a protein's 3D atomic structure, from the Protein Data Bank)
     │
     │ PDB_to_initial_structure.py
     │ Extracts the amino acid sequence (FASTA is the standard text format for sequences)
     │ and the 3D coordinates of each backbone atom
     ▼
   FASTA sequence + initial backbone atom coordinates (N, Cα, C per residue)
     │
     │ upside_config.py + upside_nodes.py
     │ Reads the sequence and coordinates, looks up force-field tables, and writes
     │ the full simulation specification into HDF5
     ▼
   protein.up  (a single HDF5 file containing everything)
     ├── /input/pos             — starting atom positions
     ├── /input/sequence        — amino acid labels
     └── /input/potential/*     — the full graph specification as HDF5 groups


2. SIMULATION
   ───────────
   protein.up
     │
     │ initialize_engine_from_hdf5()
     │ Reads every group in /input/potential/, creates C++ node objects,
     │ wires them together, and sorts them into execution order
     ▼
   DerivEngine graph in memory (C++ objects)
     │
     │ Main loop (OpenMP runs all replicas on separate CPU cores simultaneously)
     ▼
   Every step:  compute forces → move atoms (integration_cycle)
   Periodically: apply thermostat, attempt replica swaps, write frames to HDF5 buffer
     │
     │ H5Logger flushes the buffer to disk
     ▼
   protein.up /output/*
     ├── pos         — atom coordinates at each saved time point
     ├── potential   — total potential energy per frame
     ├── kinetic     — total kinetic energy per frame
     ├── time        — simulation time per frame
     └── temperature — thermostat temperature per frame


3. ANALYSIS
   ─────────
   protein.up /output/*
     │
     ├── mdtraj_upside.py     — RMSD (how far from a reference structure), contact maps, secondary structure
     ├── get_info_from_upside_traj.py — H-bond analysis, folding observables
     └── Jupyter + nglview    — interactive 3D structure and trajectory visualisation in a notebook
```

---

## 11. Tech Stack

| Component | Technology | Role |
|-----------|-----------|------|
| Core MD engine | C++11 | The compiled simulation — fast computation graph, integrator, file I/O, OpenMP parallelism |
| Linear algebra | Eigen3 | A C++ header-only library for vector and matrix math used throughout the potential calculations |
| Random numbers | Random123 | A counter-based pseudorandom number generator — produces reproducible random sequences from a seed |
| CLI parsing | TCLAP | Templatized C++ Command Line Argument Parser — parses all the `--flag value` arguments |
| File format | HDF5 + PyTables | HDF5 is the binary file format; PyTables is Python's interface to it |
| Python config | NumPy + SciPy | Standard Python scientific computing libraries for array math |
| Trajectory analysis | mdtraj + ProDy | Post-simulation analysis: RMSD, contacts, secondary structure |
| Visualisation | nglview + matplotlib | nglview renders 3D protein structures in Jupyter notebooks; matplotlib makes plots |
| Python–C bridge | ctypes | Python's built-in library for calling compiled C/C++ functions from `.so` files |
| Optional training | TensorFlow + mpi4py | TensorFlow for gradient-based optimisation; mpi4py for running across many machines simultaneously |
| Containers | Docker + conda | Docker packages the entire environment into a reproducible container; conda manages Python packages |
| SIMD on ARM | sse2neon | Translates Intel x86 SIMD (Single Instruction Multiple Data — processing many numbers at once) instructions to ARM NEON equivalents, enabling the same code to run on Apple Silicon |

---

## 12. Key Design Decisions

**HDF5 as the lingua franca.** The `.up` file is the only interface between Python and C++. The simulation spec is fully self-contained — one file contains everything needed to run, restart, or reproduce a simulation and all output it ever produced. Python and C++ can evolve independently.

**Autodiff graph authored in Python, evaluated in C++.** The potential is a composable DAG, not a hardcoded force field. Python defines new potentials by writing HDF5 groups via `upside_nodes.py`. C++ evaluates them with automatic reverse-mode differentiation. Adding a new restraint type is purely a Python operation if the underlying C++ node class already exists.

**`PARAM_DERIV` compile flag separates production from training.** `obj/upside` carries zero overhead from parameter gradient machinery. `obj/libupside.so` compiled with `-DPARAM_DERIV` activates full parameter gradient support. There's no performance cost for production simulations that don't need gradients.

**ctypes over pybind11.** pybind11 is a popular alternative for exposing C++ to Python that requires writing wrapper code. ctypes binds directly to the C API with zero additional compilation dependency — only the `.so` binary is needed at runtime. The tradeoff is a more verbose Python side, but the C API is simple enough that this is acceptable.

**Asynchronous replica exchange swap sets.** Multiple swap-set groups stagger their attempts. With two swap sets and `--replica-interval 5`, set-0 tries at t=5,15,25,… and set-1 at t=10,20,30,… . This doubles the effective exchange frequency for the same synchronisation cost — especially valuable for short training runs where exchange frequency matters.

**RAII signal handling for graceful termination.** The signal handler (called when the OS sends a kill signal) does only one thing: sets a flag variable. No memory allocation, no file I/O — this is required because signal handlers run in an interrupt context where almost no standard library functions are safe to call. `SignalHandlerHandler` (a RAII wrapper — a C++ pattern where cleanup happens automatically in the destructor) restores the original Python signal handlers when the simulation ends, so Ctrl-C works correctly afterward.

**Sqrt-interpolation annealing.** Linear temperature schedules don't work well because the protein's behaviour changes much more sensitively near low temperatures (where it's almost frozen) than near high temperatures. The schedule `T(t) = (√T₀·(1−f) + √T₁·f)²` spaces temperatures more densely at low values, giving empirically better coverage of the energy landscape.

---

## 13. Upside2 vs. Standard MD Codes

| Aspect | Standard MD (GROMACS, AMBER) | Upside2 |
|--------|------------------------------|---------|
| **Representation** | All-atom — every hydrogen, carbon, nitrogen, oxygen explicitly | Coarse-grained — ~3–4 beads per residue |
| **Force field** | Classical physics — Lennard-Jones van der Waals, Coulomb electrostatics, bonded terms | Statistical potentials derived from PDB structure distributions |
| **Potential definition** | Hard-coded mathematical formulas in C/Fortran/CUDA source files | A composable computation graph written in Python and evaluated in C++ |
| **Force computation** | Analytic gradient formulas written by hand for each term | Automatic reverse-mode differentiation through the graph — no manual derivation |
| **Parameter training** | Rare; typically requires modifying C/Fortran source and recompiling | First-class feature: `get_param_deriv()` + Python gradient loop |
| **Configuration format** | Text topology files + separate coordinate files | Single self-contained HDF5 `.up` file |
| **Accessible timescale** | ns–μs with large compute clusters | μs–ms on modest hardware |
| **Extensibility** | New energy term = modify and recompile C/Fortran/CUDA | New energy term = new Python function + HDF5 group (no recompilation) |

---

## 14. How to Actually Run Simulations

Upside2 is **not a web service** — it's a local simulation tool that runs on your own computer (or in a cloud development environment you control). The Dockerfile is for creating a reproducible development environment with all dependencies pre-installed, not for deploying a web app.

### Option 1: VS Code Dev Container (Recommended for most users)

This is the easiest way to get started. VS Code handles all the Docker complexity for you.

**Requirements:**
- Visual Studio Code (free, from https://code.visualstudio.com)
- Docker Desktop (free, from https://docker.com)
- The "Dev Containers" VS Code extension (`ms-vscode-remote.remote-containers`)

**Steps:**
1. Open this folder in VS Code
2. Click the green `><` icon in the bottom-left corner
3. Select "Reopen in Container"
4. Wait 5–10 minutes the first time (it's building the environment)
5. You're now inside a Linux container with everything installed

**If you're on Apple Silicon (M1/M2/M3/M4):** Before step 2, edit `.devcontainer/devcontainer.json` and change `"TARGETPLATFORM": "linux/amd64"` to `"TARGETPLATFORM": "linux/arm64"`.

### Option 2: GitHub Codespaces (Cloud-based, no local Docker needed)

If you don't want to install Docker locally, GitHub can run the container for you in the cloud.

1. Go to the repository on GitHub
2. Click the green "Code" button → "Codespaces" tab → "Create codespace on main"
3. Wait for it to build
4. You now have a VS Code instance in your browser with everything ready

This uses GitHub's free tier (60 hours/month for free accounts).

### Option 3: Docker directly (for scripting/automation)

```bash
# Pull the pre-built image
docker pull oliverkleinmann/upside2-md

# Or build from source
docker build -t upside2-md .

# Run interactively
docker run -it --rm -v "$(pwd)":/workspaces/upside2-md upside2-md bash
```

### Running Your First Simulation

Once you're inside the container (via any of the three options above), here's how to run a basic simulation:

**Example 1: Single-replica equilibrium simulation**
```bash
cd start

python Single_Replica.py \
  1dfn ../example/01.GettingStarted/pdb \
  my_first_sim 1e7 100 False 0.85 None
```

This runs a simulation of PDB structure `1dfn` (defensin, a small protein) for 10 million steps, saving a frame every 100 steps, at temperature 0.85 (reduced units). Output goes to `start/outputs/my_first_sim/`.

**Example 2: Pulling simulation (constant tension)**
```bash
cd start

python Pulling_Simulations.py \
  1dfn ../example/01.GettingStarted/pdb \
  my_pull_sim 1e7 100 tension False 0.85 None
```

Same protein, but now with a constant pulling force applied end-to-end. This is what you'd use for the cryptic epitope discovery workflow.

**What the arguments mean:**
| Argument | Example | Meaning |
|----------|---------|---------|
| `pdb_id` | `1dfn` | The PDB filename (without `.pdb` extension) |
| `pdb_dir` | `../example/01.GettingStarted/pdb` | Path to the folder containing the PDB file |
| `sim_id` | `my_first_sim` | A name you choose — output folder will be named this |
| `duration` | `1e7` | Number of simulation steps (10 million here) |
| `frame_interval` | `100` | Save a frame every N steps |
| `sim_type` | `tension` | For pulling sims: `tension` (constant force) or `velocity` (constant speed) |
| `continue_sim` | `False` | `True` to continue a previous run, `False` to start fresh |
| `temperature` | `0.85` | Thermostat temperature in reduced units (~room temp) |
| `restraints` | `None` | Optional restraint file, or `None` |

### Where Output Goes

All output is written to HDF5 files in `start/outputs/<sim_id>/`. You can analyse these with:

```python
import tables as tb

# Open the output file
with tb.open_file('start/outputs/my_first_sim/my_first_sim.up', 'r') as f:
    # Read trajectory positions (n_frames × n_atoms × 3)
    positions = f.root.output.pos[:]
    
    # Read potential energy per frame
    energy = f.root.output.potential[:]
    
    # Read simulation time per frame
    time = f.root.output.time[:]
    
    print(f"Trajectory has {len(time)} frames")
    print(f"Final energy: {energy[-1]}")
```

Or use MDTraj for more sophisticated analysis:
```python
import mdtraj as md
# (requires the mdtraj_upside.py utilities)
```

---

## 15. Notes for This Checkout

**Force field parameters are complete.** This repository contains all the parameter files needed for full simulations:
- `parameters/common/rama.dat` (35 MB) — Ramachandran backbone angle tables
- `parameters/ff_2.1/sidechain.h5` (1.2 MB) — rotamer library
- `parameters/ff_2.1/hbond.h5` — hydrogen bond geometry
- `parameters/ff_2.1/environment.h5` — burial/solvation potential
- `parameters/ff_2.1/membrane.h5` — membrane potential (for membrane protein sims)

**Build output.** The `obj/` directory may not contain compiled binaries until you build. The Dev Container runs the build automatically on first launch. If running manually, execute `bash install.sh` from the repository root.

**`web/` folder.** The `web/` directory contains static HTML/JS demo pages — these are standalone files you can open in a browser, not a deployed web service.

---

*Upside2 MD · Sosnick lab, University of Chicago · ff_2.1 · Python 3 / C++11 · HDF5*

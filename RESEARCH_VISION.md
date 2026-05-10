# Mechanobiology Research Vision
## Cryptic Epitopes, Targeted Fibrosis Therapy, and a New Experimental Platform

---

## Table of Contents

1. [The Core Hypothesis](#1-the-core-hypothesis)
2. [The Disease Context — Fibrosis](#2-the-disease-context--fibrosis)
3. [The Three-Step Pipeline](#3-the-three-step-pipeline)
4. [Step 1: Computational Pulling with Upside](#4-step-1-computational-pulling-with-upside)
   - [Why Upside Is the Right Tool](#why-upside-is-the-right-tool)
   - [What a Pulling Simulation Looks Like](#what-a-pulling-simulation-looks-like)
   - [Identifying Cryptic Epitopes from Trajectories](#identifying-cryptic-epitopes-from-trajectories)
   - [Force Unit Calibration](#force-unit-calibration)
5. [Step 2: AI-Driven Nanobody Design](#5-step-2-ai-driven-nanobody-design)
6. [Step 3: Experimental Validation](#6-step-3-experimental-validation)
   - [Why Optical Tweezers Alone Don't Scale](#why-optical-tweezers-alone-dont-scale)
   - [The Three Prototype Platforms](#the-three-prototype-platforms)
   - [The Centrifuge Platform in Detail](#the-centrifuge-platform-in-detail)
   - [The Fluorescent Binder Readout](#the-fluorescent-binder-readout)
7. [Connecting Computational and Experimental](#7-connecting-computational-and-experimental)
8. [The Broader Tool](#8-the-broader-tool)
9. [Immediate Next Steps](#9-immediate-next-steps)
10. [Open Questions and Gaps](#10-open-questions-and-gaps)

---

## 1. The Core Hypothesis

Most proteins in the body are not floating freely in solution — they are anchored at both ends, embedded in tissue, stretched between cells, or held under sustained mechanical tension. A protein under load adopts **conformational states** (three-dimensional shapes and configurations) that are fundamentally different from its resting, relaxed shape. Parts of the protein that are normally buried and inaccessible — folded into the protein interior where nothing from outside can reach them — become exposed when the protein is pulled or stretched.

These newly revealed surface regions are called **cryptic epitopes**: binding sites (locations on the protein surface where another molecule can dock or attach) that are hidden in the relaxed state and only appear under mechanical tension. The word "cryptic" means hidden; an "epitope" is any molecular surface feature that a binding partner — antibody, nanobody, drug molecule — can recognise and attach to.

A therapeutic molecule designed to bind a cryptic epitope would, by definition, only engage proteins that are currently under mechanical stress. It could not bind the same protein in its relaxed state, giving it a form of tissue-selectivity that conventional drug design cannot achieve.

The hypothesis driving this research:

> *Proteins under chronic mechanical tension in fibrotic (scarred) tissue display cryptic epitopes that are absent from the same proteins in healthy, unstressed tissue. These epitopes can be identified computationally by simulating mechanical pulling, targeted by AI-designed nanobodies (small, engineered antibody-like binding proteins), and validated by a high-throughput force-controlled binding assay — providing a platform for selective mechanotherapy: drugs that go to the site of mechanical disease.*

---

## 2. The Disease Context — Fibrosis

### What fibrosis is

Fibrosis is pathological scarring — the body's wound-healing response gone wrong. In a normal wound, cells temporarily deposit **extracellular matrix (ECM)** proteins — structural proteins that form the scaffolding between cells, holding tissues together — and then remodel and resolve them. In fibrosis, this process fails to resolve: ECM proteins keep accumulating, the tissue becomes stiff and disorganised, and normal function is lost. The result is effectively scar tissue in an organ that shouldn't have scar tissue.

Fibrosis is a feature of a remarkably wide spectrum of diseases:
- **Pulmonary fibrosis** — scarring of the lung (idiopathic pulmonary fibrosis, or IPF; also seen in long COVID)
- **Liver fibrosis / cirrhosis** — from chronic hepatitis, alcohol, non-alcoholic fatty liver disease
- **Cardiac fibrosis** — post-heart-attack scarring that reduces heart function
- **Renal fibrosis** — late-stage kidney disease
- **Systemic sclerosis** — an autoimmune condition causing widespread skin and visceral fibrosis

### The mechanical problem

The key insight is that elevated matrix stiffness directly causes the ECM proteins themselves — the structural proteins like **collagen I** (the most abundant protein in the human body, the primary structural component of connective tissue), **fibronectin** (a large adhesive protein that connects cells to the ECM), periostin, and tenascin-C — to experience forces far above their normal physiological range. Fibrotic tissue can be 10–100× stiffer than healthy tissue. As the tissue tightens around the embedded ECM proteins, those proteins get pulled and stretched. The forces on individual protein domains — individual folded units within the larger protein — scale accordingly.

### Why existing drugs fail and why this approach is different

The selectivity problem with ECM-targeted therapies is fundamental: collagen I is everywhere in the body — in skin, tendons, bone, cartilage, blood vessels, and every organ. An antibody or drug that binds collagen I in fibrotic lung will also bind it in all of those healthy tissues, causing **on-target off-disease toxicity** (the drug does exactly what it's supposed to do, just in the wrong places). This is a core reason why ECM-targeted drugs have largely failed clinically despite years of effort.

The mechanical biomarker solution: if a drug only binds collagen I when the protein is stretched — targeting a cryptic epitope that appears only above a certain force threshold, say 20 pN (piconewtons — explained below) — it will selectively accumulate in fibrotic tissue where that force is present, and leave healthy collagen in normal tissue completely untouched. The drug is intrinsically selective because the target itself only exists where the disease is. This is **mechanistic selectivity**: a drug that physically cannot bind its target in healthy tissue.

A **piconewton (pN)** is an extraordinarily small force — 10⁻¹² Newtons, roughly a trillion times smaller than the weight of a paperclip. It is nevertheless the relevant force scale for individual proteins: it takes ~5–100 pN to partially unfold a protein domain, and these are the forces that act on ECM proteins in fibrotic tissue.

---

## 3. The Three-Step Pipeline

```
STEP 1: Computational              STEP 2: AI Design              STEP 3: Experimental
────────────────────────────────  ───────────────────────────    ──────────────────────────────
Upside MD pulling simulations  →  RFdiffusion + ProteinMPNN  →  Force-controlled binding assay
at 5–50 pN equivalent force        AI tools design nanobody        on surface-immobilised protein
                                    binders for the exposed
                                    epitope surface
                                    
Identify which regions of the      Predict the 3D structure of     Validate force-dependent
protein unfold and what surfaces   the binder–epitope complex      binding with a fluorescent
become accessible at each force    and filter candidates before    readout at controlled pN
level                              synthesising anything           forces
```

Each step has a clear input and a clear output that feeds directly into the next step. The experimental platform (step 3) is the current bottleneck — steps 1 and 2 are computationally mature and can be done now.

---

## 4. Step 1: Computational Pulling with Upside

### Why Upside Is the Right Tool

The force range of interest (5–50 pN) corresponds to **domain-level partial unfolding events** — situations where one folded structural unit within a larger protein partially opens up and loses its normal shape, while the rest of the protein remains intact. These transitions happen on **microsecond-to-millisecond timescales** (a microsecond is 10⁻⁶ seconds; a millisecond is 10⁻³ seconds). This is completely inaccessible to standard all-atom MD simulation, which, even with enormous computational budgets, can only simulate a few microseconds for a small protein. Upside's coarse-grained model accesses these timescales routinely because:

- It represents each amino acid residue as ~4 beads rather than ~15–25 individual atoms, making each simulation step ~100× cheaper
- The statistical potentials it uses are smooth mathematical curves that are faster to evaluate than all-atom force field calculations
- It supports pulling simulations natively — `tension` and `AFM` modes are already built in to the codebase
- It can run hundreds of independent copies of the simulation simultaneously at different force values, which matches the ensemble approach of the centrifuge experimental platform

The coarse-grained representation is actually well-matched to the biological question being asked. The Ramachandran potential (which encodes how the backbone wants to fold) and the hydrogen bond potential (which holds secondary structure together) directly represent the stability of α-helices and β-sheets — so "which structural elements unfold and in what order as force increases" is exactly the question these potentials can answer.

### What a Pulling Simulation Looks Like

Upside already has this as a ready-to-use workflow via `start/Pulling_Simulations.py`:

```bash
python start/Pulling_Simulations.py \
    <pdb_id> <pdb_dir> <sim_id> \
    <duration> <frame_interval> \
    tension False <temperature> None
```

Two modes are directly relevant:

**Constant-tension mode** (`tension`): A fixed force is applied continuously along a defined axis — typically the vector from one end of the protein to the other. The protein sits under constant load, and you observe how it fluctuates and, eventually, how it unfolds. This is the direct computational analog of the centrifuge experiment: same geometry (anchored at one end, pulled from the other), same force type (constant, not velocity-dependent).

**Velocity-clamp mode** (`AFM`): One end is pulled at a constant velocity while the other end is held fixed. This generates a **force-extension curve** — a plot of how much force is required to extend the protein to a given length. This is the computational analog of atomic force microscopy (AFM, an instrument that uses a nano-scale cantilever tip to pull individual molecules). Useful for characterising the mechanical pathway of unfolding, but less directly comparable to the centrifuge assay.

Under the hood, `advanced_config.py` writes a `tension` or `AFM` **PotentialNode** (a computation-graph node that calculates an energy corresponding to the applied force) into the HDF5 config. The `Linear` node applies a constant directional force on a defined group of atoms' **centre-of-mass** (the average position of a group of atoms, weighted by mass) — it already supports pulling on an entire protein end rather than just a single atom, which is more physically realistic.

### Identifying Cryptic Epitopes from Trajectories

The HDF5 trajectory output (explained in the architecture document) gives you every saved frame of atomic positions at every force level. The analysis pipeline to find cryptic epitopes:

1. **Load the trajectory** using `mdtraj_upside.py`, which connects Upside's HDF5 output to MDTraj, a widely-used Python library for protein trajectory analysis.

2. **Identify unfolded regions**: Track which residues deviate from their **native Ramachandran basin** — the (φ,ψ) backbone torsion angle region expected for their secondary structure type. For example, a residue that was in an α-helix should have φ ≈ −60°, ψ ≈ −45°. If, under tension, it shifts to extended conformations (φ ≈ −120°, ψ ≈ +120°), it has unfolded. The `Dihedral` CoordNode logs backbone angles continuously in the simulation output, and the per-residue `rama_map` potential energy is accessible via `engine.get_output('rama_map')`.

3. **Track burial changes**: The `environment` PotentialNode computes a **burial score** for every residue at every time step — essentially, how many other residues are nearby. A residue that moves from high burial (deeply embedded, inaccessible) to low burial (surface-exposed) under tension is a candidate for cryptic epitope exposure. Accessible via `engine.get_output('environment')`.

4. **Cluster intermediate states**: Group trajectory frames by **RMSD** (root-mean-square deviation — the average distance between corresponding atoms when two structures are overlaid, a standard measure of structural similarity) or contact-map similarity (which pairs of residues are close to each other) using MDTraj. This identifies discrete, reproducible partially unfolded intermediate states. Each intermediate represents one candidate cryptic epitope conformation with a defined force threshold (the force at which it first appears).

5. **Extract representative structures**: For each intermediate, extract the backbone coordinates of the newly exposed region. Since Upside is coarse-grained (only N, Cα, C atoms), these must be **back-mapped** to all-atom detail before nanobody design — a standard procedure described below.

**Back-mapping to all-atom:** Coarse-grained MD tracks only the backbone scaffold, not the full atomic detail of each side chain. Back-mapping is the process of reconstructing the missing atoms from the backbone scaffold. Standard tools: **PULCHRA** reconstructs approximate side-chain positions from backbone coordinates based on common rotamer geometries; **SCWRL4** or **Modeller** then energy-minimises the side-chain orientations into realistic positions. The output is a full-atom PDB file (the standard format for protein 3D structures) of the cryptic epitope conformation, ready to input into the nanobody design pipeline.

### Force Unit Calibration

Upside uses **reduced units** — dimensionless internal numbers that make the simulation mathematics convenient, but that don't directly correspond to physical units like nanometres or piconewtons. The time step of 0.009 and temperature of ~0.85 are both dimensionless. Before making quantitative comparisons between a simulated force value and a real-world experimental pN value, you need a calibration factor.

The recommended approach: run Upside's velocity-clamp pulling mode on a protein whose mechanical unfolding force is already well-established from optical tweezer or AFM experiments in the literature. For example:
- **Fibronectin FN-III domain**: first unfolding events at ~90 pN at typical AFM pulling rates
- **Titin I27 domain**: ~200 pN

You run the same pull in Upside, identify where the same unfolding event occurs in the simulation, and divide: (real-world force in pN) / (Upside force constant that produced the same event) = the calibration factor. From then on, multiplying any Upside force value by this factor gives pN.

---

## 5. Step 2: AI-Driven Nanobody Design

Once you have an all-atom structure of a cryptic epitope conformation (from step 1 + back-mapping), the current AI protein design pipeline can produce **nanobody** (a class of small, single-domain antibody-like binding protein derived from camelid antibodies — llamas and camels — that is roughly 1/10th the size of a conventional antibody, making it easier to engineer and express) binders computationally.

A **nanobody** is about 125 amino acids long. It has a scaffold structure that holds three hypervariable loops (called CDRs — Complementarity Determining Regions) that can take many shapes, and the CDR shapes determine what surface the nanobody binds to. AI tools can now design CDR sequences that will fold into a shape complementary to a specific target surface.

This step uses tools external to the Upside codebase but operates on standard PDB input files that the Upside analysis pipeline generates.

**Recommended pipeline:**

1. **RFdiffusion** (Baker lab at the University of Washington, 2023) — a **diffusion model** (an AI architecture that has learned to generate protein structures by learning to reverse a process of gradually adding noise; the same mathematical framework used by image-generation AI like Stable Diffusion, but for 3D protein backbones). You specify the cryptic epitope surface as the target; RFdiffusion generates diverse candidate binder backbone scaffolds that should dock to it.

2. **ProteinMPNN** — an **inverse folding model** (an AI that has learned to go backwards from a 3D backbone geometry to the amino acid sequence most likely to fold into it). It takes the backbone scaffolds from RFdiffusion and outputs amino acid sequences that will fold into those scaffolds and have surface chemistry complementary to the epitope.

3. **AlphaFold-Multimer or Chai-1** — **structure prediction** tools that predict the 3D structure of a protein complex. Here, you use them to predict the structure of the nanobody–epitope complex (binder + target protein fragment docked together). The **ipTM score** (interface predicted template modelling score — a confidence metric between 0 and 1 for how likely the predicted interface geometry is correct) from AlphaFold filters out candidates likely to fail before any wet-lab work begins.

4. **ESMFold** — a rapid structure prediction tool from Meta AI. Used as a second independent structural opinion on sequences that passed the AlphaFold filter.

The output is a ranked list of candidate nanobody sequences. The top 3–5 go to experimental synthesis: gene synthesis (a commercial service that chemically synthesises the DNA encoding the nanobody), bacterial expression (growing E. coli containing that DNA to produce the nanobody protein), and purification (isolating the nanobody from the bacterial culture).

**The critical design constraint:** The epitope structure fed into RFdiffusion must be the **tension-induced conformation** — the shape the protein adopts when stretched — not the relaxed folded structure. If you design against the folded protein, you get a binder that binds everywhere (every collagen molecule in the body). You want a binder specific to the stretched conformation. This is what Upside uniquely provides: a high-resolution picture of the stretched state that cannot be obtained experimentally at scale.

---

## 6. Step 3: Experimental Validation

### Why Optical Tweezers Alone Don't Scale

**Optical tweezers** (also called laser tweezers) are the current gold standard for measuring protein mechanics at the single-molecule level. The technique works by trapping microscopic beads — attached to either end of a protein — in focused laser beams. By moving the laser beams apart, you can pull on the protein with precisely controlled piconewton forces while measuring the extension in real time. It is extraordinarily precise but fundamentally one-molecule-at-a-time:

- Each experiment measures one molecule, requiring hundreds of repetitions for statistical significance (protein unfolding is stochastic — random — so you need many events to characterise the distribution)
- Setup requires skilled operators, specialised optical equipment, and bead conjugation chemistry (chemically attaching beads to specific sites on the protein)
- Data collection is slow — hours per condition per molecule
- Instrument cost is $300K–$1M, severely limiting access
- Most importantly: it is essentially impossible to run a binding assay (testing whether a nanobody binds) while simultaneously controlling force on hundreds of molecules

The goal is to move from single-molecule studies to **ensemble measurements under controlled tension** — running hundreds or thousands of simultaneous pulling experiments with a simple fluorescent readout. This is the experimental analog of what Upside does computationally with replica exchange: many copies, many forces, all at once.

### The Three Prototype Platforms

Three physical principles have been designed to apply controlled piconewton-range forces to proteins that are fixed to a surface at one end, leaving the other end free to be pulled:

**Platform 1 — Fluid Flow:** Proteins anchored to a surface; shear flow of fluid past the surface applies a **drag force** (resistance force from the fluid) on the free end of the protein. Force is controlled by flow velocity. The challenge: force uniformity across the surface is difficult to achieve; the hydrodynamics (fluid mechanics near a wall) are complex; careful engineering is needed to align the force along the desired axis.

**Platform 2 — Electric/Magnetic Field:** Proteins tagged at one end with a charged molecule or a magnetic particle; an electric or magnetic field gradient applies force. The challenge: generating field gradients that are both strong enough and uniform enough for quantitative force control over a large surface area is difficult; adding a magnetic bead to the protein significantly increases its mass and may alter its behaviour.

**Platform 3 — Centrifugal Force (preferred):** Proteins anchored to the inner wall of a centrifuge tube. When the tube spins, centrifugal force (the apparent outward force you feel on a merry-go-round) pulls the free end of the protein radially outward away from the tube wall. Force is set by rotation speed (RPM). Clean geometry, highly uniform force across the entire tube wall, precise and continuously tuneable force control.

### The Centrifuge Platform in Detail

**Force range and control:** Centrifugal force on an object is `F = m · ω² · r`, where:
- `m` is the effective mass of the protein (corrected for buoyancy in solution — the protein is less dense than the surrounding water, so it's partially offset)
- `ω` (omega) is the angular velocity in radians per second (proportional to RPM)
- `r` is the radius — how far from the rotation axis the protein is anchored

For a typical protein domain weighing 10–50 kDa (kilodaltons — the standard unit for protein mass, where 1 dalton ≈ the mass of one proton) anchored at r ≈ 5 cm from the rotation axis, spinning at a few thousand RPM gives forces in the 5–50 pN range. The force is continuously tuneable by changing the RPM, and because the centrifugal field is uniform across the entire tube wall at a given radius, all proteins at the same position experience identical force — unlike flow-based methods where edge effects create non-uniformities.

**The simultaneous multi-condition design:** The key insight is that within a single centrifuge tube, by placing proteins at different radial distances from the rotation axis, different zones experience different forces at the same RPM (because `F ∝ r`). A single tube can be divided into 10 radial zones spanning, say, 4–7 cm from the axis — each zone at a distinct force level. One spin = 10 simultaneous force conditions. Running 10 different RPM values gives 100 conditions from 10 spins.

**The specific target:** 10 simultaneous experiments at forces from 14 to 38 pN in one tube. This range covers the physiologically relevant forces for ECM protein partial unfolding in fibrotic tissue.

**Surface attachment chemistry:** Proteins must be attached at one specific end (N- or C-terminus — the two ends of a protein chain) to the tube surface, leaving the other end free to be pulled outward. Common attachment strategies:
- **His-tag / Ni-NTA**: A short sequence of 6 histidine amino acids (His-tag) engineered onto the protein end binds tightly to a nickel-chelating surface (Ni-NTA). Standard in biochemistry labs.
- **Biotin / streptavidin**: A small molecule (biotin) covalently attached to the protein end binds with extraordinary affinity to streptavidin (a protein from bacteria) coated on the surface. One of the strongest non-covalent interactions in biology.

The attachment chemistry defines the **pulling axis** — which direction the force is applied to the protein — and this must match the axis used in the Upside simulations for the computational predictions to be directly comparable.

### The Fluorescent Binder Readout

The assay principle is simple:

1. Immobilise the target protein (e.g. a fibronectin or collagen domain) on the centrifuge tube surface at multiple radial zones — same protein concentration at each zone.
2. Spin the tube at a defined RPM to apply the desired force profile across the zones.
3. While spinning (or immediately after stopping, before the protein can relax), incubate the surface with the **fluorescently tagged nanobody candidate** — the nanobody chemically attached to a fluorescent dye molecule that glows when illuminated by the right wavelength of light.
4. Wash off unbound nanobody and image the tube surface.

If the nanobody was designed against the tension-induced epitope, it should only bind — and produce fluorescent signal — at zones where the applied force exceeds the unfolding threshold. Below the threshold, the protein is folded, the epitope is buried, and nothing to bind means no fluorescence.

**Example of what a successful validation result looks like:** A nanobody designed against the epitope that appears at 20 pN shows:
- No fluorescence at the 14 pN zone
- No fluorescence at the 17 pN zone
- Signal first appears at the 20 pN zone
- Increasing signal at 24, 28, 32, 38 pN

This pattern of force-dependent binding proves the nanobody is recognising the stretched conformation specifically — a tension-selective binder that cannot bind the same protein in its relaxed state.

**Negative controls** (experiments designed to ensure the signal is real and not an artefact):
- Same nanobody with no centrifugation (protein relaxed, zero force) — should show no binding
- A non-specific nanobody with the same structural framework but **scrambled CDRs** (randomly reordered binding loops that shouldn't bind anything specifically) at all force levels — should show no binding
- The target protein with a **disulfide staple** (an engineered chemical crosslink between two cysteines that physically prevents a region of the protein from opening up) that blocks the relevant region from unfolding — should show no binding at any force

---

## 7. Connecting Computational and Experimental

The power of this approach is that the computational predictions and experimental results are directly, quantitatively comparable:

| Computational (Upside) | Experimental (Centrifuge) |
|------------------------|--------------------------|
| Constant-tension mode at simulated force F | Zone at radius r experiencing force F pN |
| Multiple replicas at 10 different force values | 10 radial zones in one tube spin |
| Force threshold where burial score drops and backbone angles shift | Force threshold where fluorescent signal first appears |
| Trajectory frames where the epitope becomes surface-exposed | Protein conformation in the binding-positive force zone |
| `environment` node burial score per residue | Physical accessibility to the fluorescent nanobody |

The gold-standard validation experiment:

1. Upside simulation predicts: "at 22 pN, residues 45–58 of fibronectin FN-III domain 10 become surface-exposed; their backbone angles shift from β-strand values to extended conformation"
2. A nanobody is designed (via RFdiffusion/ProteinMPNN) against that specific exposed surface
3. Centrifuge assay shows: the nanobody binds at the 22 pN zone but not at the 18 pN zone

A match between the computational unfolding threshold and the experimental binding threshold simultaneously validates two things: (1) that the simulation captures the actual mechanical behaviour of the real protein, and (2) that the AI-designed nanobody works as intended.

---

## 8. The Broader Tool

Beyond the immediate therapeutic application, the centrifuge platform — if it works — solves a general unsolved problem in the field of **mechanobiology** (the study of how mechanical forces affect biological systems at the molecular and cellular level).

**The current state of the field:** Almost everything known about protein mechanics at the single-molecule level comes from optical tweezers and AFM. These are powerful but slow, expensive, and low-throughput. As a result, mechanobiology has a data problem: only a tiny fraction of the proteome (the complete set of proteins in an organism) has been mechanically characterised, and even well-studied proteins have only been characterised under fast pulling conditions (millisecond timescales in AFM) rather than the slow, sustained equilibrium loading that actually occurs in living tissue.

**What the centrifuge platform adds:**
- **Ensemble measurements** — hundreds to thousands of protein molecules simultaneously, not one at a time
- **Equilibrium force application** — sustained constant tension over minutes to hours, matching physiological loading conditions, not millisecond pulls
- **High throughput** — tens of force conditions per spin, multiple spins per day
- **Low cost and simplicity** — uses a standard laboratory centrifuge, surface chemistry compatible with ELISA (a standard plate-based biochemistry assay) workflows
- **Combinatorial screening** — can test multiple nanobody candidates against the same protein at multiple forces in parallel, in a single experiment

**The mechanobiology research question it uniquely opens:** Most ECM proteins in living tissue are **dual-anchored** — attached to cells on both ends, actively mediating mechanical tension across the cell-ECM interface. This physiological state (protein under sustained tension, anchored at both ends, transmitting force) has essentially never been studied *in vitro* (in a controlled lab setting outside a living organism) because there has been no good experimental tool for it. The centrifuge platform is that tool. It opens the possibility of studying not just how individual proteins unfold under force, but how the entire ECM responds to the mechanical environment it experiences in diseased tissue.

---

## 9. Immediate Next Steps

Given current funding and time constraints, the highest-leverage actions in priority order:

**1. Run Upside pulling simulations on the primary target protein** (~days to a week, primarily computational work)
   - Identify the target protein. **Fibronectin FN-III domain 10** (a well-characterised folded domain within fibronectin — the "FN-III" refers to a specific fold type, and domain 10 contains the RGD sequence, a short amino acid motif Arg-Gly-Asp that is the primary cell-attachment site on fibronectin) is the recommended starting point — it is mechanically well-characterised in the literature and more tractable than collagen I's complex triple-helix structure
   - Obtain the PDB structure, run `upside_config.py` + `advanced_config.py` to prepare the pulling simulation
   - Run constant-tension simulations at 5–7 force values spanning the 14–38 pN range (after calibrating the Upside force scale to physical pN)
   - Extract partially unfolded intermediate structures from the trajectory
   - Identify candidate cryptic epitope regions by tracking burial drops and backbone angle shifts

**2. Back-map to all-atom and submit to RFdiffusion** (~1–2 weeks, mostly automated)
   - Use PULCHRA + SCWRL4 to reconstruct full atomic detail from the coarse-grained backbone
   - Energy-minimise the back-mapped structure using an all-atom force field to relax any unrealistic geometries introduced by the back-mapping
   - Run RFdiffusion targeting the newly exposed epitope surface
   - Run ProteinMPNN to design sequences for the top backbone scaffolds
   - Filter with AlphaFold-Multimer predicted interface scores (ipTM > 0.7 is the typical threshold for confidence in the complex structure prediction)
   - Select the top 3–5 candidate nanobody sequences for synthesis

**3. Build and validate the centrifuge prototype** (the critical bottleneck — no shortcuts here)
   - Use fibronectin FN-III domain 10 as the first test protein since its optical tweezer unfolding forces are known — this lets you validate the centrifuge force calibration against a reference
   - Establish the surface chemistry: test His-tag/Ni-NTA or biotin/streptavidin for protein attachment
   - Confirm that force is actually being applied at the expected levels using a **FRET-based molecular tension sensor** (FRET = Förster Resonance Energy Transfer, a technique where two fluorescent dyes on the same molecule change their fluorescence ratio when the molecule is stretched — a direct molecular ruler for force)
   - Test the fluorescent readout using a commercially available antibody against a known epitope as a positive control before using the AI-designed nanobody

**4. Integrate all three steps for one target protein**
   - The minimum publishable result: "we designed a nanobody that binds fibronectin at 22 pN but not at 15 pN, matching the computational prediction of epitope exposure at ~20 pN equivalent force"
   - This result is publishable as a methods paper in a high-impact journal (Nature Methods, Nature Biomedical Engineering) regardless of its immediate therapeutic application — it establishes the proof-of-concept for the entire platform

---

## 10. Open Questions and Gaps

**Force unit calibration.** Upside's internal force units are dimensionless and need to be anchored to physical piconewtons. This requires at least one well-characterised reference protein (fibronectin FN-III is the recommended choice). Until this calibration is done, force comparisons between simulation and experiment are qualitative.

**Coarse-grained to all-atom back-mapping.** The CG → AA (coarse-grained to all-atom) back-mapping step introduces uncertainty in side-chain positions. Since nanobody design depends critically on the atomic detail of the target surface, back-mapped structures should always be energy-minimised (their geometry optimised with an all-atom force field) before being submitted to RFdiffusion. The quality of the back-mapping is one of the weakest links in the pipeline.

**Which proteins to start with.** Collagen I is the most clinically relevant fibrosis target, but its triple-helix structure (three intertwined protein chains wound together, very different from a globular folded domain) is challenging to model in Upside's force field, which was designed primarily for globular proteins. Fibronectin FN-III domains are structurally simpler, better characterised mechanically, and a better proof-of-concept target.

**Centrifuge geometry and surface chemistry.** The specific tube geometry, surface functionalisation chemistry (how proteins are attached to the tube wall), protein orientation control (ensuring proteins are anchored at the right end), and imaging modality (confocal microscopy, total internal reflection fluorescence/TIRF, or a standard plate reader) all need to be specified and validated before the assay produces interpretable data.

**Selectivity over the relaxed protein.** The designed nanobody must not bind the same protein in its relaxed (zero-force) form. This selectivity is designed in from the start — the target was the tension-induced conformation — but it must be explicitly experimentally verified. The negative control (no centrifugation) is essential and must be done before claiming success.

**In vivo relevance.** Even if the *in vitro* platform works perfectly — the nanobody binds selectively at the right force threshold on a purified protein — the question remains whether it behaves the same way in fibrotic tissue, where the mechanical environment is heterogeneous, dynamic, and far more complex than a controlled centrifuge assay. This is a downstream validation question, but it should inform how the platform is designed from the start, so that *in vitro* results are as predictive of *in vivo* behaviour as possible.

---

*Research vision document — Mechanobiology / Targeted Fibrosis Therapy · Upside2 MD platform*

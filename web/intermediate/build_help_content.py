#!/usr/bin/env python3
"""Build help-content.js from structured entries. Run from repo: python3 web/intermediate/build_help_content.py"""
from __future__ import annotations

import json
from pathlib import Path


def E(title: str, overview: str, detail: str) -> dict:
    return {"title": title, "overviewHtml": overview.strip(), "detailHtml": detail.strip()}


def md_p(*paras: str) -> str:
    return "".join(f"<p>{p}</p>" for p in paras)


def analysis_metric(
    title: str,
    short: str,
    beginner: str,
    under_force: str,
    caveats: str,
) -> dict:
    overview = md_p(
        short,
        "Use it together with other plots: one metric rarely tells the whole story.",
    )
    detail = (
        "<h4>If you are completely new to MD</h4>"
        + md_p(
            "A molecular dynamics (MD) simulation is a computer experiment where the protein is treated as a collection of atoms (or simplified sites) that move under approximate physics. You get a movie of structures called a trajectory.",
            beginner,
        )
        + "<h4>Why this matters under force</h4>"
        + md_p(under_force)
        + "<h4>How to read the plot cautiously</h4>"
        + md_p(caveats)
    )
    return E(title, overview, detail)


def main() -> None:
    out: dict[str, dict] = {}

    out["settings_tamarind"] = E(
        "Tamarind Bio API key",
        md_p(
            "<strong>Tamarind Bio</strong> is an external cloud service that runs heavy protein-AI steps: roughly speaking, it can propose new binder shapes (diffusion-style), fill in sequences (MPNN-style), and score how well a binder might dock to your target (AlphaFold-Multimer-like models).",
            "Your API key is like a password. DynaLab stores it only in <code>web/server/.env</code> on the machine running the Flask server (that file should stay out of git).",
            "If you leave the key blank or use the mock client in the design card, the UI still works for demos—responses are fake but deterministic.",
        ),
        md_p(
            "Think of the key as permission to spend Tamarind compute credits. The key is never embedded in the web page sent to your browser; the browser asks your Flask server, and the server uses the key when it forwards a design job.",
            "If you are not ready to call a paid API, check <strong>mock client</strong> in the design section. That path exercises file handling and UI without touching Tamarind.",
            "If you rotate or revoke a key, update Settings and save again. Old jobs on disk are unaffected; only new submissions use the updated secret.",
        ),
    )

    out["settings_endpoint"] = E(
        "API endpoint",
        md_p(
            "The <strong>endpoint</strong> is the base web address Tamarind uses for its REST API—similar to how <code>https://api.example.com</code> is the front door for many services.",
            "Almost everyone should keep the default Tamarind host unless their support team gives you a staging URL or regional mirror.",
        ),
        md_p(
            "A REST API is just structured HTTPS traffic: DynaLab packages JSON, sends it to the endpoint, and reads JSON back. If the endpoint is wrong, you will see network errors or HTML error pages instead of JSON.",
            "Changing the endpoint does not change your science parameters; it only changes where the design request is delivered.",
            "If you are behind a strict firewall, outbound HTTPS to that host must be allowed from the machine running Flask—not from your laptop alone unless Flask runs locally.",
        ),
    )

    pdb_ov = (
        "<p>A <strong>PDB file</strong> is a text file that lists atoms (often just heavy atoms or Cα) and their 3D coordinates. It is the usual way crystallographers and structural biologists share a starting structure.</p>"
        '<figure class="help-modal__media"><img src="media/pdb-structure.gif" alt="Example protein structure rotating in 3D (cartoon representation)" loading="lazy" decoding="async">'
        '<figcaption class="help-modal__caption">Cartoons are a visualization; the PDB itself is coordinate tables, not a movie.</figcaption></figure>'
        "<p>DynaLab feeds that geometry into Upside preparation so the coarse-grained model matches your protein's shape and connectivity.</p>"
    )
    out["upload_pdb"] = E(
        "Structure upload",
        pdb_ov,
        md_p(
            "If you have never opened a PDB, open one in a text editor: you will see headers (metadata) and lines starting with ATOM or HETATM. Each line names an element and gives x,y,z in Ångströms.",
            "A <strong>single clean chain</strong> is easiest: missing atoms, unresolved loops, and fused crystal partners all become modeling assumptions. For membrane proteins, make sure the PDB orientation matches how you will configure the membrane card.",
            "Hydrogens are often absent in experimental PDBs—that is normal. Upside uses a coarse representation where hydrogens are implicit or grouped; the preparation step builds what the force field expects.",
            "Very large assemblies or multi-chain viral particles can run, but they cost more time. Start with the domain you care about if you only need local unfolding behavior.",
        ),
    )

    out["contact_details"] = E(
        "Contact information",
        md_p(
            "These fields are <strong>metadata only</strong>: they tag who initiated a run so shared servers, teaching labs, or core facilities can audit usage.",
            "Nothing here changes energies, forces, or integrators—it is purely for humans reading logs or job folders later.",
        ),
        md_p(
            "Treat this like signing a lab notebook page: useful when six months later you wonder who queued the 48-hour sweep.",
            "If privacy matters, use initials or a lab role instead of a personal email. The app does not validate email format beyond basic input.",
            "If you export or archive job directories, remember names and emails live in those JSON/metadata sidecars too.",
        ),
    )

    out["contact_name"] = E(
        "Name",
        md_p("Stored next to the job id on the Flask host when you click run.", "Helpful when multiple people share one workstation or queue."),
        md_p(
            "This is not authentication: anyone who can reach the server UI can type any name. It is a courtesy label, not access control.",
            "If you integrate with LIMS later, this field is the obvious hook to map into an operator id.",
        ),
    )

    out["contact_email"] = E(
        "Email",
        md_p(
            "Optional contact string recorded with the job.",
            "This demo does not send mail; it is only for humans browsing completed jobs.",
        ),
        md_p(
            "If you paste a shared lab inbox, everyone watching that inbox can correlate downloads—but the simulation itself does not email that address automatically.",
        ),
    )

    out["basic_simulation"] = E(
        "Basic simulation",
        md_p(
            "Here you choose <strong>how long</strong> to integrate, <strong>how often</strong> to save frames, and whether you simulate at one temperature or use <strong>replica exchange</strong> (several temperatures that occasionally swap coordinates).",
            "Upside reports temperature and time in <strong>reduced units</strong> tied to its force field. Think of them as dial settings you compare across runs rather than literal lab thermometers until you do a careful calibration story.",
        ),
        md_p(
            "Molecular dynamics solves Newton-like equations for many particles. Short runs only explore tiny vibrations; longer runs let larger rearrangements appear, but never guarantee you will see rare events.",
            "The <strong>frame interval</strong> controls how often you take a snapshot for movies and analysis. Saving every step is almost never necessary and creates huge files.",
            "Replica exchange is a statistical trick: hot copies help hop barriers while cold copies stay near physiological conditions; swaps must be accepted often enough or you wasted parallel CPUs.",
            "If a setting feels abstract, run a 30-second toy job and look at the trajectory: intuition follows from watching cartoons move.",
        ),
    )

    out["sim_mode"] = E(
        "Simulation mode",
        md_p(
            "<strong>Constant temperature</strong> keeps one thermostat on one copy of your protein—classic MD.",
            "<strong>Replica exchange</strong> runs several copies at different temperatures and periodically tries to swap coordinates between neighbors to improve sampling.",
        ),
        md_p(
            "Constant-T mode is the default mental model: energy bumps into the bath, the bath stays at set temperature, the protein explores conformations allowed at that heat.",
            "Replica exchange adds ladders: a very hot replica can unfold quickly, while a cool replica stays near native conditions. Swaps let the cool chain inherit beneficial moves discovered by hot chains.",
            "If your question is only local relaxation around a crystal structure, constant temperature is simpler. If you need barrier crossings (partial unfolding without insane heat on the physical replica), replica exchange is attractive.",
        ),
    )

    out["duration_steps"] = E(
        "Duration (steps)",
        md_p(
            "Total number of MD integration steps before the job stops.",
            "More steps cost more CPU but let slower motions appear; tiny runs are only smoke tests.",
        ),
        md_p(
            "An integration step is one tick of the simulation clock. The physical time per step depends on the propagator and model; Upside uses a coarse model where each step is cheap but not a literal femtosecond mapping without documentation.",
            "If you pull or sweep forces, interesting events might occur late—too-short jobs end before the protein responds.",
            "If you are iterating parameters, start short, then extend once plots look stable.",
        ),
    )

    out["frame_interval"] = E(
        "Frame interval",
        md_p(
            "Save a snapshot every <em>N</em> steps into the trajectory file.",
            "Smaller <em>N</em> gives smoother movies and finer plots but larger files and slower analysis.",
        ),
        md_p(
            "Think of frames as photographs of a race: more photos catch brief grimaces, but your album becomes heavy.",
            "For slow observables like radius of gyration, a modest interval is fine. For rapid bond vibrations you rarely save every vibration anyway because the model is coarse.",
            "If disk is tight, double the interval and see whether your plots change materially.",
        ),
    )

    out["temperature_reduced"] = E(
        "Temperature",
        md_p(
            "Thermostat target in Upside <strong>reduced</strong> units—not literal Kelvin in this UI field.",
            "Higher values add kinetic energy and can accelerate unfolding; lower values keep the chain more frozen.",
        ),
        md_p(
            "Temperature controls how vigorously random kicks jiggle the chain. In reduced units, what matters is relative comparisons between runs and the replica ladder spacing—not the absolute number by itself.",
            "If you compare to wet lab, you need a mapping story from reduced units to physical units for your force field and model resolution—that is research-level calibration, not a single universal factor.",
            "If the protein explodes numerically, temperature may be too high for your timestep or constraints; if nothing moves, it may be too low or your duration too short.",
        ),
    )

    out["replica_exchange"] = E(
        "Replica exchange",
        md_p(
            "Several simulations run in parallel at different temperatures and periodically attempt to exchange coordinates between neighbors.",
            "Cold replicas stay near the structure you care about; hot replicas help hop barriers; exchange moves share progress between them.",
        ),
        md_p(
            "Without replica exchange, you might crank heat to see rare events—but then your 'physical' chain is unrealistically hot. Replica exchange keeps a cool chain while borrowing exploration from hot chains via accepted swaps.",
            "The <strong>replica interval</strong> sets how many MD steps occur between swap attempts. Too frequent swaps can hurt relaxation; too rare swaps under-use the ladder.",
            "Acceptance rates matter: if temperatures are too far apart, swaps never accept; if too close, you duplicate work without benefit.",
            "This is still not magic: if the phenomenon needs milliseconds and your model gives microseconds of effective sampling, MD may never show it.",
        ),
    )

    out["replica_n_replicas"] = E(
        "Number of replicas",
        md_p("How many parallel temperature rungs sit on the replica ladder.", "More rungs widen the temperature span or tighten spacing—both cost CPU."),
        md_p(
            "Each replica is a full copy of the system evolving at its own temperature. Doubling replicas roughly doubles wall time unless you have idle cores.",
            "Spacing replicas evenly in temperature space is common; the UI exposes low/high and count rather than every intermediate value explicitly.",
        ),
    )

    out["replica_t_low"] = E(
        "T_low",
        md_p("The coldest replica's thermostat setting (reduced units).", "Usually closest to the 'physiological' behavior you want to interpret."),
        md_p(
            "This is the replica whose frames you might compare most directly to experimental intuition—still coarse-grained, but not artificially scorching.",
            "If T_low is too high, even your 'cold' chain is overheated; if too low, swaps from warm replicas may rarely propagate useful moves.",
        ),
    )

    out["replica_t_high"] = E(
        "T_high",
        md_p("The hottest replica on the ladder (reduced units).", "Helps cross barriers that block the cold replica."),
        md_p(
            "Hot replicas explore more aggressively but can look denatured—that is acceptable if swaps feed partial progress back to cold replicas.",
            "If T_high is not hot enough, you may see no improvement over constant temperature. If absurdly hot, numerical instabilities or junk structures can appear.",
        ),
    )

    out["replica_interval"] = E(
        "Replica interval",
        md_p("MD steps between batches of replica swap attempts.", "Shorter intervals mix more aggressively; longer intervals let each replica relax."),
        md_p(
            "Swapping too often is like shaking a lava lamp every second: interfaces never settle. Swapping too rarely is like stirring once an hour: replicas stay isolated.",
            "Watch logs or acceptance metrics if you add them later; tuning intervals is an advanced but common task.",
        ),
    )

    out["pulling_overview"] = E(
        "Pulling",
        md_p(
            "Adds external forces so the protein feels mechanical load similar to <strong>AFM</strong>, <strong>optical tweezers</strong>, or a <strong>centrifuge</strong> assay after calibration.",
            "Enable only when your question involves tension, unfolding pathways, or cryptic surfaces exposed under stress.",
        ),
        md_p(
            "In the lab, pulling unfolds domains at a measured rate or force. In the model, pulling biases the energy landscape so unfolded states become accessible within simulation time.",
            "If you do not need force, leave pulling off: extra handles add parameters and ways to misuse geometry.",
            "Pulling is not a substitute for careful experimental geometry: attachment points, linker compliance, and surface chemistry all shift real forces.",
        ),
    )

    out["pulling_mode"] = E(
        "Pulling mode",
        md_p(
            "<strong>Velocity clamp (AFM-style)</strong>: a virtual spring moves at set speed; force builds as the protein resists.",
            "<strong>Constant tension</strong>: applies a target load more directly—closer to thinking in piconewtons once calibrated.",
        ),
        md_p(
            "Real AFM cantilevers are springs dragged at constant speed until bonds break; the velocity-clamp mode mirrors that story line.",
            "Constant tension is closer to 'I apply 20 pN and see how the extension drifts'—useful when your experiment holds load while fluorescence reports state.",
            "Neither mode includes the wet-lab fluid viscosity, surface adsorption, or cantilever calibration drift; those remain interpretation layers on top.",
        ),
    )

    out["pulling_afm_config"] = E(
        "AFM (velocity clamp) fields",
        md_p(
            "<strong>Residue</strong> (0-based index): which Cα the spring grabs.",
            "<strong>Spring constant</strong>: stiffer spring transmits more force for the same extension (Upside reduced units).",
            "<strong>Tip position</strong> and <strong>pulling velocity</strong>: where the spring anchor lives in space and how fast it moves per step.",
        ),
        md_p(
            "Indexing: most programmers count from 0; biologists often count residues from 1. If results look off by one, check this mismatch first.",
            "The spring constant couples geometry to force: too soft and nothing happens; too stiff and integrators can become finicky.",
            "Velocity is per integration step in Å/step in the UI fields—tiny numbers are normal. Think in orders of magnitude and watch extension traces.",
        ),
    )

    out["pulling_tension_config"] = E(
        "Constant tension fields",
        md_p(
            "Each row lists a residue and a tension vector <strong>(tx, ty, tz)</strong> in kT/Å units used internally.",
            "Multiple rows can implement opposed pulls: anchor one end, tug the other.",
        ),
        md_p(
            "Constant tension does not magically know your centrifuge lane calibration; pN targets in sweeps are converted using documented factors elsewhere in the pipeline.",
            "Vectors mean direction matters: pulling along z versus x can sample different unfolding pathways.",
            "If nothing moves, tension might be tiny relative to internal forces; if everything explodes, tension or timestep may be too aggressive.",
        ),
    )

    out["force_sweep"] = E(
        "Force sweep",
        md_p(
            "Runs a <strong>ladder of forces</strong> (in piconewtons after calibration), one sub-simulation per force (with optional replicas each).",
            "This mirrors multi-lane centrifuge experiments where each lane feels a different effective load.",
        ),
        md_p(
            "Single pulling answers 'what happens at one load'. Sweeping answers 'at which load does this epitope or domain cross a threshold'.",
            "Cost scales with number of forces times replicas times duration—plan a sparse ladder first, then refine near interesting thresholds.",
            "When sweep is enabled, the big Run button orchestrates many child jobs instead of the single configuration in card 4 alone.",
        ),
    )

    out["sweep_subsim"] = E(
        "Sub-simulation type",
        md_p("Chooses velocity-clamp vs constant-tension physics <em>inside each</em> sweep sub-job.", "Matches the same conceptual choice as the single pulling card."),
        md_p(
            "The sweep only changes the force schedule; the underlying pull mode still changes how load enters the equations.",
            "If you mix modes between papers and simulation, document which mode matched which assay.",
        ),
    )

    out["sweep_forces_pn"] = E(
        "Forces (pN)",
        md_p(
            "Comma-separated list of target forces in <strong>piconewtons</strong> after your calibration story.",
            "Example ladder: <code>14,18,22,26,30,34,38</code> spanning a biophysically interesting window.",
        ),
        md_p(
            "A piconewton is a trillionth of a newton—typical single-molecule forces live in tens to hundreds of pN.",
            "Spacing: linear ladders are easy to interpret; adaptive refinement is a manual loop (rerun with tighter spacing near transitions).",
            "If a value fails to parse, that sub-job may error—keep commas plain ASCII and numbers simple decimals.",
        ),
    )

    out["sweep_replicas"] = E(
        "Replicas per force",
        md_p("Independent repeats at <em>each</em> force in the ladder.", "Improves statistics for stochastic unfolding; multiplies CPU time."),
        md_p(
            "Biological single-molecule traces jitter run-to-run; replicas mimic repeating the experiment under identical programmed load.",
            "Use at least 2–3 when you will compare distributions; use 1 only for exploratory wiring.",
        ),
    )

    out["sweep_anchor"] = E(
        "Anchor residue",
        md_p(
            "0-based residue treated as the fixed or reference end of the pull geometry for sweep sub-jobs.",
            "Pairs with pull residue to define a load path through the chain.",
        ),
        md_p(
            "Pick anchors that match how the protein attaches in assay: C-term His-tag immobilized implies different effective anchors than N-term fusion.",
            "If anchor equals pull site, forces are degenerate—double-check indices.",
        ),
    )

    out["sweep_pull_residue"] = E(
        "Pull residue",
        md_p(
            "0-based residue where the pulling potential applies.",
            "Use <strong>-1</strong> to mean the last residue—common for C-terminal handles.",
        ),
        md_p(
            "The pull site should coincide with the chemistry that actually feels the bead or surface in your experimental construct.",
            "Off-by-one errors between sequence numbering and PDB numbering are a classic pitfall; verify against a structure viewer.",
        ),
    )

    out["membrane"] = E(
        "Membrane",
        md_p(
            "Adds implicit membrane boundaries so membrane proteins feel confinement similar to a bilayer slab.",
            "Disable for soluble-only systems; tune inner/outer limits when enabled.",
        ),
        md_p(
            "This is not an explicit lipid bilayer with every tail: it is a simplified potential that captures the large-scale effect of being embedded.",
            "Orientation matters: your PDB must sit in the coordinate frame expected by the slab definition.",
            "If the protein drifts out of the slab, recentering options or boundary choices may be wrong.",
        ),
    )

    out["membrane_coord_system"] = E(
        "Membrane coordinate system",
        md_p(
            "<strong>Cartesian</strong>: slab normal along z; inner/outer are z limits.",
            "<strong>Spherical</strong>: alternate convention for specialized Upside setups—only if your preparation matches.",
        ),
        md_p(
            "If you are unsure, Cartesian is the common teaching picture: membrane horizontal in the xy plane, thickness along z.",
            "Mismatch here is a silent science bug: the protein can be 'in membrane' numerically while visually outside in a viewer if frames are rotated.",
        ),
    )

    out["membrane_inner_bound"] = E(
        "Inner membrane boundary",
        md_p("One edge of the membrane slab in Ångströms.", "Together with the outer boundary defines where the implicit membrane acts."),
        md_p(
            "Inner vs outer naming follows the Upside convention for the slab; visually verify in a structure viewer which leaflet is which for your PDB.",
            "If boundaries hug the protein too tightly, steric clashes or artificial squeezing can appear.",
        ),
    )

    out["membrane_outer_bound"] = E(
        "Outer membrane boundary",
        md_p("The opposite slab face from the inner boundary (Å).", "Adjust until the protein sits in the intended region."),
        md_p(
            "Think of the two boundaries like the walls of a narrow elevator shaft: the chain should ride comfortably between them.",
            "If water or headgroup chemistry matters for your question, remember those details are not atomically resolved here.",
        ),
    )

    out["membrane_recenter_opts"] = E(
        "Membrane recentering",
        md_p(
            "Controls whether the simulation periodically recenters the system relative to the membrane.",
            "Turn off only if you deliberately want drift or have an exotic setup.",
        ),
        md_p(
            "Periodic boxes can make proteins appear to slide; recentering keeps the biology interpretable in Cartesian viewers.",
            "Wrong recentering can 'yank' a protein out of the slab—if that happens, revisit boundaries and these toggles.",
        ),
    )

    out["restraints"] = E(
        "Restraints",
        md_p(
            "Extra springs or walls that pin atoms, keep distances, or mimic attachment points.",
            "Text formats mirror Upside preparation tables—typos become silent or loud failures at prep time.",
        ),
        md_p(
            "Restraints are mathematical rubber bands: cheap computationally but easy to over-constrain so the physics is no longer representative.",
            "Use the smallest restraint that enforces your experimental symmetry (e.g., pinned termini for an AFM handle).",
            "Each subtype (wall vs spring vs nail) encodes different geometry—read the inline card examples slowly.",
        ),
    )

    out["restraint_fixed_wall"] = E(
        "Fixed wall restraint",
        md_p(
            "Each line: <code>residue radius spring_const wall_type x0 y0 z0</code>.",
            "Keeps a residue outside a spherical wall centered at a fixed point.",
        ),
        md_p(
            "Imagine an invisible ping-pong ball the residue cannot enter: the wall_type and radius set the geometry; the spring constant sets how sharply you bounce off.",
            "Use when you want a steric exclusion zone (e.g., a surface) without modeling every surface atom.",
        ),
    )

    out["restraint_pair_wall"] = E(
        "Pair wall restraint",
        md_p("Each line: <code>residue1 residue2 radius spring_const</code>.", "Enforces a minimum distance between two residues."),
        md_p(
            "Pair walls mimic 'these two parts cannot interpenetrate beyond this contact distance'—looser than a bond, tighter than free flight.",
            "Good for approximate excluded volume between domains when you do not want a full spring connecting them.",
        ),
    )

    out["restraint_fixed_spring"] = E(
        "Fixed spring restraint",
        md_p("Each line: <code>residue spring_const x0 y0 z0</code>.", "Harmonic spring tying a residue toward a fixed coordinate."),
        md_p(
            "This is the AFM-like idea in miniature: a point in space attracts a residue with a quadratic penalty.",
            "High spring constants behave like rigid tethers; low constants allow breathing.",
        ),
    )

    out["restraint_pair_spring"] = E(
        "Pair spring restraint",
        md_p("Each line: <code>residue1 residue2 radius spring_const</code>.", "Spring-like coupling between two residues as consumed by Upside prep."),
        md_p(
            "Use when two sites should feel an attractive or repulsive bias relative to one another beyond ordinary nonbonded interactions.",
            "Check units and signs in the Upside documentation—this UI only forwards your table faithfully.",
        ),
    )

    out["restraint_nail"] = E(
        "Nail restraint",
        md_p("Each line: <code>residue spring_const</code>.", "Very strong pinning of a residue—use sparingly."),
        md_p(
            "Think of a nail through a board: you freeze a spot so the rest of the chain can flap.",
            "Overuse nails artificial crystal artifacts into the trajectory; prefer the weakest nail that still enforces your boundary condition.",
        ),
    )

    out["run_simulation"] = E(
        "Run",
        md_p(
            "Packages your PDB and configuration, launches Upside (or the sweep orchestrator) on the Flask host, and streams logs into <code>web/server/jobs/&lt;id&gt;/</code>.",
            "Requires name, email, and a selected PDB; additional cards add optional physics.",
        ),
        md_p(
            "Nothing here runs in your browser: the browser is a remote control for the server process.",
            "If the button stays disabled, required fields are missing or the UI thinks the form is incomplete.",
            "If sweep is enabled, the same button fans out many child jobs—watch disk and CPU accordingly.",
        ),
    )

    out["progress_tracking"] = E(
        "Progress",
        md_p(
            "Parses the simulation log for step counts vs target and coarse status text.",
            "Long jobs can sit apparently still while the integrator grinds—refresh patience first.",
        ),
        md_p(
            "Progress bars are best-effort: they depend on log formatting from the engine version you run.",
            "If a job fails early, the bar may jump to failure text instead of 100%—read the log card when available.",
        ),
    )

    out["results_download"] = E(
        "Results",
        md_p(
            "Finished jobs expose the trajectory file (Upside/HDF5 style <code>.up</code>) for download.",
            "That file feeds downstream analysis checkboxes.",
        ),
        md_p(
            "Trajectories are the raw experimental record of the simulation: every analysis is a derived view.",
            "If downloads fail, check browser pop-up blockers and reverse-proxy size limits for large files.",
        ),
    )

    out["post_analysis_overview"] = E(
        "Post-processing analysis",
        md_p(
            "Each checkbox triggers a Python analysis on the server that rereads the trajectory and emits plots plus JSON summaries.",
            "Some analyses are cheap scalars; others (contacts, clustering) are heavier—toggle only what you need.",
        ),
        md_p(
            "Post-processing does not change the saved trajectory; it only creates sibling artifacts under the job directory.",
            "Order of operations: finish MD, download if you want a local copy, then run analyses against the server-side file.",
            "No checkbox replaces experimental validation: these are computational observables tied to a specific force field and resolution.",
        ),
    )

    out["analysis_rg"] = analysis_metric(
        "Radius of gyration (Rg)",
        "Rg measures how spread out the mass is around its center: compact proteins have small Rg; stretched or unfolded chains have large Rg.",
        "Rg is a single number per frame computed from atomic or Cα positions and masses (depending on implementation). It is like asking 'how big is the cloud of atoms?'.",
        "Under force, Rg often rises when domains detach or the chain elongates along the pull axis.",
        "Rg is blind to shape details: two different shapes can share the same Rg. Pair it with end-to-end distance, contact maps, or visuals.",
    )

    out["analysis_rmsd"] = analysis_metric(
        "RMSD",
        "RMSD (root-mean-square deviation) compares the current structure to a reference frame—usually the first saved frame—and reports how far atoms moved on average.",
        "RMSD is computed after superimposing structures to remove overall translation/rotation, so it focuses on internal deformation rather than drifting through space.",
        "When pulling unfolds a domain, RMSD often climbs because the internal arrangement no longer matches the starting crystal-like pose.",
        "Large flexible loops can dominate RMSD even when the core is fine; interpret alongside per-residue RMSF.",
    )

    out["analysis_rmsf"] = analysis_metric(
        "RMSF",
        "RMSF (root-mean-square fluctuation) is per residue: it tells you which parts of the chain jiggle a lot vs stay rigid over the trajectory.",
        "After aligning frames, each atom's variance around its average position is summarized; peaks highlight loops and hinges.",
        "Under tension, flexible epitope-containing loops may spike in RMSF right before or during exposure events.",
        "RMSF is not dynamics timescales: a residue can fluctuate quickly or slowly yet show similar variance if the amplitude is large.",
    )

    out["analysis_e2e"] = analysis_metric(
        "End-to-end distance",
        "Distance between the first and last Cα atoms—simple scalar stretch measure for single-chain constructs.",
        "If your construct is one continuous chain, end-to-end tracks how much the termini separate under load.",
        "In pulling, rising end-to-end often tracks global unraveling along the pull vector when handles are termini.",
        "If your functional site is mid-chain, pair this with local distance monitors or contact maps; end-to-end can miss mid-domain opening.",
    )

    out["analysis_hbonds"] = analysis_metric(
        "Hydrogen bonds",
        "Counts backbone hydrogen bonds per frame using a geometric criterion (Baker–Hubbard style).",
        "Secondary structure elements like helices and sheets are stabilized by patterns of hydrogen bonds; losing them often tracks unfolding.",
        "Under force, hydrogen-bond counts may drop as helices peel or sheets fray.",
        "This is still a geometric proxy: it does not equal free energy of folding and can mis-count in coarse models.",
    )

    out["analysis_salt"] = analysis_metric(
        "Salt bridges",
        "Approximates salt-bridge-like contacts using Cβ distances—fast and coarse-grained friendly, not a full electrostatic energy.",
        "Salt bridges are attractive interactions between oppositely charged side chains; they stabilize many protein interfaces.",
        "Force can disrupt salt bridges as charged groups separate, sometimes correlating with functional exposure.",
        "Because the metric is simplified, do not over-interpret single bond counts—look for sustained trends.",
    )

    out["analysis_shape"] = analysis_metric(
        "Shape descriptors",
        "Scalars derived from the gyration tensor: asphericity, acylindricity, and anisotropy describe whether the mass distribution is spherical, cigar-like, or pancake-like.",
        "These numbers summarize 3D shape without rendering a picture—useful for automated sweeps.",
        "Under tension proteins often elongate: anisotropy and asphericity move in characteristic directions.",
        "They are global summaries: combine with contact maps when shape changes are subtle or localized.",
    )

    out["analysis_crosscorr"] = analysis_metric(
        "Cross-correlation",
        "Measures correlated motion between residues: who moves together or opposite over time.",
        "Allostery is 'motion at a distance': a perturbation at site A changes dynamics at site B. Cross-correlation helps visualize that coupling network.",
        "Under load, mechanical propagation can show up as streaks of positive correlation along the pull pathway.",
        "Correlation is not causation: statistical coupling can arise from many degenerate pathways.",
    )

    out["analysis_ss"] = analysis_metric(
        "Secondary structure",
        "Assigns helix/sheet/coil labels over time using DSSP when installed, otherwise a simplified hydrogen-bond fallback.",
        "Secondary structure is the local repeating backbone pattern: α-helices look like coils, β-sheets look like ladders in cartoons.",
        "Unfolding under force often shows sheets or helices converting to coil in regions that were structured at rest.",
        "DSSP needs backbone geometry compatible with its assumptions; missing atoms or extreme distortions reduce reliability.",
    )

    out["analysis_pca"] = analysis_metric(
        "PCA",
        "Principal component analysis finds the dominant collective motions in the set of Cα frames—usually the first few modes capture most variance.",
        "Imagine approximating a wiggling protein path as a sum of a few simple 'shapes' of motion; PCA discovers those shapes from data.",
        "Useful to see global opening/closing or hinge motions under force without hand-picking a reaction coordinate.",
        "Too many components overfit noise; too few miss nuance. Start with 2–3 for plotting, then justify more if needed.",
    )

    out["analysis_force_ext"] = analysis_metric(
        "Force vs extension",
        "Builds approximate force–extension curves from pulling geometry recorded in the trajectory plus job metadata.",
        "An AFM trace is force vs tip extension; this analysis tries to put simulation on comparable axes after calibration assumptions.",
        "Compare qualitative shapes (sawtooth, ripples, plateaus) to experiment, not absolute numbers without calibration.",
        "Approximate: coarse models omit many physical effects present in real tips and buffers.",
    )

    out["analysis_contacts"] = analysis_metric(
        "Contact map",
        "Shows how often pairs of residues are within a cutoff distance across the trajectory—heatmap style.",
        "Contacts reveal which parts of the protein touch; stable cores stay dark; opening shows as fading or shifting patches.",
        "Under force, long-range contacts between termini may break while new local contacts appear transiently.",
        "Heavy to compute: expect longer runtime and larger memory than scalar plots.",
    )

    out["analysis_burial"] = analysis_metric(
        "Burial scan",
        "Tracks a solvent exposure proxy per residue over time to see when side chains become more solvent-accessible.",
        "Cryptic epitopes are sometimes hidden in grooves until tension opens the groove; burial scans hunt that signature.",
        "Pair with structural snapshots at the same frames to avoid over-reading a single scalar curve.",
        "Exposure metrics depend on probe radius and coarse representation; compare runs only with identical settings.",
    )

    out["analysis_dihedral"] = analysis_metric(
        "Dihedral unfolding",
        "Summarizes how backbone Ramachandran basins shift from start to end of the trajectory.",
        "Each residue's backbone has two main dihedral angles (φ, ψ); preferred combinations define helices vs sheets.",
        "Useful when secondary structure labels say 'coil' but you want to see if angles hop between basins gradually.",
        "Interpretation benefits from molecular graphics literacy; if new, pair with secondary structure plots first.",
    )

    out["analysis_cluster"] = analysis_metric(
        "Intermediate clustering",
        "Clusters trajectory frames in a contact-based feature space and writes representative PDBs into <code>intermediates/</code> for downstream design.",
        "Clustering answers 'how many distinct shapes did we visit?' rather than 'what is the average structure?'.",
        "Under heterogeneous unfolding, you may get separate clusters for native-like, partially unfolded, and fully stretched states.",
        "Choosing cluster medoids for AI design is a scientific judgment: outliers may be artifacts if clustering noise dominates.",
    )

    out["backmapping"] = E(
        "All-atom back-mapping",
        md_p(
            "Upside is coarse-grained: it does not keep every atom explicit. <strong>PULCHRA</strong> rebuilds an all-atom PDB from Cα geometry.",
            "Optional minimization can relax clashes if OpenMM is installed.",
        ),
        md_p(
            "Many downstream tools (diffusion, docking, MPNN) expect full atom types and bond chemistry; back-mapping is the bridge step.",
            "Back-mapping is reconstructive guesswork: validate stereochemistry in a viewer before trusting hydrogens or unusual residues.",
            "If minimization is off, clashes may remain; if on, watch that minimization does not erase the unfolded state you cared about.",
        ),
    )

    out["ai_design"] = E(
        "AI nanobody design",
        md_p(
            "Sends a chosen snapshot through an external stack that proposes binder backbones, fills sequences, and scores predicted complexes (Tamarind).",
            "Mock mode runs a deterministic stub for demos without API keys or billing.",
        ),
        md_p(
            "Think of three stages: (1) propose shapes that might dock, (2) choose sequences that fold, (3) score predicted binding quality.",
            "Outputs are hypotheses, not drugs: expression, immunogenicity, and wet binding still dominate real programs.",
            "Costs and latency scale with how many backbones and sequences you request—start small while learning the UI.",
        ),
    )

    out["design_intermediate"] = E(
        "Intermediate state",
        md_p(
            "Pick which clustered, back-mapped PDB best represents the partially unfolded 'target face' you want binders against.",
            "Usually comes from the clustering analysis outputs.",
        ),
        md_p(
            "The same raw trajectory can yield different medoids; your scientific story should justify which state is the design target.",
            "If the snapshot is barely unfolded, binders may not gain cryptic-site specificity you hoped for.",
        ),
    )

    out["design_hotspots"] = E(
        "Hotspot residues",
        md_p(
            "Comma-separated residue indices where you want the binder to make contact—often from epitope prediction or exposure plots.",
            "Guides the external model toward biologically relevant interfaces.",
        ),
        md_p(
            "Hotspots are soft hints: algorithms may still deviate if other contacts lower energy dramatically.",
            "Use 0-based indices consistent with the uploaded PDB used throughout the job.",
        ),
    )

    out["design_n_backbones"] = E(
        "Number of backbones",
        md_p(
            "How many distinct backbone scaffolds the diffusion-style sampler requests before sequence design.",
            "More diversity increases exploration and cost.",
        ),
        md_p(
            "If you request many backbones early, you may drown in similar solutions—iterate with small counts first.",
            "Diversity interacts with binder length and hotspot patterns; expect to tune jointly.",
        ),
    )

    out["design_binder_length"] = E(
        "Binder length",
        md_p(
            "Target length in amino acids for the designed binder.",
            "Longer chains can bury more interface but are harder to express and fold.",
        ),
        md_p(
            "Nanobodies are single-domain antibodies; their natural lengths inform sensible starting ranges.",
            "If length is mismatched to epitope size, you may get frustrated loops or incomplete coverage.",
        ),
    )

    out["design_n_seqs_mpnn"] = E(
        "MPNN sequences per backbone",
        md_p(
            "How many sequence variants ProteinMPNN proposes per backbone scaffold.",
            "More sequences explore sequence space but increase compute and API time.",
        ),
        md_p(
            "Sequence design assumes the backbone is reasonable; fix backbone issues before cranking sequences.",
            "Use diversity where experimental throughput can screen many candidates; otherwise keep small.",
        ),
    )

    out["design_use_mock"] = E(
        "Mock client",
        md_p(
            "When enabled, the server uses a deterministic offline stub instead of Tamarind.",
            "No API key, no charges—ideal for CI, teaching, or UI testing.",
        ),
        md_p(
            "Mock outputs look structurally plausible at a glance but are not biophysical predictions.",
            "Switch mocks off only when you are ready to spend credits and have keys configured.",
        ),
    )

    out["centrifuge_experiment"] = E(
        "Centrifuge experiment design",
        md_p(
            "Generates a bench-oriented markdown sheet mapping rotor zones, force ranges, attachment chemistry, and predicted thresholds.",
            "Bridges simulation language to what a human does at the bench.",
        ),
        md_p(
            "The sheet is a communication artifact for teams: it does not replace SOPs or safety review for real rotors.",
            "Fill forces and zones honestly to match the hardware you own; otherwise predictions misalign with reality.",
        ),
    )

    out["exp_zones"] = E(
        "Radial zones",
        md_p(
            "How many discrete radial lanes or bins you will use in the tube/rotor experiment.",
            "Matches stratifying g-force exposure across positions.",
        ),
        md_p(
            "Each zone can map to a different effective load on the protein construct if calibration is done carefully.",
            "If you mismatch zone count vs simulation ladder, overlays become harder to read.",
        ),
    )

    out["exp_force_range_low"] = E(
        "Force range (low)",
        md_p("Lower end of the experimental pN window for the protocol sheet.", "Should pair with the high end to span the regime you test."),
        md_p(
            "Choose based on instrument sensitivity and the forces where your readout changes in pilot data.",
            "If low is near zero, remember surface-specific detachment forces can dominate near the bottom of the range.",
        ),
    )

    out["exp_force_range_high"] = E(
        "Force range (high)",
        md_p("Upper end of the experimental pN window for the protocol sheet.", "Must exceed the low end."),
        md_p(
            "Rotor geometry and column height determine achievable ranges; do not copy literature numbers blindly.",
            "If high forces risk denaturation unrelated to your epitope, note that in the attachment chemistry section.",
        ),
    )

    out["exp_thresholds_list"] = E(
        "Predicted thresholds",
        md_p(
            "Comma-separated pN values from simulation that you want printed on the bench sheet as reference lines.",
            "Example: predicted exposure onset forces from burial scans.",
        ),
        md_p(
            "Thresholds are hypotheses until validated against fluorescence or binding assays.",
            "Use separate thresholds for distinct conformational events if the biology has multiple steps.",
        ),
    )

    out["exp_attachment_chemistry"] = E(
        "Attachment chemistry",
        md_p(
            "Free text describing how the protein attaches to the surface (His-tag/Ni-NTA, biotin/streptavidin, covalent linker, etc.).",
            "Changes how you interpret force at the protein–surface junction.",
        ),
        md_p(
            "The same nominal rotor g-force can produce different protein tension depending on linker compliance and orientation.",
            "Good notes here prevent collaborators from mixing incompatible constructs when comparing lanes.",
        ),
    )

    out["wetlab_csv"] = E(
        "Wet-lab CSV",
        md_p(
            "Upload a CSV of measured fluorescence (or similar) vs force with columns like <code>force_pN</code>, <code>fluorescence</code>, <code>replicate</code>, <code>condition</code>.",
            "Lets the server overlay experimental batches against computational predictions.",
        ),
        md_p(
            "Tidy data beats pretty spreadsheets: one row per observation, consistent units, ASCII commas.",
            "Document what fluorescence means (FRET pair, dye quenching, etc.) in your lab notebook; the CSV cannot carry full prose safely.",
        ),
    )

    out["pred_threshold_pn"] = E(
        "Predicted threshold (pN)",
        md_p(
            "Single scalar threshold from simulation (e.g., onset of exposure) used when comparing to uploaded wet-lab curves.",
            "Drawn as a vertical reference on comparison plots.",
        ),
        md_p(
            "Pick the threshold from the same analysis pipeline you trust scientifically, not an arbitrary round number.",
            "If multiple events exist, run separate comparisons or extend the tool later—this field is one scalar by design.",
        ),
    )

    root = Path(__file__).resolve().parent
    target = root / "help-content.js"
    target.write_text(
        "/* Auto-generated by build_help_content.py — edit that script and re-run: python3 web/intermediate/build_help_content.py */\n"
        "window.DYNALAB_HELP_CONTENT = "
        + json.dumps(out, ensure_ascii=False, indent=2)
        + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {target} ({len(out)} topics)")


if __name__ == "__main__":
    main()

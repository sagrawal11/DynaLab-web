"""AI nanobody design package.

Phase 3 of the DynaLab pipeline: take a back-mapped intermediate (Phase 2),
ship the structure to a hosted AI design service (Tamarind Bio), and
return ranked binder candidates.

Modules:
  * ``tamarind_client.py`` -- thin REST wrapper around Tamarind Bio's API
                              (RFdiffusion / ProteinMPNN / AlphaFold-Multimer).
  * ``tamarind_mock.py``   -- in-process mock used by tests + offline runs.
  * ``pipeline.py``        -- orchestrator: chooses real vs. mock client,
                              executes the design plan, writes manifest.json.
"""

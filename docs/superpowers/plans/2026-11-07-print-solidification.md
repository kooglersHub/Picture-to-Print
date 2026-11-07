# Print solidification implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement task by task.

**Goal:** Turn a Trellis mesh into validated, texture-free print geometry.

**Architecture:** Python orchestrates an isolated MeshLib worker (default) or
headless Blender comparison and validates the exported STL with Trimesh. A 3MF
writer and JSON manifest support future shop jobs without provider coupling.

**Tech stack:** Python 3.11+, optional MeshLib 3.1.4.297, Blender 4.5 LTS, numpy,
trimesh, scipy, rtree, pytest, Ruff.

**Spec:** ../specs/2026-11-07-print-solidification-design.md

## Global constraints

100 mm longest dimension; 0.4 mm voxel; 300 s timeout; 150 million grid cells.
Always review_required; preserve external components; remove nested cavities.

## Review focus

Scene transforms, nonfinite settings, excessive resolution, interior cavities,
existing output directories and child-process failures must be tested.

## Task 1: Repair and exports

- [x] Write tests for settings, closed/open/hollow models, separate parts,
  scene transforms, 3MF units, failure manifests and existing output protection.
- [x] Run pytest and observe missing pipeline behavior fail.
- [x] Implement `prepare_model(source, output, settings, blender)` in
  `picture_to_print/pipeline.py`, geometry analysis/export in `geometry.py`,
  and a standalone Blender worker in `blender_worker.py`.
- [x] Run tests including real headless Blender; lint and format.

## Task 2: Runnable repository

- [x] Add CLI, packaging, CI and README with input/output examples, physical
  scaling and shop worker contract; clearly document limitations.
- [x] Run full suite, CLI help and a damaged-model command end to end.
- [ ] Commit and push main as requested after verifying the remote state.

## Execution decisions

- User-supplied research changed the primary method from Blender remesh to
  MeshLib HoleWindingRule; no new generative model or GPU run is required.
- Independent review reproduced unsafe vertex-only containment and float32
  corruption at distant origins. Added red/green regression tests; moved
  MeshLib containment into its isolated worker using collision-aware isInside,
  and center in float64 before scale/conversion. The Blender comparison retains
  ambiguous intersecting shells conservatively.
- Native repair has a timeout. The host job runner must enforce a total limit
  covering Python loading, analysis and export as documented in the README.

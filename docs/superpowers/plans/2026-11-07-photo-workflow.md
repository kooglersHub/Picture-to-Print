# Photo workflow implementation plan

> **For agentic workers:** Use superpowers:executing-plans task by task.

**Goal:** A token-protected hosted UI from photo upload through geometry generation to reviewed print downloads.

User expanded the initial local scope to a hosted website. See README.md and
CHECKPOINT.md for deployed architecture, validation evidence and remaining work.
**Architecture:** FastAPI plus a persistent single-worker job service; Modal
shape-only generation returns raw PLY; existing prepare_model validates exports.
**Tech stack:** Python 3.11+, FastAPI, Modal, Pillow, existing MeshLib processor.
**Spec:** ../specs/2026-11-07-photo-workflow-design.md

## Global constraints

25 MB uploads, 20 MP images, one GPU job at a time; no automatic retries.
Reuse weights volume. Never generate textures. Never claim automatic print certification.

## Review focus

Missing account access before billing, traversal/cross-origin writes, persisted
job recovery, failure cleanup, native/GPU timeouts and preservation of raw mesh.

## Tasks

- [ ] Write failing tests for real mesh-to-download jobs, injected photo-to-raw
  generation, failures, repair-only retry, upload limits, restart recovery and
  shape-only inference with an API-shaped fake pipeline.
- [ ] Implement shape sampling and pinned Modal image/function with a local
  command entrypoint. Inspect SDK APIs without initiating a paid GPU run.
- [ ] Implement job service, connection status, FastAPI routes, packaged local
  UI, interactive preview and Windows launcher.
- [ ] Run full tests, lint, UI smoke test and build/package checks. Independently
  review, fix actionable findings and document any unverified GPU step.
- [ ] Publish via PR to main per the user's repository instructions.

# GMK Schema v1 — Build 020 Changelog

## Added
- `VisualCoverageRuntime` in `gmk_assets.visual_coverage`.
- CLI command `gmk visual-coverage`.
- Independent runtime verification that every active Narration Beat has at least one production-ready `VERIFIED` Segment before advancing.
- Idempotent replay behavior at `VISUAL_COVERAGE_READY`.
- Build 020 regression coverage.

## Fixed
- Successful `ASSET_COVERAGE_REPORT` retests now resolve historical open coverage `QA_ISSUE` blockers through `QARuntime.resolve_issue`.
- This closes a latent lifecycle defect discovered while testing the real Build 018/019 completion path: old Build 017 coverage failures could otherwise keep `NO_BLOCKERS=false` after all missing media had been supplied.

## Preserved
- Frozen Schema v1 contract unchanged.
- No new Core Object or artifact contract.
- No Asset/Segment fabrication.
- P.T. pilot remains at `ASSET_RECON` until the two exact source-locked videos are supplied.

## Proven completion path
In an isolated copy of the P.T. workspace using real generated video bytes as test inputs only:

`ASSET_RECON → ASSET_CATALOG_READY → VISUAL_COVERAGE_READY`

The generated test media never enters the durable P.T. pilot workspace.

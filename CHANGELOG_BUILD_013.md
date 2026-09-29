# GMK Schema v1 — Changelog Build 013

## Added
- `gmk_narrative` runtime package.
- `RoughNarrativeRuntime`, `RoughNarrativeResult`, and `RoughNarrativeError`.
- CLI command `rough-narrative`.
- `docs/ROUGH_NARRATIVE.md`.
- `pilot/PT_ROUGH_NARRATIVE_INPUT.json`.
- durable rough-narrative report/status/doctor/next-action JSON.
- `ROUGH_NARRATIVE_REPORT.md`.
- Build 013 tests + `rough_narrative_smoke.py`.

## P.T. pilot changes
- Created 5 active Acts, 7 active Scenes, and 10 active research-bound Narration Beats.
- Created `NARRATIVE_SPINE_000001@1`.
- Bound the spine to nine exact audited Claims.
- Deferred two nonessential community theories (`CLM_000004`, `CLM_000010`).
- Kept `CLM_000011`–`CLM_000013` out of the graph because Research Audit marks them `PROHIBITED`.
- Entered `ROUGH_NARRATIVE_READY` through the real `ROUGH_NARRATIVE` Gate.
- Current next legal target is `VISUAL_REQUIREMENTS_READY`.

## Runtime behavior
- Claim eligibility is checked before opening the narrative transaction.
- Exact ACTIVE Claim versions are pinned into Beat bindings.
- Rough narrative replay is idempotent by `batch_id + plan SHA-256`.
- Reusing a batch ID with changed content fails closed.
- Final narration and visual requirements remain intentionally absent in this stage.

## Validation
- Schema registry: 75 contracts, PASS.
- Structural/Semantic validation: PASS.
- Rough Narrative smoke: PASS.
- Repo layout audit: PASS.
- Full pytest: **108 passed**.

## Architecture
No frozen Schema v1 contract change.

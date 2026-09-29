# GMK Schema v1 — Build 030 Changelog

## Added
- `gmk_render.RenderQAStageRuntime`.
- CLI command `gmk render-shot-qa`.
- Actual local final-render handoff with `ffprobe`, immutable SHA-256 media copy, and Project Production Lock binding.
- Explicit Shot QA review coverage: one review entry is required for every current ACTIVE Shot.
- Immutable workspace Shot-QA review ledger keyed by `batch_id + plan SHA-256`.
- Per-review QA profile hashes binding reviewer/time/findings to each persisted `SHOT_QA` report.
- Project-level `QA_BASELINE` creation after render + Shot QA.
- Build 030 integration tests for happy path, incomplete review rejection, FAIL→PASS retest, and idempotent replay.

## Fixed
- `QA_REPORT_RESULT` Gate evaluation now uses the latest current QA report per scope instead of allowing historical FAIL/WARN reports to poison all future retests.
- A PASS Shot retest resolves prior unresolved Shot QA issues using the new PASS report as verification evidence before transition.

## Runtime behavior
- Requires project state `PRODUCTION_RENDER` for first execution.
- Requires one exact current valid Project `PRODUCTION_LOCK_MANIFEST`.
- Requires actual readable video bytes; page metadata or placeholder bytes cannot satisfy the render handoff.
- Copies the exact rendered media into immutable workspace `media/renders/<sha256>.<ext>` storage.
- Queues/execut es Final Render through the existing `RenderRuntime` using the exact Project Production Lock.
- Requires explicit reviewer attribution and one review record per active Shot.
- Creates one current `SHOT_QA` report per reviewed Shot against the exact project `RENDER_OUTPUT`.
- Advances `PRODUCTION_RENDER → SHOT_QA_PASSED` only when both existing `RENDER` and `SHOT_QA` Gates return `PASS` and no blockers remain.
- Failed QA remains durable and does not transition. A later explicit retest may supersede the historical report only through a newer current QA snapshot and verified issue resolution.

## Contract status
No Core Object, Artifact contract, Project State, Gate ID, or transition was added.

`GMK_SCHEMA_V1_CONTRACT = FROZEN_WITH_ERRATA_024_025_029`

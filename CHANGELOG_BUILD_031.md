# CHANGELOG — GMK Schema v1 Build 031

## Added
- `gmk_qa.SceneQAStageRuntime`.
- CLI command `gmk scene-qa`.
- explicit Scene QA review ledger under `reviews/scene_qa/`.
- required Scene checklist dimensions: shot continuity, visual continuity, audio continuity, narrative flow, and coverage.
- exact aggregation of current PASS Shot QA evidence per Scene.
- Build 031 Scene QA integration tests.
- `SCENE_QA_RUNTIME_REPORT.md`.

## Runtime behavior
- runs only from `SHOT_QA_PASSED` (or exact idempotent replay from `SCENE_QA_PASSED`).
- requires current `RENDER` and `SHOT_QA` gates to remain PASS before Scene QA begins.
- requires every current Scene Plan to resolve to current active Shots.
- requires each Shot's latest `SHOT_QA` report to be PASS and all Scene evidence to reference one exact Final Render output.
- requires explicit review coverage for every active Scene.
- converts checklist WARN/FAIL results into contract-valid Scene QA findings rather than treating an empty findings list as sufficient evidence of review.
- resolves prior Scene QA issues only after a later PASS verification report.
- advances through the existing `SCENE_QA` Gate only when its latest per-Scene reports are PASS.
- supports idempotent replay and batch-ID collision detection.

## Compatibility
- no Core Object added.
- no Artifact contract added or changed.
- no Project State or Gate ID added.
- Schema registry remains **79 contracts**.
- Schema status remains `FROZEN_WITH_ERRATA_024_025_029`.

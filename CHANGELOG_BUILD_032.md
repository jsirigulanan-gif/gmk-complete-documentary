# GMK Schema v1 — Build 032 Changelog

## Added
- `gmk_qa.full_film_stage.FullFilmQAStageRuntime`.
- CLI command `gmk full-film-qa`.
- Explicit three-pass Full Film QA review normalization and immutable review ledger.
- Exact current Scene-QA/Final-Render/Production-Lock evidence binding.
- Review-profile SHA-256 pinning for Viewer Experience, Production Integrity, Delivery Integrity, and aggregate Full Film QA.
- Full Film QA retest resolution for prior verified issues.
- Build 032 integration tests and Full Film QA smoke test.
- `FULL_FILM_QA_RUNTIME_REPORT.md`.

## Compatibility
- Existing `QARuntime.evaluate_full_film(...)` calls remain compatible; `qa_profiles` is optional.
- Build 009 release/orchestrator tests remain PASS.
- Build 030–031 QA stage tests remain PASS.
- No schema contract change.

## State boundary
Build 032 may advance only:

`SCENE_QA_PASSED → FULL_FILM_QA_PASSED`

The real P.T. pilot remains fail-closed at `ASSET_RECON`.

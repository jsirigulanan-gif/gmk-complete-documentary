# GMK Schema v1 — Build 034 Changelog

## Added
- `gmk_release.final_stage.ReleaseFinalStageRuntime`.
- CLI command `gmk release-finalize`.
- Authorized `LOCAL_EXPORT` publish adapter for CLI use; it performs a real local delivery side effect without claiming a remote-platform publish.
- Exact binding from the latest human-approved `DELIVERY_REVIEW_PACKAGE` to PUBLISH, immutable `RELEASE`, `FINAL_PROJECT` checkpoint, and `PROJECT_COMPLETED`.
- Release/finalization replay ledger and batch-collision protection.
- Build 034 integration tests.
- `RELEASE_FINAL_STAGE_REPORT.md`.

## Fixed
- `ReleaseRuntime.publish()` no longer creates duplicate immutable `RELEASE` objects when a successful PUBLISH Operation is replayed.
- `ReleaseRuntime.finalize_project()` is now idempotent after `PROJECT_COMPLETED`; replay returns the existing valid `FINAL_PROJECT` checkpoint instead of creating another.

## Boundary
Build 034 does not pretend that YouTube or another remote platform was published when no authorized remote adapter exists. The CLI supports `LOCAL_EXPORT` only. External adapters may still call `ReleaseRuntime.publish()` through the existing Operation boundary when separately authorized.

## Architecture
- No Core Object added.
- No Project State added.
- No Gate ID or transition added.
- No Artifact contract added or changed.
- Schema status remains `FROZEN_WITH_ERRATA_024_025_029_033`.

## Proven terminal path
`DELIVERY_READY → PUBLISH → RELEASED RELEASE → FINAL_PROJECT → PROJECT_COMPLETED`

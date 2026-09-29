# GMK Schema v1 — Build 036 Changelog

## Focus
P.T. Pilot Execution Pack: operationalize the real external-media boundary without adding a new production stage or bypassing any Gate.

## Added
- `gmk_pilot.PilotExecutionRuntime`
- CLI `pilot-execution-pack`
- CLI `pilot-media-preflight`
- CLI `pilot-media-execute`
- public non-mutating `MediaHandoffRuntime.validate_plan()` path
- generated `pilot/PT_EXECUTION_PACK/` with exact source locks, handoff template, and runbook
- P.T. execution-pack smoke and Build 036 integration tests
- audit checks for current README baseline and P.T. execution-pack continuity

## Runtime behavior
- `prepare` derives the exact pending media set from the durable P.T. workspace; it does not hard-code Asset IDs as authority.
- `preflight` runs the same ffprobe, source-lock, checksum, and segment-range validation as the real handoff without mutating the workspace.
- `execute` accepts only a complete passing source-locked handoff and automatically advances only through the non-human `VISUAL_COVERAGE` stage.
- Human approval boundaries after Visual Coverage are never auto-created or skipped.
- replay after `VISUAL_COVERAGE_READY` is idempotent and does not duplicate acquisition/coverage records.

## P.T. pilot
The real durable pilot remains at `ASSET_RECON` because the two actual external video files are still not present:
- `LISA_X_DIRECT_VERIFIED`
- `TGA_VIDEO`

The execution pack now records the exact source/result/Asset identities and generates a ready-to-fill handoff plan from that current state.

## Architecture
- no Core Object added
- no Project State added
- no Gate ID added
- no schema/artifact contract added or changed
- schema remains `FROZEN_WITH_ERRATA_024_025_029_033`

## Final validation
- Build 036 integration: 6 PASS (heavy cases independently)
- Build 018: 4 PASS
- Build 019: 3 PASS
- Build 020: 3 PASS (partitioned)
- Build 035 audit regression: 3 PASS
- Quick Audit: 16 PASS / 0 FAIL / 0 TIMEOUT / 1 WARN
- execution-pack smoke: PASS
- packaged-template preflight: fail-closed and non-mutating

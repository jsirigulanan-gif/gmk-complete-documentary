# GMK Schema v1 — Build 037 Changelog

## Added
- `gmk_pilot.PilotMediaIntakeRuntime`.
- CLI `pilot-media-intake-init`.
- CLI `pilot-media-intake-build`.
- `pilot/PT_MEDIA_INTAKE/` source-locked staging pack generated from the real P.T. workspace.
- Per-candidate intake slots for `LISA_X_DIRECT_VERIFIED` and `TGA_VIDEO`.
- Human inspection worksheet, immutable SHA-256 receipt, ffprobe technical capture, and compiled handoff-plan output.
- Audit check that P.T. intake-pack candidate/source locks exactly match the existing execution pack.
- Build 037 integration tests.

## Boundary
- Intake never downloads media.
- Intake never decides visual identity from a filename or checksum alone.
- Exactly one authorized local video is accepted per source-locked slot.
- Human inspection fields are mandatory before plan compilation.
- The existing `MediaHandoffRuntime.validate_plan()` remains authoritative for source URL, source-lock range, checksum, and media validation.
- `pilot-media-intake-build` does not mutate `PT_WORKSPACE`.
- Actual state mutation still occurs only through the existing `pilot-media-execute` path.

## Schema
No schema/artifact contract changes. Schema remains `FROZEN_WITH_ERRATA_024_025_029_033` with 80 contracts.

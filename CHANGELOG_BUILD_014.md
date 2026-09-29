# CHANGELOG — GMK Schema v1 Build 014

## Added
- `VisualRequirementsRuntime` in `gmk_narrative.visual_requirements`.
- CLI command: `gmk visual-requirements`.
- P.T. visual-requirement input and durable result/replay/status/next-action/doctor reports.
- Build 014 visual requirement tests and smoke test.
- `VISUAL_REQUIREMENTS_REPORT.md`.

## Runtime behavior
- Pins the visual-requirement plan to an exact `NARRATIVE_SPINE` reference and hash.
- Requires exact rough-narrative Beat baseline before first application.
- Requires complete one-to-one visual requirement coverage for every active `NARRATION_BEAT`.
- Creates new Beat versions, promotes them deliberately, and moves workflow state to `VISUAL_REQUIREMENT_READY`.
- Rejects missing, extra, duplicate, invalid, or placeholder requirements.
- Rejects final narration appearing before visual coverage.
- Supports idempotent replay and batch-ID collision detection.
- Transitions through the existing `VISUAL_REQUIREMENTS` Gate to `VISUAL_REQUIREMENTS_READY`.

## P.T. pilot result
- 10/10 active Beats have visual requirements.
- Priority: 6 CRITICAL, 3 MAJOR, 1 STANDARD.
- Asset needs: VIDEO 8, DOCUMENT 8, STILL 8, TECHNICAL_REFERENCE 2, THREE_D_REFERENCE 1.
- Project state: `VISUAL_REQUIREMENTS_READY`.
- Next legal target: `ASSET_RECON`.

## Compatibility
- No Core Object added.
- No Schema contract added or changed.
- Frozen `GMK_SCHEMA_V1_CONTRACT` remains intact.
- Build 013 rough-narrative compatibility tests/smoke were updated only to accept legitimate forward state progression into `VISUAL_REQUIREMENTS_READY`.

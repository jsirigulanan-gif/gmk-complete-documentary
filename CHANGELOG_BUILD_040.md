# GMK Schema v1 — Build 040 Changelog

## Added
- `gmk_operator` desktop operator surface built with Python/Tkinter.
- Windows launchers: `INSTALL_GMK.cmd` and `START_GMK.cmd`.
- Thai quick-start guide: `README_START_HERE_TH.md`.
- GUI controls for P.T. readiness, media-slot selection, human inspection editing, preflight, explicit media execution, Quick Audit, and runtime checks.
- persistent non-authoritative operator config for an explicitly selected `ffprobe` executable.
- `gmk-operator` console entry point.
- operator smoke test and Build 040 regression coverage.

## Media-tool hardening
- Added `gmk_runtime.media_tools` as the shared ffprobe resolver.
- Resolution order is explicit `GMK_FFPROBE`, normal PATH, then a bounded set of common Windows locations.
- Media Handoff, P.T. Intake, Voice and Render QA now resolve ffprobe through the same helper.
- No media-validation semantics were loosened.

## Operator safety
- Selecting a video only stages a local copy in its exact source-locked slot; it does not mutate `PT_WORKSPACE`.
- Source identity is not inferred from a filename.
- Human inspection remains mandatory.
- Execute is enabled logically only after authoritative readiness returns `READY_TO_EXECUTE` and requires an explicit confirmation dialog.
- Execution still stops at `VISUAL_COVERAGE_READY`; later Human Approval boundaries remain unchanged.

## Compatibility
- No Core Object, Project State, Gate ID, enum, or artifact contract added.
- Schema remains `FROZEN_WITH_ERRATA_024_025_029_033` with 80 contracts.
- P.T. packaged workspace remains `ASSET_RECON`, manifest version 104, with no Lisa/TGA media bytes embedded.

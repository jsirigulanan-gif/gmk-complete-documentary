# GMK Schema v1 — Build 039 Changelog

## Added
- `gmk_pilot.readiness.PilotReadinessRuntime`.
- CLI command `gmk pilot-readiness`.
- packaged `pilot/PT_PILOT_READINESS/` snapshot for the real P.T. workspace.
- read-only readiness states: `BLOCKED_MEDIA`, `BLOCKED_INSPECTION`, `BLOCKED_PREFLIGHT`, `READY_TO_EXECUTE`, `ALREADY_ADVANCED`.
- per-slot visibility for media presence, inspection completeness, source-lock match and locked locator.

## Runtime behavior
- Reads the current durable P.T. state and intake pack without mutating `PT_WORKSPACE`.
- When all local inputs exist, runs one authoritative intake/source-lock validation pass in a temporary output directory.
- Uses `CURRENT_MANIFEST.json` SHA-256 as a non-mutation guard.
- Produces JSON and Markdown operator reports with the exact next action.
- Does not auto-download media, infer visual identity from filenames, or execute acquisition.

## Performance hardening
- Removed redundant readiness-time validation layers. `PilotMediaIntakeRuntime.build()` already delegates to `MediaHandoffRuntime.validate_plan`, so Build 039 does not immediately repeat the same validation through `PilotExecutionRuntime.preflight`.
- Removed the redundant post-check Cold Start; immutable manifest-pointer hash comparison provides the non-mutation guard.

## P.T. packaged snapshot
- Project state: `ASSET_RECON`.
- Manifest version: `104`.
- Readiness: `BLOCKED_MEDIA`.
- Pending slots: `LISA_X_DIRECT_VERIFIED`, `TGA_VIDEO`.
- Workspace mutation: none.

## Compatibility
- No Core Object, Project State, Gate ID, enum, or artifact contract added.
- Schema remains `FROZEN_WITH_ERRATA_024_025_029_033` with 80 contracts.

# GMK Schema v1 — Build 038 Changelog

## Added
- `gmk_pilot.PilotMediaProcessRuntime`.
- CLI `pilot-media-process`.
- `PT_MEDIA_PROCESS_REPORT.json` output.
- non-mutating one-command intake build + receipt + authoritative preflight.
- explicit `--execute` boundary for acquisition + Visual Coverage.
- static audit check for the packaged/documented media processor.

## Hardened
- `PilotExecutionRuntime.execute()` no longer performs redundant Cold Starts after stage runtimes already return exact committed project state and manifest version.
- replay at `VISUAL_COVERAGE_READY` skips intake rescanning and does not mutate state.
- `ASSET_CATALOG_READY` can continue directly to Visual Coverage without pretending media is still pending.

## Boundary
- no media download;
- no automatic human inspection;
- no authenticity decision from filename/checksum alone;
- no state mutation without explicit `--execute`;
- no Human Approval stage is crossed automatically.

## Schema
No schema/artifact contract change. Schema remains `FROZEN_WITH_ERRATA_024_025_029_033` with 80 contracts.

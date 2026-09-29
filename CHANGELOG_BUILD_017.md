# Changelog — Build 017

## Added
- `gmk_assets.verification.AssetAcquisitionRuntime`
- CLI command `asset-acquire`
- immutable acquired-byte storage under workspace `media/originals/`
- SHA-256 verification before `FILE_VERIFIED`
- catalog transition support after verified bytes
- SEGMENT creation only after file verification
- strict `ASSET_COVERAGE_REPORT`
- `LOCAL_FILE`, `WEB_TEXT_SNAPSHOT`, and `DEFERRED` acquisition modes
- Build 017 regression tests

## Fixed
- OPERATION audit-anchor dependency cycle no longer propagates stale state back into the subject Asset.
- SEARCH_RESULT selection/promotion-only revisions are `NON_PRODUCTION` for dependency impact.
- Asset acquisition pins the terminal exact Operation version rather than leaving a stale planned Operation ref.

## Pilot
- 8 document evidence Assets cataloged with immutable checksummed snapshots.
- 8 verified Segments created.
- 2 selected video Assets remain acquisition-pending; no substitution performed.
- Visual coverage intentionally remains FAIL.

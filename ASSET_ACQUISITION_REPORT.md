# GMK Build 017 — Asset Acquisition / Verification Report

## Result

Build 017 implements the acquisition-verification boundary without pretending that provider page metadata is original media.

### P.T. pilot execution

- Batch: `PT_ASSET_ACQUISITION_017`
- Project state after execution: `ASSET_RECON`
- Selected Assets: 10
- Cataloged / checksummed evidence Assets: 8
- Deferred direct-media Assets: 2
- Verified Segments created: 8
- Acquisition Operations: 8 `SUCCEEDED`, 2 `PLANNED`
- `ASSET_COVERAGE_REPORT`: `FAIL` (expected, because two selected video Assets still lack acquired media bytes)
- Cold Start after persistence: PASS
- Manifest version: 104

## Acquired representations

The eight document selections were captured as bounded `WEB_TEXT_SNAPSHOT` evidence representations. Each file is immutable in the workspace, has a SHA-256 checksum, and is explicitly marked `origin_bytes=false`. This is a traceable evidence capture, not a claim that the runtime downloaded publisher-origin HTML bytes.

The two selected video Assets remain `ACQUISITION_PENDING`:

1. `LISA_X_DIRECT_VERIFIED` — Lance McDonald original embedded camera-hack media.
2. `TGA_VIDEO` — selected audiovisual stage statement.

No secondary clip or page metadata was silently substituted for either selected video.

## Lifecycle proven

`ACQUISITION_PENDING → ACQUIRED → FILE_VERIFIED → CATALOGED` is now executable when bytes are present. `SEGMENT` creation occurs only after immutable verified bytes exist.

## Dependency-runtime fixes

Build 017 found two implementation-level stale-cycle problems during Cold Start and patched them without changing the frozen architecture:

- OPERATION objects are a dependency-propagation boundary because their subject is an audit anchor; operation lifecycle changes must not recursively stale their subject Asset.
- SEARCH_RESULT lifecycle-only revisions (`candidate_state`, promotion bookkeeping) are classified `NON_PRODUCTION`; promotion does not change the discovered visual evidence that an Asset was derived from.

These fixes implement the frozen principle that stale propagation is based on meaning and changed paths, not version numbers alone.

## Coverage boundary

Eight Beats now have verified production-planning evidence Segments. The visual coverage report remains FAIL until the two selected video Assets are acquired and exact usable moments can be verified. The runtime therefore does **not** transition the project to `ASSET_CATALOG_READY`.

## Validation addendum

- `tools/asset_acquisition_smoke.py`: PASS after Cold Start.
- CLI replay (`asset-acquire` with the same batch): PASS with `idempotent_replay=true`; no duplicate Assets or Segments were created.

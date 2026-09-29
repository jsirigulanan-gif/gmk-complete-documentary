# GMK Schema v1 — Build 018 Changelog

## Added
- `MediaHandoffRuntime` for authorized/manual direct-video byte ingestion.
- `asset-media-handoff` CLI command.
- ffprobe-based video validation and technical metadata extraction.
- SHA-256 handoff verification.
- exact `VIDEO_TIME_RANGE` validation against probed duration.
- complete pending-video-set enforcement.
- P.T. direct-media handoff input template.
- Build 018 regression tests.

## P.T. pilot
- Durable pilot remains at `ASSET_RECON` because actual Lisa/TGA media bytes are not available inside this execution environment.
- 8 Assets remain cataloged, 2 selected videos remain acquisition-pending, 8 Segments remain verified.
- The system now has a fail-closed path that will close both pending videos and transition to `ASSET_CATALOG_READY` only after real supplied bytes pass validation.

## Preserved
- No new Core Object.
- No frozen schema or Gate contract change.
- No fabricated media bytes.
- No page/metadata substitution for selected direct video.
- No GitHub repository created.

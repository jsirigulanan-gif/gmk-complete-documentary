# GMK Build 018 — Direct Media Handoff Report

## Scope
Build 018 closes the implementation gap between a selected direct-video Asset and externally/authorized acquired media bytes. It does **not** claim that the two P.T. videos have been downloaded in this build.

## Added
- `gmk_assets.media_handoff.MediaHandoffRuntime`
- CLI command `gmk asset-media-handoff`
- `ffprobe` validation for supplied video bytes
- SHA-256 verification before delegation to the existing immutable `LOCAL_FILE` acquisition path
- complete-set enforcement for all currently pending selected video Assets
- exact `VIDEO_TIME_RANGE` bounds validation before Segment creation
- pilot handoff template for the two remaining P.T. videos
- Build 018 tests covering successful closure with real synthetic video bytes, non-video rejection, and out-of-bounds Segment rejection

## Current P.T. pilot state
The durable pilot itself remains intentionally unchanged from Build 017:

```text
Project State                 ASSET_RECON
Cataloged Assets              8
Pending selected video Assets 2
Verified Segments             8
Asset Coverage                FAIL (expected)
```

Pending handoff requirements:

1. `LISA_X_DIRECT_VERIFIED` — original Lance McDonald camera-hack video bytes.
2. `TGA_VIDEO` — selected Game Awards audiovisual statement bytes.

## Completion behavior
When both authorized files are supplied with inspected exact time ranges, `asset-media-handoff`:

1. rejects missing/empty/non-video inputs;
2. validates container/video stream/duration with `ffprobe`;
3. validates the requested exact video range against real duration;
4. computes SHA-256;
5. delegates to the existing `AssetAcquisitionRuntime` `LOCAL_FILE` path;
6. advances each Asset through `ACQUIRED → FILE_VERIFIED → CATALOGED`;
7. creates verified production-ready Segments;
8. regenerates `ASSET_COVERAGE_REPORT`;
9. allows the existing Gate Engine to enter `ASSET_CATALOG_READY` only when the coverage gate genuinely passes.

## Boundary
No webpage text, embed metadata, thumbnail, or URL is treated as original video bytes. No Project State advance is recorded in the packaged P.T. workspace until actual media files are supplied.

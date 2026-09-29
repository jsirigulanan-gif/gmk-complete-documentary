# GMK Schema v1 — Build 019 Changelog

## Added
- Source-locked media handoff enforcement for pending direct-video Assets.
- Handoff requirements now expose the exact immutable origin `SEARCH_RESULT` ref, canonical discovery URL, source family, source title, and inspected candidate locator.
- Canonical source substitution guard: a locally supplied file cannot be accepted under a different selected candidate URL.
- Inspected-range guard: when the selected candidate was inspected as a bounded `VIDEO_TIME_RANGE`, handoff segments must stay inside that exact inspected range.
- Build 019 tests covering immutable source locks, source substitution rejection, and inspected-range enforcement.

## P.T. pilot source locks
- `LISA_X_DIRECT_VERIFIED` → `SR_000031@2` → Lance McDonald original-creator post (`twitter.com/manfightdragon/status/1170860592233472001`).
- `TGA_VIDEO` → `SR_000024@2` → selected YouTube reupload (`youtube.com/watch?v=PKl5rYdwM6c`), inspected range `0–135s` with key moment `55s`.

## Boundary
- No network downloader was added.
- No webpage, embed metadata, synthetic video, or alternate clip is promoted as acquired original media.
- The durable P.T. pilot remains `ASSET_RECON` with two `ACQUISITION_PENDING` video Assets until authorized local media bytes are supplied.
- No Core Object, Schema contract, Gate ID, or frozen architecture change.

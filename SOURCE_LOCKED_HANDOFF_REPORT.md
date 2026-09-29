# GMK Build 019 — Source-Locked Media Handoff Report

## Result
Build 019 hardens the Build 018 authorized/manual video handoff so acquisition cannot silently substitute a different clip for a selected candidate.

### P.T. durable state
```text
Project State                  ASSET_RECON
Selected Assets                10
Cataloged Assets                8
Pending VIDEO Assets            2
Verified Segments               8
Asset Coverage                  FAIL (expected / fail-closed)
Schema v1                       FROZEN
```

## Exact pending source locks

### LISA_X_DIRECT_VERIFIED
- Asset: `AST_000004@2`
- Immutable origin Search Result: `SR_000031@2`
- Source family: `ORIGINAL_CREATOR`
- Canonical locator: `https://twitter.com/manfightdragon/status/1170860592233472001`
- Candidate locator: `FULL_SOURCE`
- Constraint: evidence supports Lisa's attachment/following relationship; no invented exact numerical distance.

### TGA_VIDEO
- Asset: `AST_000008@2`
- Immutable origin Search Result: `SR_000024@2`
- Source family: `REUPLOAD`
- Canonical locator: `https://www.youtube.com/watch?v=PKl5rYdwM6c`
- Inspected candidate range: `0–135s`
- Key moment: `55s`
- Constraint: any production handoff segment must remain inside the inspected range.

## Enforcement
A media handoff now fails closed if:
1. the pending Asset lacks an immutable origin Search Result;
2. the selected Search Result lacks a canonical `WEB_URI`;
3. the supplied `source_url` differs from that exact selected locator;
4. the requested segment exceeds the candidate range already inspected during Asset Recon;
5. any Build 018 byte/video/range/SHA-256 validation fails.

## External-source status
Public web verification confirms that the Lance McDonald post is the September 9, 2019 P.T. camera-hack source discussed by contemporary coverage. The selected `PKl5rYdwM6c` YouTube locator resolves to a video titled “Geoff Keighley Says Hideo Kojima Wasn't Allowed to Come to The Game Awards 2015.” These checks validate locator identity only; they do not fabricate or acquire media bytes.

## Next legal action
Supply authorized local bytes for both exact source locks, then run `asset-media-handoff`. A successful handoff delegates to the existing acquisition runtime for SHA-256 verification, cataloging, Segment creation, coverage evaluation, and Gate-controlled transition to `ASSET_CATALOG_READY`.

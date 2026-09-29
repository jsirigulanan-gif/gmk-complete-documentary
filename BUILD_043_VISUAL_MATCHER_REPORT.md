# Build 043 Visual Matcher Report

## Objective

Close the remaining Build 042 gap where footage with no reliable transcript/caption timestamp could be ranked by metadata but could not safely enter automatic production.

## Result

Implemented a pixel-grounded visual semantic stage. The system samples real frames from already acquired candidate video, sends those frames to a configured vision provider, scores the returned visible-content description against the Narration Beat's `viewer_must_see`, entity terms, claims and viewer takeaway, and nominates timestamp windows only when the visual score meets threshold.

Automatic production now follows an evidence hierarchy:

1. Transcript/caption timestamp match.
2. Visual-semantic frame match.
3. Unresolved.

Metadata-only candidates never become production clips merely because their title or description looks relevant.

## Local vision provider

`OllamaVisionProvider` uses localhost only and requires an explicit model (`GMK_VISION_MODEL`). This keeps the core provider-pluggable and avoids silently imposing a large ML dependency on operator machines.

## Evidence emitted

For visual matching, the runtime writes:

- `FRAME_INSPECTION_MANIFEST.json`
- `VISUAL_SEMANTIC_MATCH.json`
- sampled frame paths and checksums
- provider identity
- per-frame descriptions
- score breakdowns
- nominated start/end/key timestamps
- report SHA-256

Auto-production then records the visual match manifest path and `selection_mode=VISUAL_SEMANTIC` in the production manifest.

## Compatibility

Legacy Build 042 transcript-driven auto-production remains unchanged in behavior. Older tests constructing `BeatResearchResult` without `search_intent` remain valid because the new field is optional and appended with a default.

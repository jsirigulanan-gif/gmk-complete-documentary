# P.T. Pilot Execution Runbook — Build 036

Current state: `ASSET_RECON`

## Hard boundary

Do not substitute screenshots, webpage text, metadata, unrelated reuploads, or synthetic test media for the two source-locked videos.

## Required media

### `LISA_X_DIRECT_VERIFIED`
- Asset: `AST_000004@2`
- Source result: `SR_000031@2`
- Canonical source: https://twitter.com/manfightdragon/status/1170860592233472001
- Source family: `ORIGINAL_CREATOR`
- Rights status: `COMMENTARY_REVIEW`
- Locked locator: `{"type": "FULL_SOURCE"}`

### `TGA_VIDEO`
- Asset: `AST_000008@2`
- Source result: `SR_000024@2`
- Canonical source: https://www.youtube.com/watch?v=PKl5rYdwM6c
- Source family: `REUPLOAD`
- Rights status: `COMMENTARY_REVIEW`
- Locked locator: `{"end_seconds": 135, "key_seconds": 55, "start_seconds": 0, "type": "VIDEO_TIME_RANGE"}`

## Procedure

1. Copy `PT_MEDIA_HANDOFF_INPUT.json` and replace each `local_path` with an authorized local video file.
2. Inspect the exact usable moment. Fill `start_seconds`, `end_seconds`, and `key_seconds`; do not guess.
3. Optionally fill `expected_sha256` from an independently recorded checksum.
4. Run preflight. It performs ffprobe, range, source-lock, and checksum checks without mutating the workspace.
5. Only after preflight reports `ready: true`, run execute.

```bash
python -m gmk_cli pilot-media-preflight --workspace pilot/PT_WORKSPACE --input PT_MEDIA_HANDOFF_INPUT.json --json
python -m gmk_cli pilot-media-execute --workspace pilot/PT_WORKSPACE --input PT_MEDIA_HANDOFF_INPUT.json --json
```

A successful execute closes the two media acquisitions and automatically advances only through `VISUAL_COVERAGE_READY`. Script/TTS/Voice and every Human Approval boundary remain separate.

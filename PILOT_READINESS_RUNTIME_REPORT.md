# GMK Build 039 — P.T. Pilot Readiness Runtime Report

## Purpose
Build 039 turns the external-media boundary into a single operator-facing readiness view. The production pipeline is already implemented through `PROJECT_COMPLETED`; the real P.T. pilot is still correctly blocked at `ASSET_RECON` until two exact source-locked videos and their human inspection records are supplied.

## Readiness states
- `BLOCKED_MEDIA` — one or more candidate slots do not contain exactly one local video.
- `BLOCKED_INSPECTION` — local media exists, but the human worksheet is incomplete or its declared source URL does not match the source lock.
- `BLOCKED_PREFLIGHT` — media + worksheet are complete, but authoritative source-lock/checksum/technical/range validation fails.
- `READY_TO_EXECUTE` — authoritative non-mutating validation passes; operator may explicitly run `pilot-media-process --execute`.
- `ALREADY_ADVANCED` — the project is already beyond `ASSET_RECON`; media should not be re-imported.

## Non-mutation boundary
`pilot-readiness` never calls media acquisition or any project-state transition. It fingerprints `CURRENT_MANIFEST.json` before inspection and requires the fingerprint to remain unchanged. Authoritative validation output is written only to a temporary directory until the user explicitly executes the existing media processor.

## Current packaged P.T. result
```text
Project State        ASSET_RECON
Manifest Version     104
Readiness            BLOCKED_MEDIA
Ready To Execute     NO
Missing Media        LISA_X_DIRECT_VERIFIED, TGA_VIDEO
```

The packaged snapshot is available under `pilot/PT_PILOT_READINESS/`.

## Operator command
```bash
python -m gmk_cli pilot-readiness \
  --workspace pilot/PT_WORKSPACE \
  --intake-dir pilot/PT_MEDIA_INTAKE \
  --output-dir pilot/PT_PILOT_READINESS \
  --json
```

Exit code is zero only for `READY_TO_EXECUTE` or `ALREADY_ADVANCED`. Blocked states return non-zero so the command can be used safely in scripts.

## Validation
- Build 039 integration tests: 5/5 PASS.
- READY_TO_EXECUTE validation path after optimization: ~9 seconds in the build environment with probeable test videos.
- Packaged empty-intake result: `BLOCKED_MEDIA`, non-mutating.
- Schema contracts unchanged: 80.

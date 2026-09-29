# GMK Operator Handoff — Build 040

## Current baseline
- Current package baseline: **Build 040**
- Core pipeline: **runtime-complete through `PROJECT_COMPLETED`**
- Schema status: `FROZEN_WITH_ERRATA_024_025_029_033`
- P.T. pilot state: `ASSET_RECON`
- P.T. external media still required:
  - `LISA_X_DIRECT_VERIFIED`
  - `TGA_VIDEO`
- Execution pack: `pilot/PT_EXECUTION_PACK/`
- Preferred operator intake: `pilot/PT_MEDIA_INTAKE/`

Do not advance the real P.T. workspace by substituting page metadata, screenshots, unrelated reuploads, test fixtures, or fabricated media bytes for these two source-locked videos.

## Preferred CachyOS operator flow

1. Run `./INSTALL_GMK.sh` once.
2. Open **GMK P.T. Operator** from the app launcher or run `./START_GMK.sh`.
3. Use the Lisa/TGA tabs to choose media and complete human inspection.
4. Refresh readiness, run Preflight, and Execute only when `READY_TO_EXECUTE`.

## Windows operator flow
1. Extract the ZIP.
2. Run `INSTALL_GMK.cmd` once.
3. Run `START_GMK.cmd`.
4. Select Lisa/TGA media from their tabs, fill inspection fields, Refresh, Preflight, then Execute only when readiness is `READY_TO_EXECUTE`.

The CLI workflow below remains fully supported and authoritative.

## First commands after handoff
```bash
python -m gmk_cli audit --profile QUICK --json
python -m gmk_cli status --workspace pilot/PT_WORKSPACE --json
python -m gmk_cli doctor --workspace pilot/PT_WORKSPACE --json
python -m gmk_cli pilot-media-intake-init \
  --workspace pilot/PT_WORKSPACE \
  --intake-dir pilot/PT_MEDIA_INTAKE \
  --json
```

## When the two authorized video files are available
1. Place exactly one file in each source-locked candidate slot:
   - `pilot/PT_MEDIA_INTAKE/LISA_X_DIRECT_VERIFIED/`
   - `pilot/PT_MEDIA_INTAKE/TGA_VIDEO/`
2. Inspect the actual media and fill `pilot/PT_MEDIA_INTAKE/PT_MEDIA_INSPECTION_WORKSHEET.json`.
3. Record the operator name, inspection note, exact usable time range, visual-content description, and match reason.
4. Run the one-command processor without `--execute` first:

```bash
python -m gmk_cli pilot-media-process \
  --workspace pilot/PT_WORKSPACE \
  --intake-dir pilot/PT_MEDIA_INTAKE \
  --inspection pilot/PT_MEDIA_INTAKE/PT_MEDIA_INSPECTION_WORKSHEET.json \
  --json
```

This creates/refreshes `PT_MEDIA_INTAKE_RECEIPT.json`, `PT_MEDIA_HANDOFF_READY.json`, and `PT_MEDIA_PROCESS_REPORT.json`, and performs the authoritative preflight without mutating `PT_WORKSPACE`.

5. Review the receipt and process report. Only when `ready` is `true`, rerun explicitly with `--execute`:

```bash
python -m gmk_cli pilot-media-process \
  --workspace pilot/PT_WORKSPACE \
  --intake-dir pilot/PT_MEDIA_INTAKE \
  --inspection pilot/PT_MEDIA_INTAKE/PT_MEDIA_INSPECTION_WORKSHEET.json \
  --execute \
  --json
```

A successful execution advances automatically only to `VISUAL_COVERAGE_READY`. Script/TTS/Voice and every later Human Approval boundary remain separate.

## Proven downstream path
The isolated runtime has already been proven through:

`VISUAL_COVERAGE_READY → SCRIPT_READY → TTS_READY → VOICE_LOCKED → DESIGN_DNA_APPROVED → SCENE_PLAN_READY → SHOT_PLAN_READY → HTML_APPROVED → PRODUCTION_RENDER → SHOT_QA_PASSED → SCENE_QA_PASSED → FULL_FILM_QA_PASSED → DELIVERY_READY → PROJECT_COMPLETED`.

## Human approvals
Do not auto-create human decisions. Voice, Design DNA, HTML Preview, Production Lock, and Delivery/Release approvals must be made against exact current review-package hashes.

## Publish boundary
The built-in final-stage adapter is `LOCAL_EXPORT`. Remote publication requires an explicitly authorized external adapter/integration.

## Package hygiene
Before distribution, remove `__pycache__`, `.pytest_cache`, `*.pyc`, and `*.pyo`, then verify the final ZIP checksum.


## Build 039 readiness-first workflow
Before editing the worksheet or running acquisition, execute:

```bash
python -m gmk_cli pilot-readiness \
  --workspace pilot/PT_WORKSPACE \
  --intake-dir pilot/PT_MEDIA_INTAKE \
  --output-dir pilot/PT_PILOT_READINESS \
  --json
```

Interpret the status literally:
- `BLOCKED_MEDIA`: place exactly one authorized video in each missing source-locked slot.
- `BLOCKED_INSPECTION`: inspect the real bytes and complete the worksheet.
- `BLOCKED_PREFLIGHT`: correct the range/source/checksum/technical validation problem.
- `READY_TO_EXECUTE`: review the readiness report, then run `pilot-media-process --execute` explicitly.
- `ALREADY_ADVANCED`: do not re-import the videos; continue from the current project state.

The readiness command is read-only and must not change `CURRENT_MANIFEST.json`.

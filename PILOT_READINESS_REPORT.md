# P.T. Pilot Readiness — Build 038

## Current stage
`ASSET_RECON`

The core pipeline implementation is complete through `PROJECT_COMPLETED`, but the real P.T. workspace is correctly held at the external-media acquisition boundary.

## Ready
- Research Audit: PASS
- Rough Narrative / Narrative Spine: complete
- Visual Requirements: 10/10 Beats
- Asset Recon / Search Completion: PASS
- Explicit selected Assets: 10/10
- Cataloged evidence Assets: 8/10
- Verified evidence Segments: 8
- Source-locked media handoff runtime: implemented
- P.T. Execution Pack: generated
- P.T. Media Intake Pack: generated with 2 source-locked candidate slots
- One-command media processor: implemented; non-mutating by default, explicit `--execute` required
- Downstream isolated completion path: proven through `PROJECT_COMPLETED`

## Still required from the real world
1. Authorized local video bytes matching `LISA_X_DIRECT_VERIFIED`.
2. Authorized local video bytes matching `TGA_VIDEO`.
3. Exact local-file segment inspection, especially Lisa's numerical usable range.
4. Optional independent SHA-256 recorded before handoff.

## Hard boundary
Do not use webpage text, screenshots, embed metadata, unrelated reuploads, synthetic fixtures, or guessed timestamps as substitutes for the two source-locked media files.

## Next operator action
1. Put one authorized local video in each directory under `pilot/PT_MEDIA_INTAKE/`.
2. Fill `PT_MEDIA_INSPECTION_WORKSHEET.json` from inspection of those actual bytes.
3. Run `pilot-media-process` without `--execute`; review `PT_MEDIA_INTAKE_RECEIPT.json` and `PT_MEDIA_PROCESS_REPORT.json`.
4. Confirm the report says `ready: true` and `mutated: false`.
5. Rerun `pilot-media-process --execute` only after that review.

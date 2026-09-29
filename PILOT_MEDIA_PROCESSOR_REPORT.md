# GMK Build 038 — P.T. One-Command Media Processor

## Purpose
Build 038 reduces operator error at the real P.T. media boundary without weakening any source-lock, inspection, checksum, Gate, or Human Approval rule.

## Workflow
`pilot-media-process` performs, in order:

1. source-locked intake build;
2. ffprobe technical inspection and SHA-256 receipt;
3. exact handoff-plan compilation;
4. authoritative `MediaHandoffRuntime` preflight;
5. **stop without mutation by default**;
6. only with explicit `--execute`: acquisition + catalog closure + Visual Coverage transition.

The command never downloads media, fills human inspection fields, infers authenticity from a filename/checksum, or crosses a Human Approval boundary.

## Performance hardening
Build 036's execution wrapper performed redundant Cold Starts after committed acquisition/coverage results were already available. On the enlarged pilot history this could make integration execution highly variable. Build 038 now uses the exact committed result returned by `AssetAcquisitionRuntime` and `VisualCoverageRuntime` instead of reconstructing state after every transition. Cold Start remains authoritative at entry/replay boundaries.

A manual integration run against a copied real P.T. workspace reached `VISUAL_COVERAGE_READY` from manifest version 104 to 122 in about 27 seconds in the build environment.

## Current real-P.T. boundary
The packaged P.T. workspace remains unchanged at `ASSET_RECON`: the two authorized source-locked video files are not bundled and still must be supplied and inspected by a human operator.

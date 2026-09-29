# P.T. External Media Intake — Build 037

This directory is a non-authoritative staging area. Adding files here does **not** mutate `PT_WORKSPACE`.

## Workflow

1. Put exactly one authorized video in each candidate directory.
2. Fill `PT_MEDIA_INSPECTION_WORKSHEET.json` after inspecting the actual media.
3. Run `pilot-media-intake-build`; it probes, hashes, creates a receipt, compiles the handoff plan, and performs the same non-mutating handoff validation used by execution.
4. Review the receipt. Only then run the existing `pilot-media-execute` with the generated handoff plan.

## Source locks

- `LISA_X_DIRECT_VERIFIED` → https://twitter.com/manfightdragon/status/1170860592233472001
- `TGA_VIDEO` → https://www.youtube.com/watch?v=PKl5rYdwM6c

A directory name or checksum never proves visual identity by itself. The human inspection worksheet is required.

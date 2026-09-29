# P.T. Pilot External Media Intake Report — Build 037

## Purpose
Build 037 reduces the remaining real-world media handoff to a deterministic operator workflow without weakening provenance or source-lock boundaries.

## Current P.T. state
```text
Project State                 ASSET_RECON
Selected Assets               10
Cataloged Assets               8
Verified Segments              8
Pending source-locked videos   2
```

Pending candidates:
- `LISA_X_DIRECT_VERIFIED` — original-creator Lance McDonald source lock.
- `TGA_VIDEO` — selected TGA audiovisual source lock with locked inspected range `0–135s`.

## Intake workflow
1. `pilot-media-intake-init` creates one candidate directory per pending media requirement and a human inspection worksheet.
2. Operator places exactly one authorized local video in each candidate slot.
3. Operator inspects the actual bytes and fills exact usable `start_seconds`, `end_seconds`, `key_seconds`, visual description, match reason, name, and inspection note.
4. `pilot-media-intake-build` runs ffprobe, computes SHA-256, records technical metadata, creates `PT_MEDIA_INTAKE_RECEIPT.json`, compiles `PT_MEDIA_HANDOFF_READY.json`, and passes that exact plan through non-mutating `MediaHandoffRuntime.validate_plan()`.
5. Only the generated validated handoff plan should be passed to `pilot-media-execute`.

## Guarantees
- Directory names are routing aids, not proof of content identity.
- Checksums prove byte identity, not historical provenance.
- Human visual inspection remains explicit and mandatory.
- Source URLs are derived from the current authoritative Search Results, not typed from memory.
- TGA segment selection cannot exceed its locked `0–135s` source range.
- Workspace state and manifest version remain unchanged during init/build.
- No synthetic/test media is packaged with the real P.T. intake pack.

## Validation
Build 037 integration cases pass independently:
- exact source-locked slot initialization,
- missing-media fail closed,
- probe/hash/receipt + handoff preflight readiness,
- incomplete human inspection rejection,
- locked-range overflow rejection.

No schema erratum is introduced by Build 037.

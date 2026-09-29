# GMK Build 025 — Design DNA Runtime / Review Context Report

## Result
Build 025 implements the frozen Design DNA stage without manufacturing Scene artifacts before their legal stage.

The runtime now supports:

```text
VOICE_LOCKED
→ DESIGN_DNA + EFFECTIVE_DESIGN_TOKENS
→ DESIGN_DNA_REVIEW_PACKAGE
→ explicit HUMAN APPROVED
→ DESIGN_DNA_APPROVED
```

A REJECTED decision leaves the project at `VOICE_LOCKED` and the `DESIGN_DNA` Gate remains FAIL.

## Design preparation guarantees
- Requires `VOICE_LOCKED`.
- Requires exact current `VOICE_LOCK_MANIFEST` and `NARRATIVE_SPINE`.
- Creates one active `DESIGN_DNA` with traceable rule bases.
- Creates `EFFECTIVE_DESIGN_TOKENS` against the exact Design DNA version.
- Does not create Scene Plan, Scene Preview, Shot, Layer, or Cue objects prematurely.
- Does not auto-approve design.

## Review-context repair
The frozen transition requires Human Approval before Scene Plan. The historical generic `REVIEW_PACKAGE` cannot serve that purpose because it requires Scene Plan + Scene Preview.

Build 025 therefore adds `DESIGN_DNA_REVIEW_PACKAGE`, analogous to the Voice-specific repair in Build 024. Historical `DESIGN_DNA` approvals that use the old generic `REVIEW_PACKAGE` remain semantically valid for backwards compatibility.

## Validation
- Schema / Artifact contracts: **78 PASS**
- Build 023–025 + Gate/Semantic targeted run: **46 PASS**
- Python compileall: **PASS**
- CLI registration: **PASS** (`design-prepare`, `design-review-package`, `design-decide`)

## P.T. pilot
The real P.T. pilot remains at `ASSET_RECON`. Build 025 validates the later-state path only in isolated workspaces and does not write simulated completion into the real pilot workspace.

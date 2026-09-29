# GMK Build 024 — Voice Review Context Architecture Repair

## Problem
Build 023 proved a real circular dependency:

```text
TTS_READY
  ↓ VOICE Gate
VOICE Approval required
  ↓
APPROVAL.review_context required
  ↓
REVIEW_PACKAGE required SCENE_PLAN + SCENE_PREVIEW
  ↓
SCENE_PLAN is only legal after VOICE_LOCKED
```

Therefore a valid Voice Approval could not be produced at the point where the pipeline required it.

## Repair
Build 024 introduces `VOICE_REVIEW_PACKAGE`, a review artifact that can legally exist in `TTS_READY` after Voice preparation and before Scene planning.

It contains only already-available Voice-stage evidence: the exact Voice Lock, Master Voice, Timing Map, TTS script, and an audio integrity summary.

The visual `REVIEW_PACKAGE` contract remains unchanged.

## Proven transition
In the Build 024 isolated integration test:

```text
TTS_READY
  → prepare verified master audio
  → VOICE_LOCK_MANIFEST
  → VOICE_REVIEW_PACKAGE
  → explicit HUMAN APPROVED decision
  → VOICE Gate PASS
  → VOICE_LOCKED
```

A HUMAN REJECTED decision remains in `TTS_READY` and the Voice Gate remains FAIL.

## Backwards compatibility
Historical Build 008/009 fixtures using the old visual `REVIEW_PACKAGE` for Voice approval still pass. This preserves existing persisted history while new production work uses `VOICE_REVIEW_PACKAGE`.

## Validation
- Schema/contracts: **77 PASS**
- Build 023 + 024: **7 PASS**
- Gate + Semantic: **34 PASS**
- Build 008 + 009 compatibility: **7 PASS**
- Semantic smoke: **PASS**
- Gate Engine smoke: **PASS**
- Python compileall: **PASS**

## P.T. pilot truth state
The real P.T. pilot is still `ASSET_RECON` because the two source-locked video assets have not yet been handed in as real media bytes. Build 024 does not skip that boundary.

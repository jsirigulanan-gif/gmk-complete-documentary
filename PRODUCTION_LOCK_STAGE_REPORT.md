# GMK Build 029 — Production Lock Stage Report

## Result
Build 029 closes the human Production Lock review boundary between `HTML_APPROVED` and `PRODUCTION_RENDER` without fabricating per-Shot approval or using an unrelated Scene-only review context for a Project lock.

## Review model
The runtime first compiles a `PRODUCTION_LOCK_REVIEW_PACKAGE` while the project remains `HTML_APPROVED`. The package contains exact refs for:

- all current approved `SCENE_PREVIEW` artifacts;
- their exact current `SCENE_PLAN` artifacts;
- exact `VOICE_LOCK_MANIFEST` and `DESIGN_DNA` dependencies;
- the ordered current `SHOT` closure;
- every referenced `LAYER` and `CUE`;
- a deterministic SHA-256 over that complete closure.

No Production Lock is created during prepare.

## Human decision
An explicit human `APPROVED` decision is allowed to authorize only the closure that was reviewed. The runtime then:

1. creates exact `SHOT_VISUAL` approvals for reviewed Shots;
2. compiles one Scene `PRODUCTION_LOCK_MANIFEST` per Scene using the existing Production Lock Runtime;
3. compiles one Project `PRODUCTION_LOCK_MANIFEST` from those exact Scene Locks;
4. creates exact `PRODUCTION_LOCK` approvals for every current lock generated from that reviewed closure;
5. evaluates the existing `PRODUCTION_LOCK` Gate;
6. transitions `HTML_APPROVED → PRODUCTION_RENDER` only on PASS/WARN with `human_confirmed=true`.

A human `REJECTED` decision is persisted against the review proposal and creates no lock.

## Why Erratum 029 is required
The standard `REVIEW_PACKAGE` is intentionally Scene-specific and requires one `SCENE_PREVIEW` + one `SCENE_PLAN`. A Project Production Lock is an aggregate closure across all Scenes and does not exist until Shot approvals are present. Reusing an arbitrary Scene Review Package would make the Human Approval technically valid but semantically misleading.

`PRODUCTION_LOCK_REVIEW_PACKAGE` repairs that context gap without loosening the old `REVIEW_PACKAGE` contract.

## Validation

```text
Schema / Artifact contracts        79 — PASS
Semantic validation                PASS
Build 029 tests                    5 / 5 PASS
Build 024–029 + Gate/Semantic      58 / 58 PASS
Build 008–009 compatibility         7 / 7 PASS
Production Render / QA smoke       PASS
Gate Engine smoke                  PASS
Python compileall                  PASS
Repository layout audit            PASS
```

## Pilot boundary
The durable P.T. pilot remains at `ASSET_RECON` because the two source-locked external video Assets are still pending. No isolated future-stage Production Lock artifacts were copied into the pilot workspace.

## Next
After `PRODUCTION_RENDER`, the frozen pipeline requires actual render execution plus Shot QA before `SHOT_QA_PASSED`. Build 030 should provide the stage runtime that queues exact final render jobs from the Project Production Lock, executes through an authorized renderer adapter, and evaluates Shot QA without treating render success as QA success.

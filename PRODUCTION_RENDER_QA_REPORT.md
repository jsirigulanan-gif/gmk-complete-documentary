# GMK Build 008 — Production Lock / Render / QA Runtime Report

## Production Lock
`ProductionLockRuntime` compiles a scene lock from exact approved inputs. It derives Layer and Cue closure from the locked Shots instead of trusting a caller-maintained duplicate list.

Required current approvals in Build 008:
- `VOICE` → exact Voice Lock Artifact
- `DESIGN_DNA` → exact Design DNA Object + decision hash
- `SCENE_PREVIEW` → exact Scene Preview Artifact
- `SHOT_VISUAL` → exact STANDARD / CRITICAL Shot + decision hash

The resulting lock is immutable and remains historical even if later project changes invalidate its current production eligibility.

## Lock invalidation behavior
Production Lock artifacts participate in the live dependency graph before Release. If a frozen Shot/Layer/Cue dependency changes through an ACTIVE promotion, the lock receives a dependency invalidation. `RenderRuntime` refuses to queue a FINAL job from that invalidated lock.

This preserves both truths:
- the old lock still proves what was approved at that time
- it is no longer eligible as the current render authority

## Render execution
`RenderRuntime` separates:
- queueing the exact FINAL render intent
- persisted RUNNING job state
- renderer execution
- immutable output Artifact creation
- Render Manifest creation
- terminal job state

A render adapter receives only compiled payload plus exact frozen input snapshot. It does not resolve project `ACTIVE` state.

## Retry and cache
Transient render errors may retry at most twice after the first attempt. The same render key is preserved across attempts.

The render cache key is derived from:
- exact Production Lock
- exact locked inputs
- renderer adapter identity/version
- output profile
- compiled renderer payload

A cache hit creates a new Render Manifest with `mode = CACHE_HIT` and points to the existing output Artifact.

## Technical validation
The Build 008 technical validator foundation verifies core output metadata before the result can become a successful Render Manifest. Provider-specific codec/profile validation remains adapter/config work for later integration.

## QA execution
`QARuntime.evaluate()` converts findings into immutable QA Issues and a QA Report snapshot. Report result is derived:
- unresolved MAJOR / CRITICAL → `FAIL`
- only MINOR findings → `WARN`
- no findings → `PASS`

## Repair boundary
QA does not mutate a Shot, Layer, Cue, Voice, Narrative or Asset. It may only create a Repair Plan after root cause is `IDENTIFIED` or `BOUNDED_UNKNOWN`.

Automatic repair planning is capped at two cycles per exact QA Issue version. Production changes still have to flow through the already-implemented Revision / State Engine path.

## Regression foundation
A QA Baseline pins the exact Production Lock, Render Manifest, QA Reports and output Artifacts. Regression Compare records expected vs observed changed scope and fails when unexpected scope changes are reported.

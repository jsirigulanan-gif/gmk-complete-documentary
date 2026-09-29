# GMK Schema v1 — Build 024 Changelog

## Purpose
Resolve the Voice Approval circular dependency discovered in Build 023 without fabricating future Scene artifacts or weakening existing visual-review semantics.

## Schema v1 erratum
Added one narrowly scoped Artifact contract:

- `VOICE_REVIEW_PACKAGE`

This package exists specifically for pre-Scene human review of a prepared `VOICE_LOCK_MANIFEST`. It pins the exact:

- `VOICE_LOCK_MANIFEST`
- `MASTER_VOICE`
- `VOICE_TIMING_MAP`
- `TTS_READY_SCRIPT`
- review summary (block count, duration, audio SHA-256)

The existing `REVIEW_PACKAGE` contract is unchanged and continues to require `SCENE_PLAN + SCENE_PREVIEW + shots` for visual review.

## Approval compatibility rule
- `VOICE` approvals may use `VOICE_REVIEW_PACKAGE`.
- Historical `VOICE` approvals that used `REVIEW_PACKAGE` remain valid for backwards compatibility.
- All non-Voice approval classes retain the original `REVIEW_PACKAGE` rule.

## Runtime
Added:
- `VoiceRuntime.review_package()`
- `VoiceRuntime.decide()`
- CLI `gmk voice-review-package`
- CLI `gmk voice-decide`

`voice-decide` requires an explicit human `actor_id` and explicit `APPROVED` or `REJECTED` decision. Only `APPROVED` may attempt the Human-authorized transition to `VOICE_LOCKED`.

## Safety / authority
Build 024 does not auto-approve Voice. It creates a reviewable context and an explicit human-decision path. A rejected decision leaves the project in `TTS_READY`.

## Architecture impact
- Core Objects: unchanged.
- Project States: unchanged.
- Gate IDs / transition order: unchanged.
- Existing `REVIEW_PACKAGE`: unchanged.
- Artifact contracts: **76 → 77**.
- Schema v1 status: **FROZEN WITH ERRATUM 024** (narrow deadlock repair; no v2 redesign).

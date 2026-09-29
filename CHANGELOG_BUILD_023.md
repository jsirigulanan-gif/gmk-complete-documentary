# GMK Schema v1 — Build 023 Changelog

## Added
- `gmk_voice.VoiceRuntime` voice-preparation runtime.
- CLI command `gmk voice-prepare`.
- verification of imported master-audio bytes with `ffprobe`.
- immutable SHA-256 capture and workspace media copy.
- exact `MASTER_VOICE` creation from verified audio bytes.
- exact `VOICE_TIMING_MAP` creation with full active Voice Block coverage.
- `VOICE_LOCK_MANIFEST` creation in imported-master mode.
- Build 023 regression tests for state guarding, verified audio preparation, and timing rejection.

## Runtime guarantees
- Runs only from `TTS_READY`.
- Requires one exact current project, voice profile, final script, TTS script and pronunciation dictionary.
- Requires every active `VOICE_BLOCK` to have one bounded timing entry.
- Rejects missing audio, missing audio streams, non-positive duration, incomplete timing coverage, overlapping/out-of-order timing, and ranges beyond master duration.
- Stores the verified master under workspace media and records immutable SHA-256 plus technical metadata.
- Does **not** manufacture a Human Approval and does **not** transition to `VOICE_LOCKED` automatically.

## Frozen-contract issue discovered
The frozen `VOICE` Gate requires a Human `APPROVAL` targeting `VOICE_LOCK_MANIFEST`. The frozen `APPROVAL` contract in turn requires `review_context` to resolve to `REVIEW_PACKAGE`. The frozen `REVIEW_PACKAGE` contract requires `SCENE_PLAN` + `SCENE_PREVIEW`, but those are produced only after `VOICE_LOCKED` in the frozen Project State sequence.

Build 023 therefore stops fail-closed at the approval boundary rather than fabricating future planning artifacts, using unresolved references, or changing Schema v1 silently.

## Architecture
No Core Object, Artifact contract, Gate ID, Project State, or frozen Schema v1 contract was added or changed.

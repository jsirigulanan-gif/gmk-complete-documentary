# GMK Schema v1 — Build 022 Changelog

## Added
- `gmk_narrative.tts.TTSRuntime`.
- CLI command `gmk tts`.
- deterministic `PRONUNCIATION_DICTIONARY` creation.
- `VOICE_PROFILE` creation for the exact TTS plan.
- exact `TTS_READY_SCRIPT` compilation from the current `VOICEOVER_SCRIPT_FINAL`.
- one active `VOICE_BLOCK` per exact narration Beat, committed in `TTS_READY` state.
- batch SHA-256 replay protection and batch-ID collision rejection.
- `pilot/PT_TTS_INPUT.json`.
- Build 022 TTS regression tests.

## Runtime guarantees
- Can run only from `SCRIPT_READY`.
- Requires exactly one current `VOICEOVER_SCRIPT_FINAL`.
- Requires one-to-one coverage of all active `NARRATION_BEAT` objects.
- Rejects stale/non-current Beat references, text drift, missing narration, placeholders, language mismatch, invalid voice settings, and duplicate pronunciation keys.
- TTS preparation does **not** claim rendered audio; `extensions.tts_runtime.rendered_audio=false` is explicit.
- Uses the frozen `TTS` Gate to enter `TTS_READY`.
- Replay is idempotent for identical `batch_id + plan SHA-256`.

## P.T. pilot boundary
The durable P.T. pilot remains at `ASSET_RECON` because the two externally supplied source-locked video files are still absent. Build 022 proves the later Script → TTS transition in an isolated, fully satisfied workspace; it does not advance the real pilot around unresolved media acquisition.

## Architecture
No Core Object, Gate ID, Project State, or frozen Schema v1 contract was added or changed.

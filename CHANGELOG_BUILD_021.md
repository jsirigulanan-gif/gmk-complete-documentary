# GMK Schema v1 — Build 021 Changelog

## Added
- `gmk_narrative.script.ScriptRuntime`.
- CLI command: `gmk script`.
- Exact one-to-one final narration coverage for all active Narration Beats.
- Conservative Claim language-mode enforcement before final narration mutation.
- Exact current Claim eligibility checks at Script compile time.
- Beat revisions to `workflow_state: NARRATION_FINAL` with final `narration` payloads.
- `VOICEOVER_SCRIPT_FINAL` compilation from exact promoted Beat versions.
- Beat decision-hash pinning into every script block.
- Idempotent replay keyed by `batch_id + plan SHA-256`.
- Build 021 regression tests.

## Runtime behavior
- Requires project state `VISUAL_COVERAGE_READY`.
- Rejects missing, extra, duplicate, empty, or placeholder Beat narration.
- Rejects stale/non-current or narration-prohibited Claim bindings.
- Rejects narration language modes stronger than the most restrictive bound Claim requires.
- Requires every active Beat to retain a visual requirement before script finalization.
- Creates final Beat versions first, then compiles the immutable script artifact from those exact versions.
- Advances only through the frozen `SCRIPT` Gate to `SCRIPT_READY`.

## Boundary
- No TTS artifact is created.
- No voice synthesis is performed.
- No frozen Schema v1 contract or Core Object is changed.
- The real P.T. pilot remains at `ASSET_RECON` until the two source-locked video files are supplied; Build 021 is validated on an isolated media-backed workspace.

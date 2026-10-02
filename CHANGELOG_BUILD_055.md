# Build 055 — Final reviewed script and real master voice

The editor previously stopped canonical integration at reviewed visual coverage. It now prepares exact final narration in the edit's scene order, refreshes the picture/coverage records after final Beat promotion, and assembles a real 48 kHz mono PCM master from existing reviewed scene audio. Core script ordering also follows Act/Scene/Beat order instead of reference IDs.

The new operator action previews current inputs, prepares script/audio through the existing SCRIPT/TTS gates, opens verified local master bytes, and requires a named explicit whole-master listening decision before VOICE_LOCKED. Per-scene listening does not approve the master. Rejection clearly requires reopening and fresh preparation; the interface prevents another decision on the same reviewed version.

Revisions retain stable identities, original media and history, archive only obsolete owned records, and protect foreign records and later locks. Exact preview hashes and rechecks reject changes during assembly. Source audio is frozen/checksummed before conversion; complete derived masters publish atomically. All canonical stages are validated in memory before one persisted publication. Failed staging may leave an unreferenced derived cache file, without advancing the persisted state or granting approval.

CLI: `final-inspect`, `final-prepare`, `final-voice-decide`, `final-reopen`. Readiness routes to the new action after coverage and library selection. Status exposes current master identity/hash and decision. FAST audit includes six new cases and splits the expanded older workflow partition to preserve bounded execution and explicit timeout reporting.

This step makes no model/TTS provider call. Existing per-scene free Edge TTS/import flows remain available. It does not establish rights, exhaustive source search, factual approval, canonical final release or real-film acceptance. Next integration remains design/graphics, scene/shot/timeline, production lock, render, whole-film QA and final delivery/release. See [validation](BUILD_055_VALIDATION.md).

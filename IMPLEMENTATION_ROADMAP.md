# Implementation against the documentary product requirement

See PRODUCT_REQUIREMENTS.md for the complete user requirement. This plan keeps all stages in scope and distinguishes reusable engines from a working product.

## Current evidence

- The legacy StateEngine supports versioned core objects, evidence/dependencies, gates, persistent manifests, QA and release records. Many component tests operate on supplied plans and fixtures.
- Build 049 extends canonical intake with archived external source text, explicit versioned claim review, and scene-to-claim wording review. Compound claim splitting remains manual; automatic evidence gathering and core gate advancement are not yet integrated.
- The general project editor imports documents, preserves source links, offers opt-in structured Codex story drafts, edits scenes/shots, and binds speech to the current narration text. Live narration verification used a generic test passage; private project text still awaits consent for Edge TTS.
- The editor connects footage search/download/caption nominations, measured-audio timelines, music ducking, titles/subtitles, MP4 rendering, full-file technical QA and explicit local delivery review. These pass synthetic media tests. Caption proposals require visual review; complete semantic matching and canonical final-release/Drive completion remain unconnected.
- Build 050 verifies exact draft package members, immutable render/QA records and current edit/research before upload; validates asset and manifest Drive receipts; and rejects post-transfer changes. Controlled transfer/retry tests pass. The last live Drive check failed on the shared rclone client quota; no complete documentary delivery has been verified.

## Integration order

1. **One authoritative project:** bind each general Drive project to a persisted StateEngine workspace, register original research without claiming an audit, expose actual core state/next action, and include production records in project storage snapshots. Preserve old projects with explicit, repeatable migration. Do not build another independent completion state machine.
2. **Research through visual requirements:** generalize intake beyond P.T.; attach source/evidence/claim records; connect a research/narrative/script provider; generate and edit stable narration beats and visual requirements. Preserve imported drafts without treating them as verified outputs. User-facing decisions must operate on these objects instead of manual JSON plans.
3. **Footage through timeline:** expose project-specific research and selection; acquire selected media and archive all downloaded candidates on Drive; connect scene/shot planning and an editable rough timeline. Show unresolved matching instead of inserting unrelated material. A short acquisition test must verify source bytes, selection, local replay and remote storage.
4. **Voice/design/render:** bind audio to exact script revisions, conform timeline durations to measured speech, implement music mixing/ducking and graphics, and render from the actual project timeline. Keep draft preview distinct from release output. Use bounded-memory acquisition/render settings for the current machine.
5. **QA/delivery/export:** connect technical film checks and editorial review to the exact master; package/export it and verify the Drive copy. Bridge that proof to final project completion. Test edit-triggered invalidation and interruption recovery, then perform the real short-film and long-film acceptance runs.

Drive quota and external TTS consent are operational blockers to live demonstrations, not substitutes for the remaining implementation work. New features must be described as implemented, tested with fixtures, or verified live; those labels are not interchangeable.

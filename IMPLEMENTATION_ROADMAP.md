# Implementation against the documentary product requirement

See PRODUCT_REQUIREMENTS.md for the complete user requirement. This plan keeps all stages in scope and distinguishes reusable engines from a working product.

## Current evidence

- The legacy StateEngine supports versioned core objects, evidence/dependencies, gates, persistent manifests, QA and release records. Many component tests operate on supplied plans and fixtures.
- The general Drive project UI currently imports a real source document, preserves its links, catalogs files, and can synthesize Thai narration. Live narration verification used a generic test passage; private project text still awaits consent for Edge TTS.
- Footage research/acquisition and rough-cut assembly exist, but the general Drive project workflow does not orchestrate them through a complete film.
- Actual Drive upload currently fails on the pre-existing shared rclone client's Google API quota. No complete exported documentary has been verified.

## Integration order

1. **One authoritative project:** bind each general Drive project to a persisted StateEngine workspace, register original research without claiming an audit, expose actual core state/next action, and include production records in project storage snapshots. Preserve old projects with explicit, repeatable migration. Do not build another independent completion state machine.
2. **Research through visual requirements:** generalize intake beyond P.T.; attach source/evidence/claim records; connect a research/narrative/script provider; generate and edit stable narration beats and visual requirements. Preserve imported drafts without treating them as verified outputs. User-facing decisions must operate on these objects instead of manual JSON plans.
3. **Footage through timeline:** expose project-specific research and selection; acquire selected media and archive all downloaded candidates on Drive; connect scene/shot planning and an editable rough timeline. Show unresolved matching instead of inserting unrelated material. A short acquisition test must verify source bytes, selection, local replay and remote storage.
4. **Voice/design/render:** bind audio to exact script revisions, conform timeline durations to measured speech, implement music mixing/ducking and graphics, and render from the actual project timeline. Keep draft preview distinct from release output. Use bounded-memory acquisition/render settings for the current machine.
5. **QA/delivery/export:** connect technical film checks and editorial review to the exact master; package/export it and verify the Drive copy. Bridge that proof to final project completion. Test edit-triggered invalidation and interruption recovery, then perform the real short-film and long-film acceptance runs.

Drive quota and external TTS consent are operational blockers to live demonstrations, not substitutes for the remaining implementation work. New features must be described as implemented, tested with fixtures, or verified live; those labels are not interchangeable.

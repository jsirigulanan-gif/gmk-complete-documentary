# Build 051 — reviewed story to canonical visual requirements

The general editor previously held story/scenes separately from production state. It can now compile explicitly reviewed narration and visual descriptions into canonical Acts, Scenes, Narration Beats and a versioned narrative spine, advancing only through the existing research, rough narrative and visual requirement gates.

- Preview missing research/wording reviews and narrative inputs before connecting. Preview hashes prevent applying an obsolete edit or research decision.
- Preserve scene/beat identities and historical versions through reorder, exclusion, reinclusion and evidence revisions. Failed final gates leave the persisted workspace untouched; unchanged reconnects are no-ops.
- Expose a Thai editor dialog and `production-inspect` / `production-connect-story` CLI commands. The project panel shows binding freshness and meaningful early-stage labels.
- Use canonical beat/claim references for connected footage search intents. Reject stale bindings before searching and reject shot insertion when the production manifest changed during acquisition. Retained downloads remain in the project catalog.
- Permit explicit claim re-review to reopen early narrative stages, while retaining the stricter behavior for later production stages and other audit callers.
- Fix a core persistence defect: consecutive upstream promotions could leave old dependency reasons that changed during cold-start reconstruction, making the project unloadable. Promotions now reconcile derived state against all exact dependency references and update registry locators transactionally.

This build stops at canonical visual requirements. It does not declare asset coverage, final script, voice, shot/render approval, canonical release, live Drive delivery, or completed documentary acceptance. Existing local draft editing/render/export remains available.

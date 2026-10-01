# Build 049 — A connected documentary editing desk

The general project workflow now has an editing desk instead of separate draft-script, voice, footage and render islands. The existing research StateEngine and immutable source history are retained. The new editable draft is a versioned working document; it does not bypass final production/release gates.

- Edit/reorder/include scenes, narration, visual requirements, title overlays and source-video ranges. Preserve acquired candidates even when cuts are removed.
- Archive public HTML/text sources, select exact excerpts, and record explicit supported/contradicted/insufficient decisions as canonical claim versions. Changed claims can discard old external support without erasing history.
- Bind each scene to current canonical claims through explicit wording review. Narration edits, changed references and retracted evidence invalidate readiness. Render/export packages preserve the per-scene research review; unreviewed drafts remain identifiable. Blank new projects can open the editor before a script import.
- Request a structured narrative/script/visual/search-query draft through an opt-in Codex CLI adapter. Constrain output with JSON Schema, verify claim IDs, preserve the old edit, and reject stale or altered drafts. Actual account-backed generation still requires live verification.
- Generate/cache Thai speech against the edited text, or import audio. Changing narration invalidates its audio binding. Existing Build 046 voice can be imported when script/text hashes match.
- Search/download YouTube footage into the project catalog, capped at 720p for this machine. Caption inspection can nominate and acquire draft cuts for one/all missing scenes; missing evidence remains unresolved. Caption matches explicitly require visual review.
- Build the timeline from measured audio and frame/sample counts. Refuse insufficient pictures unless the editor explicitly allows holding the final frame. Trim excess footage instead of cutting narration to old planned scene durations.
- Render bounded-memory H.264/AAC MP4 with music looping/ducking, selectable Thai subtitles, optional mixed Thai/Latin title overlays, credits and exact input/edit snapshots. Keep temporary media on the project disk rather than filling a RAM-backed `/tmp`.
- Decode the whole output and verify stream durations, resolution and frame count. A local full-film review action is required before building a delivery ZIP. Edit/research changes invalidate that review.
- Freeze the active working edit during Drive sync, detect checkpoint races, and mark subsequent edits pending upload.
- Make the main screen point to the active project workflow; the old P.T. pilot remains an explicit example. Voice actions now live in the editor so the GUI uses the edited draft consistently.

This build has real local render/export tests, not a completed real documentary. Full automatic visual-semantic selection and the canonical final-release/Drive completion adapter remain incomplete. Local package creation never sets `documentary_completed`. Existing Drive shared-client quota failure and pending live provider consent/configuration remain explicit.

# Build 053 — Connect reviewed project footage to production records

Reviewed local clips previously stayed only in the working edit. They now register actual source bytes, provenance, selected time ranges and exact visual decisions as canonical Source, library Search, Search Result, Asset and Segment objects. Per-scene versioned provenance receipts bind these selections to current story/beat versions. No network search, download operation or coverage certificate is fabricated.

The footage tab offers a preview and connection action. Lifecycle readiness routes selected reviewed footage to this action before rendering. The CLI exposes `media-inspect` and `media-connect`, using exact edit and production-manifest preview hashes. Repeating an unchanged registration is a no-op; stale previews fail before writing.

Drive script discovery accepts both plain `lemino script` and bracketed `[LEMiNO Script]` titles, including documents within folders. The operator handoff now describes the general documentary workspace instead of the obsolete pilot UI.

Trimming requires renewed picture review. Changed selections create new versions under stable IDs. Removed/reincluded cuts and scenes recover their previous IDs and retain original files. Explicit research changes and claim re-review can reopen only the early media stage owned by this editor, preserving the working edit; later/foreign production data remain protected.

Archived core heads are now treated as history during dependency recomputation. Previously an excluded scene's archived footage could be changed back to STALE on reload, breaking registry checksum reconstruction. Upstream changes still invalidate live dependent records.

The local library connection records human selection rather than complete external search. Rights and independence remain UNKNOWN. CONTEXT footage retains that editor classification and conservatively maps to an unverified core segment because the frozen core match enum has no CONTEXT member. Canonical coverage, downstream production locks and final release/real Drive acceptance remain unfinished.

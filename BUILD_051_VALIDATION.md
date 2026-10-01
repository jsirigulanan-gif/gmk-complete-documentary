# Build 051 validation — 2026-10-01

## Confirmed behavior

Reviewed editor scenes advance through the canonical research, rough narrative and visual requirement gates. Exact edit/manifest preview tokens prevent connecting an obsolete review. Reorder, exclusion and reinclusion retain scene/beat identities and history; unchanged reconnects do not persist a new manifest. A simulated failure at the final gate leaves the persisted workspace unchanged.

Repeated claim retraction/reapproval and consecutive source promotions survive cold-start reconstruction with identical registry snapshots. Claims stay pinned to exact versions; re-review is required before reconnecting. Media-only edits preserve the story binding. Changed narration, visual requirements, evidence or an externally revised Act invalidate it. A production-manifest check under the writer lock rejects stale shot insertion after research changes.

## Results

- Core/bridge/dependency/state/gate/cold-start partition: **57 passed in 45.72 seconds** (before the additional external-Act regression).
- Existing research audit, rough narrative and visual requirement runtimes: **16 passed in 28.69 seconds**.
- Live Tk desktop test: visible dialog controls, disabled connection before preview, readiness preview, explicit connection and canonical `VISUAL_REQUIREMENTS_READY` all passed using a temporary synthetic research project. The footer was corrected after the first visibility check found clipped buttons.
- The real local project has **13 selected scenes**, **29 readiness issues**, and remains **RESEARCH_INTAKE**. Inspection left its canonical manifest unchanged. No claims were approved by this check.

- Additional external-Act revision regression: **1 passed in 6.86 seconds**.
- Existing real FFmpeg edit/render and draft delivery regression: **18 passed in 98.35 seconds**.
- Compilation, CLI command registration and whitespace checks passed.
- QUICK audit: **33 PASS / 0 FAIL / 0 TIMEOUT / 1 legacy WARN** (missing standalone Build 001 changelog). The new fast partition passed all **11** bridge/core regression cases in 43.44 seconds.
- The four targeted partitions total **92 distinct passing cases**. QUICK repeats some of them; its cases are not added to that total.

## Limits

This verifies software integration through canonical visual requirements, not a finished documentary. No live model generation, private-project TTS request, online footage acquisition, Google Drive upload or real short/long-film acceptance was performed. The last recorded Drive quota failure remains unresolved. Canonical asset/coverage/final script/shot/timeline/render/QA/release integration remains required.

Earlier aggregate runs were interrupted by the conversation and have not been counted as passed. The separate Veocut and Sunshine files shown by the IDE were not edited.

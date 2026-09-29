# GMK Schema v1 — Build 028 Changelog

## Added
- `gmk_review.HTMLReviewRuntime`.
- CLI command `gmk html-review-prepare`.
- CLI command `gmk html-review-decide`.
- Deterministic per-Scene HTML review files with SHA-256 fingerprints.
- Exact `SCENE_PREVIEW` coverage for every active Scene.
- Standard `REVIEW_PACKAGE` creation pinned to the exact Scene Preview, Scene Plan, and ordered Shot refs.
- Explicit HUMAN Scene Preview approval/rejection flow.
- Idempotent prepare and decision replay behavior.
- Build 028 regression coverage.

## Runtime behavior
- Runs prepare only from `SHOT_PLAN_READY` or as replay from `HTML_REVIEW` / `HTML_APPROVED`.
- Uses the existing automatic `SHOT_PLAN_READY → HTML_REVIEW` transition.
- Does not auto-approve any Scene Preview.
- Leaves rejected previews in `HTML_REVIEW`.
- Transitions to `HTML_APPROVED` only after the existing `HTML_REVIEW` Gate confirms exact current approval coverage.
- Does not create Production Lock or begin render.

## Schema status
No schema contract was added or changed in Build 028.

`GMK_SCHEMA_V1_CONTRACT = FROZEN_WITH_ERRATA_024_025`

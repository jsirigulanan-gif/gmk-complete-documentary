# GMK Schema v1 — Build 016 Changelog

- Added `AssetSelectionRuntime` for Search Again closure, candidate selection, Search Completion certification, Asset identity creation, and acquisition planning.
- Added `asset-select` CLI command.
- Closed `BEAT_LISA_FINDING` using a round-2 source-trace search and an original-creator candidate.
- Preserved Candidate Comparison history and added Lisa comparison v2 (`MEETS_TARGET`).
- Created `SEARCH_COMPLETION_CERTIFICATE` as `QA_REPORT` with `PASS`.
- Explicitly promoted 10 selected candidates to 10 Asset identities.
- Planned 10 idempotent DOWNLOAD Operations; Assets remain `ACQUISITION_PENDING`.
- Enforced no fabricated `original_file` metadata and no premature Segment creation.
- Updated Build 015 regression test to scope its historical first-pass assertions to the Build 015 batch rather than later global totals.
- Added Build 016 tests and CLI coverage.
- No Core Object, authority, or frozen Schema v1 contract changes.

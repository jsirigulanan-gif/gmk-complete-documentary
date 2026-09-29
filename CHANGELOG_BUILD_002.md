# Build 002 changelog

Compared with Build 001:

- Added `gmk_semantics` validation package.
- Added exact-version in-memory `StateView` resolver.
- Added deterministic Core Object decision hash projection.
- Added object, artifact, and global semantic rule orchestration.
- Added semantic CLI.
- Added semantic pytest matrix (24 passing tests).
- Added cross-artifact validation for Voice, Planning/Review, Production Lock, Renderer Prompt, Repair, and Restore artifacts.
- Patched `EDIT_REQUEST.directive` with `constraint_id` for frozen `RELEASE_CONSTRAINT` semantics.
- Patched Approval schema so `review_context` is structurally required.
- No new Core Object was added.
- Contract remains `GMK_SCHEMA_V1_CONTRACT = FROZEN`.

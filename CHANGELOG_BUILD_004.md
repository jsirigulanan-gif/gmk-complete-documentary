# GMK Schema v1 — Build 004 Changelog

## Added
- `gmk_dependency/` runtime package
- schema-driven dependency projection compiler
- exact Object / Artifact dependency graph
- derived reverse index and cycle inspection support
- authoritative Change Set diffing
- path-based impact tagging
- pinned Dependency Policy `1.0.0`
- `UNAFFECTED / REVALIDATE / STALE / BLOCKED` classification
- transitive queue propagation
- live `HEAD / ACTIVE` filtering
- frozen Release / Final Project Checkpoint boundaries
- Human-locked impact dry-run + explicit confirmation
- runtime dependency invalidation registry
- explicit dependency revalidation action
- cold-start dependency projection integrity check
- cold-start live dependency recompute
- `DEPENDENCY_IMPACT_REPORT` artifact contract
- Dependency Engine smoke tool
- 10 Dependency Engine tests

## Schema implementation metadata
Added `x-gmk-dependency-relation` annotations to frozen v1 domain references so `dependencies[]` can be compiled instead of manually authored.

Local schema registry increases from **67 → 68** because the already-locked `DEPENDENCY_IMPACT_REPORT` artifact contract is now physically implemented.

## Fixed
- corrected semantic order-uniqueness validation so multiple immutable versions of one stable Core Object ID do not falsely collide with themselves

## Schema contract changes
**None.** Build 004 implements the already frozen 1E / 2J contracts. Schema version remains `1.0.0`.

## Runtime boundary
Artifact nodes participate in the dependency graph through exact immutable references, but a dedicated Artifact Registry lifecycle is not introduced in this build. Gate evaluation remains fail-closed until Build 005.

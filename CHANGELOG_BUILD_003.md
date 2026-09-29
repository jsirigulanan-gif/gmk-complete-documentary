# GMK Schema v1 — Build 003 Changelog

## Added
- `gmk_state/` State Engine foundation package
- system ID allocator for all 30 Core Object types
- Registry Snapshot / Entry / Version Locator runtime models
- `HEAD` vs `ACTIVE` registry semantics
- EXACT / ACTIVE / HEAD resolver
- decision hash + record hash registry locators
- staged transaction engine with optimistic concurrency
- State Engine action paths for Create/Version/Promote/Archive/Approval/Edit Request/Revision/Transition/Derived Refresh
- Human Lock path enforcement and explicit release handling
- append-only transaction audit history
- state engine smoke tool
- 18 State Engine tests

## Schema contract changes
**None.** Build 003 implements the already frozen 1D/2G contracts. JSON Schema v1 remains `1.0.0`.

## Runtime boundary
Project State transitions remain fail-closed without an external transition authorizer. This is intentional until the Gate Engine build.

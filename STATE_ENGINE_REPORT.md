# GMK Schema v1 — Registry + State Engine Foundation / Build 003

Build 003 implements the authoritative in-memory mutation foundation required by frozen Implementation 1D. It does **not** implement Dependency propagation, Gate evaluation, durable persistence, or external Operations.

## Implemented runtime foundation
- System-issued stable IDs for all 30 Core Object types
- System-issued contiguous integer versions per stable object ID
- Registry snapshots with `HEAD` and `ACTIVE` kept separate
- Exact / HEAD / ACTIVE resolver modes; persisted references remain exact-version references
- Per-version locator records with `decision_sha256`, `record_sha256`, URI, and timestamps
- Global Resolver Index derived from registries; duplicate stable IDs fail closed
- New version creation advances `HEAD` only; it does not silently promote `ACTIVE`
- Explicit `PROMOTE_ACTIVE_VERSION`
- Immutable committed decision versions by copy isolation; no external mutable object reference is published
- Live-derived refresh for status/stale/dependencies/approval summary/lock state without changing decision hash
- Human Constraint path enforcement during revision
- Explicit Human Constraint release through exact `EDIT_REQUEST` refs
- Atomic staged transactions: validate before publish; failed commits publish nothing
- Optimistic manifest and registry concurrency checks
- Append-only transaction audit log infrastructure
- Project-state transition boundary is fail-closed until a transition authorizer/Gate Engine is installed

## Frozen State Engine actions represented
- `CREATE_OBJECT` — implemented
- `CREATE_VERSION` — implemented
- `PROMOTE_ACTIVE_VERSION` — implemented
- `ARCHIVE_OBJECT` — implemented
- `CREATE_APPROVAL` — implemented as typed State Engine creation path
- `CREATE_EDIT_REQUEST` — implemented as typed State Engine creation path
- `APPLY_REVISION` — implemented as atomic version bundle + REVISION creation
- `TRANSITION_PROJECT_STATE` — boundary implemented; denied without explicit authorizer
- `REFRESH_DERIVED_STATE` — implemented

## Validation pipeline on commit
1. Stage mutations in a private state clone
2. Apply system identity/version/envelope rules
3. Rebuild affected registry entries/hashes
4. JSON Schema Draft 2020-12 validation on changed Core Objects
5. Build 002 Semantic Validator Suite across the staged state
6. Check optimistic manifest/registry versions
7. Increment affected registry snapshots once per transaction
8. Increment manifest cursor once per transaction
9. Append immutable audit record
10. Atomically publish the staged state

## HEAD vs ACTIVE proof
Build 003 tests verify:
- Core Object v1 can become `HEAD=1 / ACTIVE=1` after successful creation
- creating v2 changes `HEAD=2` but preserves `ACTIVE=1`
- only explicit promotion changes `ACTIVE=2`
- stale/blocked/archived/rejected versions cannot be promoted

## Human Lock proof
The State Engine compares the exact JSON-pointer path of every active Human Constraint before and after a revision. A changed locked path fails with `HUMAN_LOCK_CONFLICT`. Removal fails with `HUMAN_CONSTRAINT_NOT_PRESERVED` unless an exact Human `RELEASE_CONSTRAINT` Edit Request is supplied. Released IDs are recorded in `extensions.released_human_constraints` so the existing semantic lineage validator can verify the release.

## Concurrency / atomicity proof
- concurrent transactions started from the same Manifest version: first commit succeeds, second fails `MANIFEST_VERSION_CONFLICT`
- explicit expected Registry version mismatches fail before mutation
- invalid semantic state fails commit and leaves Manifest/Registries unchanged
- version creation must branch from current `HEAD`; silent branching/merge is rejected

## Deliberately deferred
These remain separate locked engine builds:
- authoritative dependency projection compiler
- Change Set / impact-tag classifier
- stale/revalidate/block propagation and reverse dependency index
- promotion blast-radius / dependency impact integration
- Gate Engine and legal Project State transition rules
- full Project Manifest writer/compiler
- durable storage / crash-recovery transaction journal
- artifact mutation/compiler runtime
- renderer/QA/external operation/release orchestration

## Test result
- Structural schema registry: **67 contracts — PASS**
- Local `$ref`: **PASS**
- Semantic smoke: **PASS**
- State Engine smoke: **PASS**
- Full pytest suite: **42 passed**

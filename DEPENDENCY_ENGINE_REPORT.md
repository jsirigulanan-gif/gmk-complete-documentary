# GMK Schema v1 — Dependency Engine Report

## Status
`BUILD_004_DEPENDENCY_ENGINE = IMPLEMENTED`

The frozen 1E contract is now executable on top of Build 003's Registry / State Engine foundation.

## 1. Authoritative dependency projection
Core Objects do not treat their stored `dependencies[]` as source truth. Dependency edges are compiled from exact domain references marked with schema metadata:

```text
x-gmk-dependency-relation
```

Build 004 contains **123 dependency annotations** across Core Object and Artifact contracts. The compiler resolves local `$ref`, shared `$defs`, `allOf`, arrays, and nested structures before normalizing exact references.

For Core Objects:

```text
authoritative domain refs
        ↓
schema dependency annotations
        ↓
normalized dependencies[] projection
```

A stored projection that differs from the compiled projection raises `DEPENDENCY_PROJECTION_MISMATCH`. On cold start this fails closed into `READ_ONLY` instead of silently repairing authoritative state.

## 2. Exact-version graph
The graph contains both:
- Core Object nodes — `OBJECT:<id>@<integer version>`
- Versioned Artifact nodes — `ARTIFACT:<artifact_id>@<integer version>`

Forward edges are compiled from authoritative refs. Reverse dependency links are derived in memory and are never persisted as source truth.

Persisted references remain exact. Build 004 never retargets an object merely because another version became `ACTIVE`.

## 3. ACTIVE promotion is the root-change event
Creating a new `HEAD` version does **not** stale downstream work.

Only explicit `PROMOTE_ACTIVE_VERSION` compares the previously trusted ACTIVE decision with the promoted decision and emits a Change Set:

```text
previous ACTIVE exact version
        ↓
authoritative decision projection diff
        ↓
changed JSON paths
        ↓
impact tags
        ↓
dependency policy
```

Decision hashes exclude identity, lineage, operational, and live-derived envelope fields. Stale propagation therefore follows authoritative meaning instead of record metadata.

## 4. Impact dispositions
Build 004 executes the four frozen dispositions:

- `UNAFFECTED` — version drift is allowed; no invalidation is stored
- `REVALIDATE` — runtime eligibility requires explicit revalidation; Common ObjectStatus is not changed
- `STALE` — live-derived object state becomes stale without creating a new decision version
- `BLOCKED` — current use is blocked

Unknown dependency relations fail conservatively to stale behavior. Unknown changed paths receive a `GENERAL` tag.

The pinned `GMK_DEPENDENCY_POLICY 1.0.0` also defines non-production changes such as `/notes` and `/working_title` as `NON_PRODUCTION`, allowing genuinely unaffected version drift rather than invalidating everything merely because a version number changed.

## 5. Transitive propagation
Propagation uses a queue over the derived reverse graph.

Each impact records:
- affected exact node
- disposition
- dependency relation
- immediate dependency
- root previous version
- root new version
- changed-path impact tags
- depth
- local blast radius
- explanatory message

This preserves both direct explanation and root-chain auditability.

## 6. Human Locks
Human Locks still prevent automatic creative mutation. For non-critical changes, if promotion would affect a Human-locked downstream production decision, promotion requires an explicit dry-run review + confirmation:

```text
PROMOTION_LOCKED_IMPACT_CONFIRMATION_REQUIRED
```

Safety / factual / rights invalidation is not allowed to disappear merely because a lock exists. Such conditions may still stale or block eligibility while preserving the Human-locked decision content itself.

## 7. Live vs historical graph
For Core Objects, Build 004 propagates only into live versions:
- current `ACTIVE`
- current `HEAD`

Middle historical versions are not mutated by new live project changes.

Frozen history boundaries stop live propagation:
- `RELEASE` with `state = RELEASED`
- `CHECKPOINT` with `checkpoint_class = FINAL_PROJECT`

Artifact lifecycle currently uses immutable exact records; a dedicated Artifact Registry HEAD/ACTIVE lifecycle remains outside Build 004.

## 8. Revalidation
`REVALIDATE` is a runtime dependency state, not a Common ObjectStatus.

An explicit dependency revalidation can clear the runtime invalidation without creating a new decision version when all exact dependencies are still resolvable and valid. Dependency-derived stale reasons can likewise be cleared without changing the decision hash.

## 9. Dependency Impact Report
Every ACTIVE promotion from one exact version to another generates a versioned:

```text
DEPENDENCY_IMPACT_REPORT
```

The report is a checksummed Artifact and contains the root change, Change Set, impacts, frozen boundaries, blast radius, and exact pinned Dependency Policy reference.

## 10. Cold-start recompute
If dependency projections are structurally consistent, a fresh State Engine process performs full live dependency recomputation from exact refs against the reconstructed ACTIVE graph.

If a current object still references an older exact upstream version and the trusted ACTIVE version has changed meaningfully, stale/revalidation state is reconstructed without relying on conversation memory or an old in-process cache.

If projection integrity itself fails, the runtime enters:

```text
READ_ONLY
```

and mutation is denied until recovery/migration corrects the persisted state.

## 11. Build 004 implementation bug found and repaired
Machine testing exposed an older Semantic Validator bug: order uniqueness counted immutable versions of the **same stable ID** as multiple objects. An ACT v1 and ACT v2 could therefore falsely collide with themselves.

Build 004 corrects `global_order_uniqueness` so history retention does not create a false duplicate. Distinct stable object identities still cannot share the same order within the same parent candidate state.

This is an implementation bug fix only; the frozen Schema v1 contract remains unchanged.

## Validation result
```text
validate_schemas.py           PASS — 68 schemas/contracts
validate_semantics.py         PASS
dependency_engine_smoke.py    PASS
state_engine_smoke.py         PASS
pytest                         52 passed
```

## Boundary after Build 004
Implemented:
- Schema v1 physical contracts
- Semantic Validator core
- Registry / State Engine foundation
- Dependency Engine / stale propagation

Not yet implemented:
- Gate Engine
- formal Project transition evidence evaluation
- durable runtime persistence
- final Git repository / GitHub publication

Next build: **Build 005 — Gate Engine + State Transition**.

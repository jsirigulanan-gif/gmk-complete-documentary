# GMK Schema v1 — Build 006 Changelog

## Added
- `gmk_state/artifact_registry.py`
  - immutable Artifact Registry snapshots
  - Artifact HEAD tracking
  - artifact payload checksum + full record checksum
  - exact artifact version locators
- generic State Transaction artifact mutation APIs
  - `create_artifact()`
  - `create_artifact_version()`
- `gmk_runtime/` persistent runtime package
  - Project Manifest compiler
  - atomic filesystem persistence
  - immutable object/artifact/registry snapshot storage
  - current manifest pointer
  - Cold Start loader and fail-closed integrity checks
- `tools/runtime_cold_start_smoke.py`
- runtime persistence / tamper / cold-start regression tests

## Completed frozen-contract behavior
- all standard Core Object registries now exist from bootstrap as empty versioned registries
- Artifact Registry is separate from Core Object registries and is versioned independently
- Project Manifest pins every standard registry plus `ARTIFACT_REGISTRY` by exact version + SHA-256
- Project Manifest pins Schema v1 + GMK Policy Bundle + current project-level refs
- persisted HEAD and ACTIVE are reconstructed exactly; Cold Start does not infer ACTIVE from HEAD
- Cold Start verifies Manifest, Policy Bundle, Registry snapshots, object records, artifact records and current refs
- latest checkpoint remains only a manifest pointer; it does not override newer manifest state
- audit log and gate evaluation history survive restart
- dependency state is recomputed on Cold Start and fails closed if projection integrity is invalid

## Compatibility implementation note
Build 006 implements an already-frozen Implementation 1C requirement that bootstrap creates empty standard registries. This changes initial Registry version semantics from “missing until first object” to “version 1 empty snapshot,” which is the locked contract. No Core Object, authority model, Project State, schema identity, or production decision semantics changed.

## Contract status
`GMK_SCHEMA_V1_CONTRACT = FROZEN`

No 2K/schema redesign was introduced.

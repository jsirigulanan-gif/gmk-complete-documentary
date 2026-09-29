# GMK Schema v1 — Build 007 Changelog

## Added
- `gmk_operations/`
  - Operation Runtime
  - idempotency collision/replay protection
  - RUNNING-before-side-effect execution boundary
  - `UNKNOWN_EXTERNAL_STATE` reconciliation
  - restart reconciliation for interrupted RUNNING operations
- `gmk_incident/`
  - Incident Runtime
  - policy-derived Safety Controller
  - `NORMAL / SAFE_MODE / READ_ONLY / EMERGENCY_STOP`
- `gmk_recovery/`
  - Checkpoint Runtime
  - Checkpoint verification
  - Restore Plan compiler
  - history-preserving restore execution
- `PROJECT_MANIFEST_SNAPSHOT` Artifact contract
- `REGISTRY_SNAPSHOT_BUNDLE` Artifact contract
- explicit OPERATION authorization evidence (`human_confirmed`, optional Checkpoint ref)
- Build 007 runtime tests and smoke tool

## Runtime behavior completed
- same idempotency key + same intent reuses the existing Operation rather than causing a duplicate external side effect
- same idempotency key + different intent fails closed
- uncertain external outcomes cannot be retried until reconciled
- PUBLISH / DELETE_EXTERNAL require Human confirmation and a verified Checkpoint under pinned v1 policy
- Incident records do not directly set global mode; policy derives the effective safety mode
- incident safety state survives persistence and Cold Start
- Restore creates a new current state and never deletes later object/artifact history
- Core Object HEAD never moves backwards during restore
- Artifact HEAD never moves backwards; baseline artifact content is restored as a new Artifact version
- OPERATION / INCIDENT / RELEASE / CHECKPOINT truth is preserved across restore because external/historical truth cannot be rolled back by project-state restoration

## Implementation corrections discovered by Build 007
1. `CHECKPOINT.integrity_summary` is a string enum in the frozen schema; the Build 006 semantic rule incorrectly treated it like an object. Fixed to match the frozen contract.
2. Persisted Dependency Impact Reports now enrich Artifact dependency nodes to full exact `ArtifactRef` (`artifact_id`, `artifact_type`, `version`, `sha256`). Internal graph NodeKeys remain lightweight. This fixes a cross-artifact `$ref` compatibility defect exposed by Checkpoint artifacts.
3. OPERATION now records explicit authorization evidence needed by the already-locked destructive-operation policy. This is an additive implementation completion, not a new authority model.
4. Two infrastructure Artifact contracts were added for the snapshot pointers already required by the frozen CHECKPOINT contract. No Core Object was added.

## Validation
```text
JSON Schema / artifact contracts   70 PASS
Local $ref resolution              PASS
Semantic smoke                     PASS
State Engine smoke                 PASS
Dependency Engine smoke            PASS
Gate Engine smoke                  PASS
Runtime Cold Start smoke           PASS
Operation/Incident/Recovery smoke  PASS
pytest                              84 passed
```

## Contract status
`GMK_SCHEMA_V1_CONTRACT = FROZEN`

No new Core Object and no 2K/schema redesign were introduced.

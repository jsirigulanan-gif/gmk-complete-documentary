# GMK Operation / Incident / Recovery Runtime Report — Build 007

## 1. Operation Runtime
The `OPERATION` Core Object is now the durable external-side-effect execution record.

Execution boundary:
```text
PLAN
  -> idempotency check
  -> policy / incident safety check
  -> OPERATION PLANNED
  -> OPERATION RUNNING persisted
  -> external adapter call
  -> SUCCEEDED / PARTIALLY_SUCCEEDED / FAILED
     OR UNKNOWN_EXTERNAL_STATE
```

A process must never blindly retry `UNKNOWN_EXTERNAL_STATE`. It must reconcile the external provider first.

### Exactly-once intent
Build 007 provides exactly-once **intent**, not a false claim of ACID semantics across the internet:
- duplicate same intent -> existing Operation is returned
- duplicate key with different intent -> fail closed
- RUNNING persisted before side effect
- restart can quarantine interrupted RUNNING state as UNKNOWN
- UNKNOWN must be reconciled before retry

## 2. Incident Safety Controller
`INCIDENT` remains evidence of an operational/safety event. Global safety mode is derived by policy from ACTIVE unresolved Incidents and containment actions.

```text
NORMAL
SAFE_MODE
READ_ONLY
EMERGENCY_STOP
```

Normal State Engine mutations are rejected while a non-NORMAL incident safety mode is active. Recovery-authorized transactions remain available for containment, incident resolution and checkpoint restoration.

Critical safety state is reconstructed after Cold Start instead of being discarded or misclassified as dependency corruption.

## 3. Checkpoint Runtime
Checkpoint creation captures the pre-checkpoint authoritative state using:
- `PROJECT_MANIFEST_SNAPSHOT`
- `REGISTRY_SNAPSHOT_BUNDLE`
- exact system pins
- exact important Artifact refs
- immutable CHECKPOINT Core Object

Checkpoint validation verifies Manifest and Registry snapshot checksums before restore planning.

## 4. Restore Runtime
Restore is history-preserving:
```text
Checkpoint
 -> Verify
 -> RESTORE_PLAN
 -> verify plan still current
 -> Human confirmation
 -> restore production ACTIVE selections
 -> recreate baseline Artifact current content as NEW Artifact HEAD versions
 -> dependency full recompute
 -> NEW Manifest version
```

Restore never deletes post-checkpoint versions and never rewinds Core Object HEAD.

The following live/historical truth registries are intentionally preserved rather than rewound:
- `CHECKPOINT_REGISTRY`
- `OPERATION_REGISTRY`
- `INCIDENT_REGISTRY`
- `RELEASE_REGISTRY`

This enforces the frozen rule that restoring GMK project state does not pretend to reverse external actions, incidents, releases, or checkpoint history.

## 5. Cold Start compatibility
Persisted active Incident state is reconstructed and safety mode is re-derived. Dependency-integrity corruption still fails closed independently.

## 6. Validation result
```text
validate_schemas.py                    PASS — 70
validate_semantics.py                  PASS
state_engine_smoke.py                  PASS
dependency_engine_smoke.py             PASS
gate_engine_smoke.py                   PASS
runtime_cold_start_smoke.py            PASS
operation_incident_recovery_smoke.py   PASS
pytest                                  84 passed
```

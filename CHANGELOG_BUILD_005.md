# GMK Schema v1 — Build 005 Changelog

## Added
- `gmk_gate/` runtime package
  - `engine.py`
  - `models.py`
  - `policy.py`
- executable Gate definitions and Project State transition policy in `config/gates_policies.yaml`
- Gate policy hash pin update in `config/gmk_policy_bundle.yaml`
- `tools/gate_engine_smoke.py`
- Gate Engine test suite
- transactional Gate revalidation on State Engine commit
- Gate evaluation history in runtime state
- exact current evidence invalidation logic
- scoped blocker derivation
- explicit Human-only `REENTER_STAGE`
- derived `Next Legal Action`

## Changed
- `StateTransaction.transition_project_state()` now uses Gate Engine authority instead of requiring an external authorizer.
- optional legacy/custom transition authorizer remains only as an additional veto hook; it cannot bypass Gate Engine failure.
- Project State transition tests updated to frozen Implementation 1F behavior.

## Contract status
No Core Object, authority model, frozen schema contract or Project State enum was changed.

`GMK_SCHEMA_V1_CONTRACT = FROZEN`

# GMK Schema v1 — Gate Engine Report (Build 005)

## Status
`GATE_ENGINE = IMPLEMENTED`

Build 005 implements the frozen Implementation 1F contract without changing the frozen Schema v1 architecture.

## Implemented
- version-pinned Gate Policy loaded from `config/gates_policies.yaml`
- policy hash pinned by `GMK_POLICY_BUNDLE`
- all 19 frozen Gate IDs defined
- all 21 adjacent Project State transitions defined exactly once
- transition permission classes:
  - `AUTO_ALLOWED`
  - `AI_WITH_RULES`
  - `HUMAN_APPROVAL_REQUIRED`
  - `HUMAN_ONLY`
  - `FORBIDDEN`
- exact current evidence evaluation
- Gate result computation: `PASS / WARN / FAIL`
- WARN transition policy with exact Exception Approval support
- historical immutable gate snapshots recorded on committed transitions
- effective historical gate validity can become `INVALIDATED`
- artifact-head and Core Object ACTIVE freshness checks
- dependency/stale invalidation awareness
- scoped blockers from Research Gaps, QA Issues and Incidents
- fail-closed safety-mode behavior
- direct Project State jumps forbidden
- explicit Human-only `REENTER_STAGE` for backwards re-entry
- transactional Gate re-evaluation immediately before commit
- derived `Next Legal Action`
- Project completion predicate requiring a RELEASED Release and valid Final Project Checkpoint

## Formal Gate mapping
```text
BOOTSTRAPPED              --BOOTSTRAP----------> RESEARCH_INTAKE
RESEARCH_INTAKE           --RESEARCH_AUDIT-----> RESEARCH_AUDITED
RESEARCH_AUDITED          --ROUGH_NARRATIVE----> ROUGH_NARRATIVE_READY
ROUGH_NARRATIVE_READY     --VISUAL_REQUIREMENTS-> VISUAL_REQUIREMENTS_READY
VISUAL_REQUIREMENTS_READY --predicate-----------> ASSET_RECON
ASSET_RECON               --ASSET_RECON--------> ASSET_CATALOG_READY
ASSET_CATALOG_READY       --VISUAL_COVERAGE----> VISUAL_COVERAGE_READY
VISUAL_COVERAGE_READY     --SCRIPT-------------> SCRIPT_READY
SCRIPT_READY              --TTS----------------> TTS_READY
TTS_READY                 --VOICE--------------> VOICE_LOCKED
VOICE_LOCKED              --DESIGN_DNA---------> DESIGN_DNA_APPROVED
DESIGN_DNA_APPROVED       --SCENE_PLAN---------> SCENE_PLAN_READY
SCENE_PLAN_READY          --SHOT_PLAN----------> SHOT_PLAN_READY
SHOT_PLAN_READY           --predicate-----------> HTML_REVIEW
HTML_REVIEW               --HTML_REVIEW--------> HTML_APPROVED
HTML_APPROVED             --PRODUCTION_LOCK----> PRODUCTION_RENDER
PRODUCTION_RENDER         --RENDER + SHOT_QA---> SHOT_QA_PASSED
SHOT_QA_PASSED            --SCENE_QA-----------> SCENE_QA_PASSED
SCENE_QA_PASSED           --FULL_FILM_QA-------> FULL_FILM_QA_PASSED
FULL_FILM_QA_PASSED       --DELIVERY-----------> DELIVERY_READY
DELIVERY_READY            --completion predicate> PROJECT_COMPLETED
```

## Evidence freshness rule
A historical Gate PASS is not permanently current. Effective validity becomes `INVALIDATED` when exact evidence is no longer current, including:
- Core Object evidence is no longer `ACTIVE`
- Artifact evidence is no longer the current head for that artifact identity
- evidence is stale/blocked/rejected/archived
- dependency invalidation is active
- a new scoped blocker appears

Historical evaluation data itself is never rewritten.

## Transition transaction rule
A transition is evaluated when requested and re-evaluated against the **final staged transaction state** immediately before commit. This prevents this invalid sequence:

```text
Gate PASS
→ stage transition
→ same transaction introduces blocker/stale evidence
→ commit anyway   ❌
```

Build 005 now rejects it with `PROJECT_STATE_TRANSITION_REVALIDATION_FAILED`.

## Blocker scoping
Blockers are not global by default.

Examples implemented:
- `RESEARCH_GAP.blocked_gates[]` blocks only the declared Gate IDs.
- unresolved Critical QA Issues block production/delivery gates, not Research gates.
- Critical unresolved Incidents are system-level transition blockers.
- runtime safety mode blocks Project State transition / re-entry.

## Next Legal Action
The Gate Engine derives one of the following based on current state/evidence/policy:
- `TRANSITION_PROJECT_STATE`
- `SATISFY_GATE_REQUIREMENTS`
- `RESOLVE_BLOCKER`
- `ACCEPT_WARNING_OR_REPAIR`
- `REQUEST_HUMAN_AUTHORIZATION`
- `NO_LEGAL_TRANSITION`

It does not perform repairs or invent evidence.

## Validation result
```text
validate_schemas.py           PASS — 68 schemas/contracts
validate_semantics.py         PASS
state_engine_smoke.py         PASS
dependency_engine_smoke.py    PASS
gate_engine_smoke.py          PASS
pytest                         64 passed
```

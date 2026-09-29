# GMK Schema v1 — Semantic Validator Suite / Build 002

Build 002 moves the frozen data contract from structural-only validation into executable cross-object semantics.

## Implemented foundation
- `StateView` exact-version resolver for Core Objects and Artifacts
- immutable `ValidationIssue` model with stable error codes
- deterministic decision-hash projection for exact-version approvals
- schema catalog for root field annotations, including live-derived fields
- object-level and project-state-level semantic rule orchestration
- CLI: `tools/validate_semantics.py`

## Implemented semantic rule groups
- Core lineage, contiguous versions, exact supersedes, stable-ID type consistency
- stale/status consistency and Human Constraint carry-forward
- Project runtime constraints
- Research reference typing, Evidence locator checks, quote/technical evidence completeness
- Claim evidence uniqueness, DISPROVEN counter-evidence requirement, production-use consistency
- Contradiction resolution requirements and Research Gap resolution/attempt typing
- Asset Recon viable-candidate inspection requirements, acquisition/file requirements, rights blocking, segment time bounds
- Narrative parent typing, claim/evidence bindings, narration certainty ceiling, promise/payoff pairing
- Voice block reference typing and TTS artifact typing
- Design rule traceability warnings
- Planning: non-base comprehension purpose, motion purpose, 3D grounding, Cue animation order, exactly one Base Layer, exact Primary Beat, Cue target containment, transition justification, absolute timing range
- Review: Approval exact target hash + Review Package context; Edit Request constraint requirements; Revision lineage / Human Constraint preservation checks
- Render: Final requires Production Lock; frozen input containment; retry hard limit; Render Manifest technical-pass consistency
- QA: root cause before repair, retest before resolution, QA report issue/summary/result consistency
- Checkpoint false-pass guard
- Operations attempt ordering
- Incident containment/verification
- Release Production Lock/QA/operation/time/lineage checks
- Parent-local order uniqueness across ACT/SCENE/NARRATION_BEAT/SHOT

## Deliberately deferred to later runtime engines
The validator suite does **not** pretend to implement runtime mutation or derivation. The following remain separate build work:
- registry HEAD/ACTIVE mutation engine and optimistic transactions
- dependency projection compiler + stale propagation engine
- gate evaluator + project state transition engine + Next Legal Action
- Voice Timing Map anchor resolver
- Production Lock compiler and frozen dependency snapshot compiler
- renderer prompt compiler / adapter execution
- QA automation and repair executor
- operation reconciliation against real external providers
- incident recovery executor
- release compiler and delivery executor

These are runtime engines, not schema semantics.

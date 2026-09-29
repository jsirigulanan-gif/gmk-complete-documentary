# Rough Narrative Runtime

Build 013 adds `gmk_narrative.RoughNarrativeRuntime` and the CLI command `gmk rough-narrative`.

The runtime is allowed only from `RESEARCH_AUDITED`. It converts an explicit narrative plan into active `ACT`, `SCENE`, and `NARRATION_BEAT` Core Objects plus one immutable `NARRATIVE_SPINE` Artifact, then evaluates the `ROUGH_NARRATIVE` gate and may transition to `ROUGH_NARRATIVE_READY`.

## Research boundary

A Beat may bind only the current exact version of a Claim whose Research Audit state is production-eligible and whose `production_use.narration_allowed` is true. `PROHIBITED`, stale, blocked, archived, rejected, `UNREVIEWED`, `INSUFFICIENT_EVIDENCE`, `CONTESTED`, `DISPROVEN`, and `UNRESOLVED` claims fail closed.

This stage does **not** create final narration and does **not** create visual requirements. Beats are committed as `workflow_state: RESEARCH_BOUND`; Build 014 is expected to turn these into visual requirements and move toward `VISUAL_REQUIREMENTS_READY`.

## Idempotency

`batch_id` is bound to SHA-256 of the complete narrative-plan JSON. Replaying the same batch returns the existing graph. Reusing the same batch ID with changed content fails with `ROUGH_NARRATIVE_BATCH_ID_COLLISION`.

## CLI

```bash
python -m gmk_cli rough-narrative \
  --workspace pilot/PT_WORKSPACE \
  --input pilot/PT_ROUGH_NARRATIVE_INPUT.json \
  --output pilot/PT_ROUGH_NARRATIVE_REPORT.json \
  --json
```

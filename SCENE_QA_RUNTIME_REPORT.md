# Gamer Must Know — Build 031 Scene QA Runtime Report

## Scope
Build 031 implements explicit Scene-level QA after Shot QA has passed. It does not infer Scene quality from the absence of Shot findings. A reviewer must submit a complete per-Scene checklist and any additional findings.

## Required Scene review dimensions
Each active Scene must explicitly report:

- `shot_continuity`
- `visual_continuity`
- `audio_continuity`
- `narrative_flow`
- `coverage`

Allowed values are `PASS`, `WARN`, and `FAIL`. WARN becomes a MINOR Scene QA issue; FAIL becomes a MAJOR Scene QA issue. The generated root-cause categories are mapped to existing frozen QA enums rather than introducing new schema vocabulary.

## Evidence boundary
For every active Scene, the runtime verifies that:

1. its current `SCENE_PLAN` references current active Shots;
2. every referenced Shot has a latest `SHOT_QA` report;
3. that latest Shot report is `PASS`;
4. all those Shot reports point to the same exact current Final Render output;
5. the operator supplied one explicit Scene review entry.

Only then is a `SCENE_QA` report created for that Scene.

## Retest behavior
A failed Scene QA does not permanently poison the project. A later PASS retest becomes the current Gate evidence and explicitly resolves earlier open Scene QA issues using the new verification report.

## Transition

```text
SHOT_QA_PASSED
      ↓
 explicit Scene reviews
      ↓
 current PASS Shot-QA evidence aggregation
      ↓
 SCENE_QA Gate
      ↓
SCENE_QA_PASSED
```

WARN does not auto-transition because the frozen transition policy requires an exception for WARN; Build 031 transitions only on PASS.

## Validation
- Build 031 integration: **5/5 PASS**
- Build 028: **4/4 PASS**
- Build 029: **5/5 PASS**
- Build 030: **4/4 PASS**
- Gate tests: **12/12 PASS**
- Semantic tests: **22/22 PASS**
- Targeted total: **52 PASS**
- Schema/contracts: **79 PASS**
- Semantic validation: **PASS**
- Semantic smoke: **PASS**
- Gate Engine smoke: **PASS**
- Production Render/QA smoke: **PASS**
- Build smoke: **2/2 PASS**
- Python compileall: **PASS**
- CLI `scene-qa`: **REGISTERED**
- real P.T. pilot: **FAIL-CLOSED at `ASSET_RECON`**

## Next
Build 032 should implement explicit Full Film QA aggregation and the transition `SCENE_QA_PASSED → FULL_FILM_QA_PASSED` using the existing Viewer Experience / Production Integrity / Delivery Integrity QA passes.

# Gamer Must Know — Build 030 Render Execution / Shot QA Report

## Scope
Build 030 implements the operator path from an approved Project Production Lock through actual Final Render ingestion/execution and complete Shot QA coverage.

## Boundary
Build 030 does **not** invent renderer success or Shot QA. The operator must provide:

1. an actual local video file that passes `ffprobe`, and
2. an explicit review record for every current ACTIVE Shot.

The exact render bytes are SHA-256 hashed and copied into immutable workspace media storage. Every Shot review is separately hashed into the QA profile used by its persisted `SHOT_QA` report.

## Proven isolated path

```text
HTML_APPROVED
→ PRODUCTION_RENDER
→ actual Project Final Render
→ explicit Shot QA coverage
→ RENDER Gate PASS
→ SHOT_QA Gate PASS
→ SHOT_QA_PASSED
```

## QA retest correction
Prior Gate behavior considered every historical QA report for a scope. That made one old FAIL permanently poison a later successful retest. Build 030 corrects Gate evaluation to use the latest current QA report per scope. A PASS Shot retest also resolves prior unresolved Shot QA issues with the new PASS report as the verification reference.

This is a runtime/Gate correctness fix; it does not change any schema contract or Gate ID.

## Validation
- Schema / Artifact contracts: **79 — PASS**
- Semantic validation: **PASS**
- Build 030 integration: **4 passed**
- Build 024–027 partition: **15 passed**
- Build 028: **4 passed**
- Build 029: **5 passed**
- Build 030: **4 passed**
- Gate + Semantic: **34 passed**
- Production/Render/Release compatibility subset: **16 passed**
- Production Render / QA smoke: **PASS**
- Gate Engine smoke: **PASS**
- Repository layout audit: **PASS**
- Python compileall: **PASS**
- CLI `render-shot-qa`: **REGISTERED**
- CLI against the real P.T. pilot: **FAIL-CLOSED at `ASSET_RECON`**

## P.T. pilot
The real P.T. pilot remains at `ASSET_RECON`, with the two source-locked external video assets still pending. No isolated render output, QA report, or future-state transition was written into the real pilot workspace.

## Next
Build 031 should implement the `SHOT_QA_PASSED → SCENE_QA_PASSED` operator stage, aggregating current Shot QA into explicit Scene QA without silently treating Shot-level success as Scene-level editorial success.

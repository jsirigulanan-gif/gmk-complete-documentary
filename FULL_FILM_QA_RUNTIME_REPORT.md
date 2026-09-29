# GMK Schema v1 — Build 032 Full Film QA Runtime Report

## Scope
Build 032 connects `SCENE_QA_PASSED` to the frozen `FULL_FILM_QA` Gate without treating an empty findings list as sufficient evidence of review.

## Runtime behavior
- Requires current PASS `RENDER`, `SHOT_QA`, and `SCENE_QA` gates.
- Requires the latest `SCENE_QA` report for every active Scene to be `PASS`.
- Requires all Scene QA reports to observe the same exact Final `RENDER_OUTPUT`.
- Resolves the exact Project Production Lock through `RENDER_OUTPUT → RENDER_JOB → production_lock`.
- Requires one explicit reviewer and all required checks for three independent passes:
  - Viewer Experience QA
  - Production Integrity QA
  - Delivery Integrity QA
- Converts checklist WARN/FAIL states into real `QA_ISSUE` findings using valid frozen root-cause categories.
- Pins each review payload into the corresponding QA profile SHA-256 while preserving the original Build 009 API.
- Creates the existing `FULL_FILM_QA` aggregate report and `FULL_FILM_QA_PACKAGE`.
- A later PASS retest resolves prior Full Film QA issues verified by the new aggregate report.
- Uses an immutable batch review ledger and rejects batch-ID collisions.
- Transitions to `FULL_FILM_QA_PASSED` only when the frozen `FULL_FILM_QA` Gate is PASS.

## Validation
- Build 032 integration: **5 PASS**.
- Build 009 + Build 030–031 compatibility: **12 PASS**.
- Gate + Semantic: **34 PASS**.
- Targeted total: **51 PASS**.
- Schema/contracts: **79 PASS**.
- Semantic validation/smoke: **PASS**.
- Gate smoke: **PASS**.
- Full Film QA smoke: **PASS**.
- Python compileall: **PASS**.
- CLI `full-film-qa`: **REGISTERED / FAIL-CLOSED ON REAL P.T. PILOT**.

## Schema impact
None. No Core Object, Artifact contract, Project State, Gate ID, or approval authority was added or changed. Schema status remains `FROZEN_WITH_ERRATA_024_025_029`.

## P.T. pilot
The real P.T. pilot remains at `ASSET_RECON` because the two source-locked external video Assets are still pending. Build 032 proves the later Full Film QA path only in an isolated valid workspace; it does not bypass earlier gates.

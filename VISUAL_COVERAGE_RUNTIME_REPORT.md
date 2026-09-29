# GMK Build 020 — Visual Coverage Runtime Report

## Scope
Build 020 implements the missing runtime boundary between a completed Asset Catalog and the frozen `VISUAL_COVERAGE` Gate. It does not pre-advance the durable P.T. pilot and does not substitute media for its two pending source locks.

## Runtime checks
Before transition, `VisualCoverageRuntime` requires:

1. Project state exactly `ASSET_CATALOG_READY` (or idempotent replay from `VISUAL_COVERAGE_READY`).
2. An active `ASSET_COVERAGE_REPORT` with `PASS` or `WARN`.
3. At least one active Narration Beat.
4. Every active Beat key covered by at least one `SEGMENT` with `production_state=VERIFIED` and `extensions.asset_acquisition.production_ready=true`.
5. Normal Gate/State Engine transition through `VISUAL_COVERAGE`, not a direct state assignment.

## QA lifecycle correction
Build 017 correctly created blocking coverage QA issues while source media was missing. A later successful coverage retest created a PASS report but did not resolve those historical issues. Because `NO_BLOCKERS` considers active QA issues, the project could remain blocked even with 10/10 coverage.

Build 020 fixes that lifecycle boundary. After a PASS/WARN coverage retest, open coverage issues are resolved against the new verification report before the catalog transition is attempted.

## Durable P.T. state
The real pilot remains intentionally unchanged:

```text
Project State       ASSET_RECON
Cataloged Assets    8/10
Pending videos      2
Verified Segments   8
Next target         ASSET_CATALOG_READY
```

## Tested completion path
An isolated workspace copy with valid video bytes for the two exact source locks proves:

```text
media handoff
  → coverage PASS
  → historical coverage blockers RESOLVED
  → ASSET_CATALOG_READY
  → visual-coverage runtime
  → VISUAL_COVERAGE_READY
```

Synthetic/generated test clips are test fixtures only and are never persisted into the durable P.T. pilot.

# Gamer Must Know — Build 016 Asset Selection / Acquisition Planning Report

## Scope
Build 016 closes the remaining P.T. Asset Recon search gap, issues the Search Completion Certificate, explicitly selects one primary candidate per active Beat, creates production Asset identities, and plans acquisition Operations.

## Durable P.T. state
```text
Project State                  ASSET_RECON
SEARCH objects                 21
SEARCH_RESULT objects          31
Search Again executions        1
Lisa comparison                MEETS_TARGET (v2)
Search Completion Certificate  PASS
Selected/promoted candidates   10
ASSET objects                  10
ASSET state                    ACQUISITION_PENDING (10)
DOWNLOAD Operations            PLANNED (10)
SEGMENT objects                0
ASSET_RECON Gate               PASS
Transition to catalog          DELIBERATELY DEFERRED
Safety Mode                    NORMAL
Manifest Version               54
```

## Lisa Search Again closure
The prior Lisa comparison remains immutable as version 1 (`NEEDS_SEARCH_AGAIN`). Build 016 adds a round-2 Search execution and a direct original-creator candidate, then creates Candidate Comparison version 2 with three viable candidates across three source families: `NEWS_ARCHIVE`, `RESEARCHER`, and `ORIGINAL_CREATOR`.

The selected direct-media candidate is the traced Lance McDonald September 2019 post demonstrating the P.T. camera hack. The production constraint remains unchanged: the evidence supports the attachment/following relationship, not an invented exact numerical distance.

## Search Completion
`SEARCH_COMPLETION_CERTIFICATE` is persisted as `QA_REPORT` and evaluates `PASS` because all ten current Beats meet their current candidate/source-family targets after Search Again.

## Selection and acquisition boundary
Ten candidate decisions are explicitly promoted to Asset identities. Every Asset is still `ACQUISITION_PENDING` and has an exact `acquisition_operation_ref` to a planned idempotent `DOWNLOAD` Operation.

Build 016 intentionally does **not**:
- invent an `original_file` URI/checksum,
- mark an acquisition as succeeded without bytes,
- mark any Asset production-ready,
- create any `SEGMENT`,
- transition the project to `ASSET_CATALOG_READY` merely because the formal Search gate is now PASS.

This preserves the frozen rule: discovery/selection intent is not equivalent to acquired, verified media.

## Validation
```text
Schema / Artifact Contracts    76 — PASS
Local $ref Resolution          PASS
Structural Validation          PASS
Semantic Validation            PASS
Build 015 + 016 tests          9 PASSED
All test groups                122 PASSED (partitioned execution)
State / Dependency / Gate      PASS
Cold Start / Recovery          PASS
Operation / Incident           PASS
Render / QA / Release smoke    PASS
Python compileall              PASS
```

## Next
Build 017 should execute the planned acquisition Operations against actual retrievable source bytes, compute immutable SHA-256 checksums, capture technical metadata, perform rights/provenance review, move valid Assets through `ACQUIRED → FILE_VERIFIED → CATALOGED`, and only then create verified `SEGMENT` objects and the first `ASSET_COVERAGE_REPORT`.

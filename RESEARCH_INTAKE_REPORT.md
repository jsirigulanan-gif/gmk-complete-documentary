# GMK Schema v1 — Build 011 Research Intake Report

## Scope
P.T. Pilot Bootstrap + Research Intake Runtime.

Pilot input: **[Research Pack] The Ghost of P.T. & The Erasure of Hideo Kojima (LEMiNO Pipeline).docx**

Input SHA-256:
`0243aad58e88e29094461e654782ce4bd007dab6500d82a729baf870c092671e`

## Deterministic parse result
The Build 011 parser extracted from the supplied pack:

```text
Claim candidates                 13
External source leads             5
Quote leads                       4
Pack unresolved questions         3
Explicit contradictions           0
```

The parser does not invent a contradiction when the pack does not explicitly contain conflicting evidence.

## Registered authoritative runtime records
Research Intake created:

```text
PROJECT                            1  (already bootstrapped)
SOURCE                             1  (the immutable Research Pack itself)
EVIDENCE                          13  (pack-content excerpts only)
CLAIM                             13  (all UNREVIEWED)
RESEARCH_GAP                       4  (3 pack questions + 1 system guard)
RESEARCH_ATTEMPT_LOG artifact      1 identity / 2 immutable versions
```

The 5 external source-library entries and 4 quotes are retained as **non-authoritative intake leads** for later Research Audit. They are not silently promoted into independently inspected SOURCE/EVIDENCE records.

## Truth-safety behavior
Pack labels such as `VERIFIED FACT` are preserved only as intake metadata. Imported claims are stamped:

```text
verification_state = UNREVIEWED
certainty.level     = UNKNOWN
production_use      = PROHIBITED
```

Each intake Evidence record references the Research Pack SOURCE, with `CONTEXTUALIZES` / `CONTEXT_ONLY`. It proves only that the pack contains the assertion.

The Research Pack SOURCE is `authority_class = UNKNOWN`.

A system-created `CRITICAL` Research Gap blocks `RESEARCH_AUDIT` until independent source/evidence verification is performed.

## Durable pilot workspace
Packaged workspace:

`pilot/PT_WORKSPACE`

Cold Start reconstructs:

```text
Project State       RESEARCH_INTAKE
Safety Mode         NORMAL
Loaded Objects      32
Loaded Artifacts     3
Manifest Version     3
Next Legal Action   RESOLVE_BLOCKER
Target State        RESEARCH_AUDITED
Blocking Gate       RESEARCH_AUDIT
```

Running Research Intake a second time with the same pack SHA-256 returns an idempotent replay and does not duplicate research records.

## Validation

```text
Schema/contracts                         PASS — 75
Semantic validation                      PASS
State Engine smoke                       PASS
Dependency Engine smoke                  PASS
Gate Engine smoke                        PASS
Cold Start smoke                         PASS
Operation / Incident / Recovery smoke    PASS
Production / Render / QA smoke           PASS
Release / Orchestrator E2E smoke         PASS
Build 010 CLI tests                      PASS — 3
Build 011 Research Intake tests          PASS — 3
Research Intake real-pack smoke          PASS
Repository layout audit                  PASS
Full pytest                              PASS — 97
```

## What this build does NOT claim
- It does not verify any external URL.
- It does not confirm the Research Pack's `VERIFIED FACT` labels.
- It does not authenticate quotes against original recordings/transcripts.
- It does not resolve source independence or corroboration.
- It does not pass `RESEARCH_AUDIT`.
- It does not begin Asset Recon or final narrative production.

## Next implementation boundary
The next logical build is **Research Audit Runtime**: inspect external source leads, create real SOURCE/EVIDENCE records from inspected material, revise Claim verification/production-use state, detect contradictions, and resolve or preserve Research Gaps without silently rewriting the original Research Pack.

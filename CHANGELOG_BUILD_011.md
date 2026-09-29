# GMK Schema v1 — Changelog Build 011

## Added
- deterministic DOCX Research Pack parser (`gmk_research`);
- Research Intake runtime that enters `RESEARCH_INTAKE` through Gate/State authority;
- safe Research Pack SOURCE registration;
- contextual Evidence + UNREVIEWED Claim creation for labeled pack assertions;
- source-lead, quote-lead and unresolved-question extraction;
- CRITICAL Research-Audit guard gap;
- intake idempotency keyed by Research Pack SHA-256;
- CLI commands `research-intake` and `pilot-bootstrap`;
- durable packaged P.T. workspace in `pilot/PT_WORKSPACE`;
- P.T. source-lead / quote-lead / unresolved-question reports;
- Build 011 tests and real-pack smoke test;
- Research Intake operator documentation.

## Architecture impact
None. No Core Object, authority rule, Project State, dependency relation, Gate ID, or frozen Schema v1 contract was added or changed.

## Safety correction implemented
Research Pack labels are no longer at risk of being confused with GMK verification state during pilot ingestion. `VERIFIED FACT` in the input remains declared metadata; runtime claims stay `UNREVIEWED`, certainty `UNKNOWN`, and narration `PROHIBITED` until Research Audit.

## GitHub
Still intentionally **NOT CREATED**.

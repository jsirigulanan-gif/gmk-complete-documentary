# GMK Research Intake Runtime

Build 011 introduces a safe bridge between an immutable Research Pack and the GMK Research domain.

## Operator flow

```bash
python -m gmk_cli pilot-bootstrap \
  --workspace "pilot/PT_WORKSPACE" \
  --research-pack "<research-pack.docx>" \
  --json

python -m gmk_cli status --workspace "pilot/PT_WORKSPACE" --json
python -m gmk_cli research-intake --workspace "pilot/PT_WORKSPACE" --json
```

`research-intake` is idempotent for the same Research Pack SHA-256.

## Safety semantics

The parser may extract labels such as `VERIFIED FACT` from the supplied document, but GMK does **not** accept that label as a verification result. Imported assertions are created as:

```text
verification_state = UNREVIEWED
certainty           = UNKNOWN
production_use      = PROHIBITED
```

The Research Pack itself becomes a `SOURCE` with `authority_class = UNKNOWN`. Evidence created during intake proves only what the pack states; its EvidenceLink relation is `CONTEXTUALIZES` with `CONTEXT_ONLY` strength.

A system-created `CRITICAL` `RESEARCH_GAP` blocks `RESEARCH_AUDIT` until independent verification is performed. Source-library URLs and quotes are parsed into non-authoritative intake leads for later Research Audit, not silently promoted into verified external `SOURCE`/`EVIDENCE` records.

## P.T. pack intake coverage

For the supplied P.T. Research Pack, the deterministic parser extracts:

- 13 claim candidates;
- 5 external source leads;
- 4 quote leads;
- 3 pack-authored unresolved questions;
- 0 explicit contradictions.

The runtime registers 13 `CLAIM`, 13 contextual `EVIDENCE`, 1 Research Pack `SOURCE`, the 3 pack gaps plus 1 system Research-Audit guard gap, and a `RESEARCH_ATTEMPT_LOG` artifact.

This stage is **Research Intake**, not Research Audit.

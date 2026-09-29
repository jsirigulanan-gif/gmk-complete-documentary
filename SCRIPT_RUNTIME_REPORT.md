# GMK Build 021 — Script Runtime Report

## Scope
Build 021 implements the production Script stage that follows `VISUAL_COVERAGE_READY`.

The runtime does not treat the Gate's minimal artifact-exists predicate as sufficient by itself. Before producing `VOICEOVER_SCRIPT_FINAL`, it verifies complete current Beat coverage, Claim eligibility, narration language policy, Beat visual readiness, and exact decision-hash lineage.

## Runtime contract
```text
Required state              VISUAL_COVERAGE_READY
Active Beats                complete one-to-one narration plan required
Claim refs                  exact ACTIVE/current versions only
Narration eligibility       production_use.narration_allowed = true
Language mode               may not be stronger than bound Claim policy
Beat output state           NARRATION_FINAL
Artifact output             VOICEOVER_SCRIPT_FINAL
Script blocks               exact current Beat refs + decision SHA-256
Gate                        SCRIPT
Success state               SCRIPT_READY
```

## Validation
```text
Build 017-018 regression       7 PASS
Build 019 regression           3 PASS
Build 020 regression           3 PASS
Build 021 regression           4 PASS
Targeted Build total          17 PASS
Gate tests                    12 PASS
Semantic tests                22 PASS
Gate + Semantic total         34 PASS
Python compileall             PASS
CLI script command            PASS
```

## Proven integration path
In an isolated copy of the P.T. workspace with authorized synthetic test-video bytes used only for runtime verification:

```text
ASSET_RECON
  -> ASSET_CATALOG_READY
  -> VISUAL_COVERAGE_READY
  -> SCRIPT_READY
```

The Script stage compiled all 10 active Beats, promoted them to `NARRATION_FINAL`, created the exact `VOICEOVER_SCRIPT_FINAL`, and replayed idempotently.

## P.T. pilot boundary
The durable real pilot is intentionally not advanced by this build. It still lacks the two actual source-locked video byte payloads required by Builds 018-020, so its legal state remains `ASSET_RECON`.

Build 021 therefore proves the next stage without fabricating those missing source bytes or bypassing the earlier Gates.

## Next
After the real pilot receives the two source-locked videos and progresses through Asset Catalog, Visual Coverage, and Script with real evidence, the next frozen state transition is:

```text
SCRIPT_READY
    -> TTS
    -> TTS_READY
```

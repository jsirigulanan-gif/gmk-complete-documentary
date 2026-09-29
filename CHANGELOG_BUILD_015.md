# CHANGELOG — GMK Schema v1 Build 015

## Added
- `CANDIDATE_COMPARISON` artifact contract and semantic rules.
- `gmk_assets.AssetReconRuntime`.
- `gmk asset-recon` CLI workflow.
- P.T. first-pass Asset Recon plan with 20 Search executions and 30 inspected candidate records.
- Candidate comparison artifacts for all 10 active P.T. Beats.
- Asset Recon smoke and Build 015 pytest coverage.

## Fixed
- Aligned semantic CandidateState checks with the frozen enum name `PROMOTED_TO_ASSET` rather than the obsolete implementation token `PROMOTED`.
- Forward-state pilot smoke/tests now recognize `ASSET_RECON` without weakening earlier stage invariants.

## Preserved
- No new Core Object.
- `SEARCH_RESULT ≠ ASSET`.
- No Asset or Segment created in first-pass discovery.
- No Search Completion Certificate fabricated while a critical Beat still requires Search Again.
- No GitHub repository created.

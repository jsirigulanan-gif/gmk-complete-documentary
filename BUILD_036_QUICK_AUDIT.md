# GMK Repository Audit

- Profile: `QUICK`
- Overall: **PASS_WITH_WARNINGS**
- PASS: 16
- FAIL: 0
- TIMEOUT: 0
- WARN: 1
- Report SHA-256: `808f17e6b9cc1b8a979a6624730a4a2c3aa2bd895bf1f8d9b573038da196ed6d`

| Check | Status | Seconds | Detail |
|---|---|---:|---|
| `build_status` | PASS | 0.000 | build=036 schema=FROZEN_WITH_ERRATA_024_025_029_033 |
| `schema_status_consistency` | PASS | 0.000 | FROZEN_WITH_ERRATA_024_025_029_033 |
| `pipeline_complete_marker` | PASS | 0.000 | NONE_CORE_PIPELINE_COMPLETE |
| `readme_current_build` | PASS | 0.000 | Current build:** Build 036 |
| `changelog_continuity_002_current` | PASS | 0.000 | continuous_through=036 |
| `legacy_build001_changelog` | WARN | 0.000 | Build 001 has README history but no standalone CHANGELOG_BUILD_001.md; retained as legacy documentation gap. |
| `errata_ledger_source` | PASS | 0.000 | errata=['024', '025', '029', '033'] |
| `package_hygiene` | PASS | 0.000 | junk_entries=0 |
| `status_contract_count_declared` | PASS | 0.000 | declared=80; artifact_contract_files=35 |
| `pilot_external_media_boundary` | PASS | 0.000 | state=ASSET_RECON pending=['LISA_X_DIRECT_VERIFIED', 'TGA_VIDEO'] |
| `pilot_execution_pack` | PASS | 0.000 | missing=[]; expected=['LISA_X_DIRECT_VERIFIED', 'TGA_VIDEO'] |
| `schema_validator` | PASS | 2.284 | PASS: 80 schemas/contracts structurally valid; all local $refs resolved; valid fixtures passed. |
| `semantic_smoke` | PASS | 0.859 | PASS: semantic smoke checks detected expected cross-field failures. |
| `gate_smoke` | PASS | 1.925 | PASS — Gate Engine evaluated exact evidence, authorized adjacent transition, and recorded immutable gate snapshot. |
| `repo_layout_audit` | PASS | 0.836 | {   "ok": true,   "checks": [     {       "check": "dir:schema",       "ok": true     },     {       "check": "dir:artifacts/contracts",       "ok": true     },     {       "check": "dir:config",       "ok": true     },     {       "check": "dir:fixtures",       "ok": true     },     {       "check": "dir:gmk_state",       "ok": true     },     {       "check": "dir:gmk_semantics",       "ok": true     },     {       "check": "dir:gmk_dependency",       "ok": true     },     {       "check": "dir:gmk_gate",       "ok": true     },     {       "check": "dir:gmk_runtime",       "ok": true     },     {       "check": "dir:gmk_operations",       "ok": true     },     {       "check": "dir:gmk_in |
| `compileall` | PASS | 0.868 |  |
| `pytest_build035_audit` | PASS | 1.971 | ...                                                                      [100%] 3 passed in 0.10s |

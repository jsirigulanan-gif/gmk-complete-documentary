# GMK Repository Audit

- Profile: `QUICK`
- Overall: **PASS_WITH_WARNINGS**
- PASS: 14
- FAIL: 0
- TIMEOUT: 0
- WARN: 1
- Report SHA-256: `dd2c62189bcf42f960c90fcaacc67f1831785807d1aacf79eaea671c2a8a204b`

| Check | Status | Seconds | Detail |
|---|---|---:|---|
| `build_status` | PASS | 0.000 | build=035 schema=FROZEN_WITH_ERRATA_024_025_029_033 |
| `schema_status_consistency` | PASS | 0.000 | FROZEN_WITH_ERRATA_024_025_029_033 |
| `pipeline_complete_marker` | PASS | 0.000 | NONE_CORE_PIPELINE_COMPLETE |
| `changelog_continuity_002_current` | PASS | 0.000 | continuous_through=035 |
| `legacy_build001_changelog` | WARN | 0.000 | Build 001 has README history but no standalone CHANGELOG_BUILD_001.md; retained as legacy documentation gap. |
| `errata_ledger_source` | PASS | 0.000 | errata=['024', '025', '029', '033'] |
| `package_hygiene` | PASS | 0.000 | junk_entries=0 |
| `status_contract_count_declared` | PASS | 0.000 | declared=80; artifact_contract_files=35 |
| `pilot_external_media_boundary` | PASS | 0.000 | state=ASSET_RECON pending=['LISA_X_DIRECT_VERIFIED', 'TGA_VIDEO'] |
| `schema_validator` | PASS | 2.233 | PASS: 80 schemas/contracts structurally valid; all local $refs resolved; valid fixtures passed. |
| `semantic_smoke` | PASS | 0.766 | PASS: semantic smoke checks detected expected cross-field failures. |
| `gate_smoke` | PASS | 1.972 | PASS — Gate Engine evaluated exact evidence, authorized adjacent transition, and recorded immutable gate snapshot. |
| `repo_layout_audit` | PASS | 0.864 | {   "ok": true,   "checks": [     {       "check": "dir:schema",       "ok": true     },     {       "check": "dir:artifacts/contracts",       "ok": true     },     {       "check": "dir:config",       "ok": true     },     {       "check": "dir:fixtures",       "ok": true     },     {       "check": "dir:gmk_state",       "ok": true     },     {       "check": "dir:gmk_semantics",       "ok": true     },     {       "check": "dir:gmk_dependency",       "ok": true     },     {       "check": "dir:gmk_gate",       "ok": true     },     {       "check": "dir:gmk_runtime",       "ok": true     },     {       "check": "dir:gmk_operations",       "ok": true     },     {       "check": "dir:gmk_in |
| `compileall` | PASS | 0.905 |  |
| `pytest_build035_audit` | PASS | 2.069 | ...                                                                      [100%] 3 passed in 0.14s |

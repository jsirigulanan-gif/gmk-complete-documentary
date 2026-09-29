# GMK Repository Audit

- Profile: `QUICK`
- Overall: **PASS_WITH_WARNINGS**
- PASS: 17
- FAIL: 0
- TIMEOUT: 0
- WARN: 1
- Report SHA-256: `bb428b41e9f510bd320b2b029c9e2bb160473861f34664e44e9f7ee8c54e150a`

| Check | Status | Seconds | Detail |
|---|---|---:|---|
| `build_status` | PASS | 0.000 | build=037 schema=FROZEN_WITH_ERRATA_024_025_029_033 |
| `schema_status_consistency` | PASS | 0.000 | FROZEN_WITH_ERRATA_024_025_029_033 |
| `pipeline_complete_marker` | PASS | 0.000 | NONE_CORE_PIPELINE_COMPLETE |
| `readme_current_build` | PASS | 0.000 | Current build:** Build 037 |
| `changelog_continuity_002_current` | PASS | 0.000 | continuous_through=037 |
| `legacy_build001_changelog` | WARN | 0.000 | Build 001 has README history but no standalone CHANGELOG_BUILD_001.md; retained as legacy documentation gap. |
| `errata_ledger_source` | PASS | 0.000 | errata=['024', '025', '029', '033'] |
| `package_hygiene` | PASS | 0.000 | junk_entries=0 |
| `status_contract_count_declared` | PASS | 0.000 | declared=80; artifact_contract_files=35 |
| `pilot_external_media_boundary` | PASS | 0.000 | state=ASSET_RECON pending=['LISA_X_DIRECT_VERIFIED', 'TGA_VIDEO'] |
| `pilot_execution_pack` | PASS | 0.000 | missing=[]; expected=['LISA_X_DIRECT_VERIFIED', 'TGA_VIDEO'] |
| `pilot_media_intake_pack` | PASS | 0.000 | keys=['LISA_X_DIRECT_VERIFIED', 'TGA_VIDEO'] source_locks_match=True slot_markers=True |
| `schema_validator` | PASS | 2.176 | PASS: 80 schemas/contracts structurally valid; all local $refs resolved; valid fixtures passed. |
| `semantic_smoke` | PASS | 0.755 | PASS: semantic smoke checks detected expected cross-field failures. |
| `gate_smoke` | PASS | 1.907 | PASS — Gate Engine evaluated exact evidence, authorized adjacent transition, and recorded immutable gate snapshot. |
| `repo_layout_audit` | PASS | 0.781 | {   "ok": true,   "checks": [     {       "check": "dir:schema",       "ok": true     },     {       "check": "dir:artifacts/contracts",       "ok": true     },     {       "check": "dir:config",       "ok": true     },     {       "check": "dir:fixtures",       "ok": true     },     {       "check": "dir:gmk_state",       "ok": true     },     {       "check": "dir:gmk_semantics",       "ok": true     },     {       "check": "dir:gmk_dependency",       "ok": true     },     {       "check": "dir:gmk_gate",       "ok": true     },     {       "check": "dir:gmk_runtime",       "ok": true     },     {       "check": "dir:gmk_operations",       "ok": true     },     {       "check": "dir:gmk_in |
| `compileall` | PASS | 0.954 |  |
| `pytest_build035_audit` | PASS | 2.017 | ...                                                                      [100%] 3 passed in 0.15s |

# GMK Repository Audit

- Profile: `QUICK`
- Overall: **PASS_WITH_WARNINGS**
- PASS: 22
- FAIL: 0
- TIMEOUT: 0
- WARN: 1
- Report SHA-256: `8caeb8c26d581dd56524e6d0d14aa13e36b6e75fb17e749e492f50208250849d`

| Check | Status | Seconds | Detail |
|---|---|---:|---|
| `build_status` | PASS | 0.000 | build=040 schema=FROZEN_WITH_ERRATA_024_025_029_033 |
| `schema_status_consistency` | PASS | 0.000 | FROZEN_WITH_ERRATA_024_025_029_033 |
| `pipeline_complete_marker` | PASS | 0.000 | NONE_CORE_PIPELINE_COMPLETE |
| `readme_current_build` | PASS | 0.000 | Current build:** Build 040 |
| `changelog_continuity_002_current` | PASS | 0.000 | continuous_through=040 |
| `legacy_build001_changelog` | WARN | 0.000 | Build 001 has README history but no standalone CHANGELOG_BUILD_001.md; retained as legacy documentation gap. |
| `errata_ledger_source` | PASS | 0.000 | errata=['024', '025', '029', '033'] |
| `package_hygiene` | PASS | 0.000 | junk_entries=0 |
| `status_contract_count_declared` | PASS | 0.000 | declared=80; artifact_contract_files=35 |
| `pilot_external_media_boundary` | PASS | 0.000 | state=ASSET_RECON pending=['LISA_X_DIRECT_VERIFIED', 'TGA_VIDEO'] |
| `pilot_execution_pack` | PASS | 0.000 | missing=[]; expected=['LISA_X_DIRECT_VERIFIED', 'TGA_VIDEO'] |
| `pilot_media_intake_pack` | PASS | 0.000 | keys=['LISA_X_DIRECT_VERIFIED', 'TGA_VIDEO'] source_locks_match=True slot_markers=True |
| `pilot_media_processor` | PASS | 0.000 | one-command non-mutating-by-default processor documented and packaged |
| `pilot_readiness_snapshot` | PASS | 0.000 | state=ASSET_RECON manifest=104 readiness=BLOCKED_MEDIA keys=['LISA_X_DIRECT_VERIFIED', 'TGA_VIDEO'] |
| `pilot_readiness_runtime` | PASS | 0.000 | read-only readiness dashboard documented and packaged |
| `operator_release_surface` | PASS | 0.000 | missing=[]; entrypoint=True |
| `schema_validator` | PASS | 1.763 | PASS: 80 schemas/contracts structurally valid; all local $refs resolved; valid fixtures passed. |
| `semantic_smoke` | PASS | 0.629 | PASS: semantic smoke checks detected expected cross-field failures. |
| `gate_smoke` | PASS | 1.632 | PASS — Gate Engine evaluated exact evidence, authorized adjacent transition, and recorded immutable gate snapshot. |
| `repo_layout_audit` | PASS | 0.626 | {   "ok": true,   "checks": [     {       "check": "dir:schema",       "ok": true     },     {       "check": "dir:artifacts/contracts",       "ok": true     },     {       "check": "dir:config",       "ok": true     },     {       "check": "dir:fixtures",       "ok": true     },     {       "check": "dir:gmk_state",       "ok": true     },     {       "check": "dir:gmk_semantics",       "ok": true     },     {       "check": "dir:gmk_dependency",       "ok": true     },     {       "check": "dir:gmk_gate",       "ok": true     },     {       "check": "dir:gmk_runtime",       "ok": true     },     {       "check": "dir:gmk_operations",       "ok": true     },     {       "check": "dir:gmk_in |
| `compileall` | PASS | 0.626 |  |
| `pytest_build035_audit` | PASS | 1.600 | ...                                                                      [100%] 3 passed in 0.07s |
| `pytest_build040_operator` | PASS | 4.466 | ....                                                                     [100%] 4 passed in 2.26s |

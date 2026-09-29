# GMK Repository Audit

- Profile: `QUICK`
- Overall: **PASS_WITH_WARNINGS**
- PASS: 20
- FAIL: 0
- TIMEOUT: 0
- WARN: 1
- Report SHA-256: `dc063d98c4c230ac32a34b051904fe3cee9a96a764d64d2005f73cb0715cf9d8`

| Check | Status | Seconds | Detail |
|---|---|---:|---|
| `build_status` | PASS | 0.000 | build=039 schema=FROZEN_WITH_ERRATA_024_025_029_033 |
| `schema_status_consistency` | PASS | 0.000 | FROZEN_WITH_ERRATA_024_025_029_033 |
| `pipeline_complete_marker` | PASS | 0.000 | NONE_CORE_PIPELINE_COMPLETE |
| `readme_current_build` | PASS | 0.000 | Current build:** Build 039 |
| `changelog_continuity_002_current` | PASS | 0.000 | continuous_through=039 |
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
| `schema_validator` | PASS | 2.555 | PASS: 80 schemas/contracts structurally valid; all local $refs resolved; valid fixtures passed. |
| `semantic_smoke` | PASS | 0.877 | PASS: semantic smoke checks detected expected cross-field failures. |
| `gate_smoke` | PASS | 2.205 | PASS — Gate Engine evaluated exact evidence, authorized adjacent transition, and recorded immutable gate snapshot. |
| `repo_layout_audit` | PASS | 0.960 | {   "ok": true,   "checks": [     {       "check": "dir:schema",       "ok": true     },     {       "check": "dir:artifacts/contracts",       "ok": true     },     {       "check": "dir:config",       "ok": true     },     {       "check": "dir:fixtures",       "ok": true     },     {       "check": "dir:gmk_state",       "ok": true     },     {       "check": "dir:gmk_semantics",       "ok": true     },     {       "check": "dir:gmk_dependency",       "ok": true     },     {       "check": "dir:gmk_gate",       "ok": true     },     {       "check": "dir:gmk_runtime",       "ok": true     },     {       "check": "dir:gmk_operations",       "ok": true     },     {       "check": "dir:gmk_in |
| `compileall` | PASS | 0.994 |  |
| `pytest_build035_audit` | PASS | 2.189 | ...                                                                      [100%] 3 passed in 0.12s |

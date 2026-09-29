# GMK Build 038 Quick Audit

- Overall: **PASS_WITH_WARNINGS**
- PASS: 18
- FAIL: 0
- TIMEOUT: 0
- WARN: 1
- Report SHA-256: `236abbb960991b3ad69449b817028dae91112add1e364efdb73a604e01660a83`

| Check | Status | Detail |
|---|---|---|
| `build_status` | PASS | build=038 schema=FROZEN_WITH_ERRATA_024_025_029_033 |
| `schema_status_consistency` | PASS | FROZEN_WITH_ERRATA_024_025_029_033 |
| `pipeline_complete_marker` | PASS | NONE_CORE_PIPELINE_COMPLETE |
| `readme_current_build` | PASS | Current build:** Build 038 |
| `changelog_continuity_002_current` | PASS | continuous_through=038 |
| `legacy_build001_changelog` | WARN | Build 001 has README history but no standalone CHANGELOG_BUILD_001.md; retained as legacy documentation gap. |
| `errata_ledger_source` | PASS | errata=['024', '025', '029', '033'] |
| `package_hygiene` | PASS | junk_entries=0 |
| `status_contract_count_declared` | PASS | declared=80; artifact_contract_files=35 |
| `pilot_external_media_boundary` | PASS | state=ASSET_RECON pending=['LISA_X_DIRECT_VERIFIED', 'TGA_VIDEO'] |
| `pilot_execution_pack` | PASS | missing=[]; expected=['LISA_X_DIRECT_VERIFIED', 'TGA_VIDEO'] |
| `pilot_media_intake_pack` | PASS | keys=['LISA_X_DIRECT_VERIFIED', 'TGA_VIDEO'] source_locks_match=True slot_markers=True |
| `pilot_media_processor` | PASS | one-command non-mutating-by-default processor documented and packaged |
| `schema_validator` | PASS | PASS: 80 schemas/contracts structurally valid; all local $refs resolved; valid fixtures passed. |
| `semantic_smoke` | PASS | PASS: semantic smoke checks detected expected cross-field failures. |
| `gate_smoke` | PASS | PASS — Gate Engine evaluated exact evidence, authorized adjacent transition, and recorded immutable gate snapshot. |
| `repo_layout_audit` | PASS | {   "ok": true,   "checks": [     {       "check": "dir:schema",       "ok": true     },     {       "check": "dir:artifacts/contracts",       "ok": true     },     {       "check": "dir:config",       "ok": true     },     {       "check": "dir:fixtures",       "ok": true     },     {       "check": "dir:gmk_state",       "ok": true     },     {       "check": "dir:gmk_semantics",       "ok": true     },     {       "check": "dir:gmk_dependency",       "ok": true     },     {       "check": "di |
| `compileall` | PASS |  |
| `pytest_build035_audit` | PASS | ...                                                                      [100%] 3 passed in 0.16s |

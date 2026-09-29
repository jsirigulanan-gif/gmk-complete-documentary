# GMK Schema v1 — Build 035 Changelog

## Focus
Hardening, repository audit, migration ledger, and operator handoff after core pipeline completion.

## Added
- `gmk_audit.AuditRuntime`
- CLI command `gmk audit`
- `STATIC`, `QUICK`, and `FULL` audit profiles
- explicit `PASS / FAIL / TIMEOUT / WARN` audit semantics
- partitioned regression declarations for heavy Build 016–034 tests
- deterministic JSON/Markdown audit reports with report SHA-256
- `ERRATA_MIGRATION_LEDGER.md`
- `OPERATOR_HANDOFF.md`
- `HARDENING_AUDIT_REPORT.md`
- Build 035 audit tests

## Preserved
- no Core Object added
- no Project State added
- no Gate ID added
- no schema/artifact contract added or changed
- schema remains `FROZEN_WITH_ERRATA_024_025_029_033`
- real P.T. pilot remains fail-closed at `ASSET_RECON`

## Validation
- Quick Audit: 14 PASS / 0 FAIL / 0 TIMEOUT / 1 documented WARN
- Existing partitioned regression observed during hardening: 123 PASS
- Build 035 tests: 3 PASS

# GMK Schema v1 — Changelog Build 012

## Added
- `gmk_research.audit.ResearchAuditRuntime`
- CLI `research-audit`
- P.T. external verification batch (`pilot/PT_RESEARCH_AUDIT_INPUT.json`)
- durable audit outputs/status/next-action JSON
- `RESEARCH_AUDIT_REPORT.md`
- Build 012 research-audit regression suite and smoke test

## P.T. Research changes
- Audited 13 intake Claims against 22 external Source records / 22 Evidence records.
- Added `CLM_000014` for the May 2015 re-download block.
- Downgraded `CLM_000004` from pack-declared fact to `COMMUNITY_THEORY`.
- Narrowed `CLM_000006` currency wording and independently supported price + eBay-removal aspects.
- Re-scoped `CLM_000007` to attributed reported assertion.
- Re-scoped `CLM_000008` to attributed technical finding and rejected unsupported exact `0.5 m` precision.
- Kept `CLM_000011`–`CLM_000013` prohibited due insufficient support.
- Added explicit re-download-date discrepancy and Lisa precision Research Gaps.
- Resolved the CRITICAL intake audit guard and transitioned to `RESEARCH_AUDITED`.

## Runtime fixes (contract-preserving)
- LIVE derived/operational record changes persist content-addressed without mutating immutable decision records.
- Cold-start dependency recompute is idempotent and preserves registry hashes when effective state is unchanged.
- `SUPERSEDES` lineage is excluded from stale propagation into the new version.
- historical `DEPENDENCY_IMPACT_REPORT` artifacts are treated as audit snapshots, not live stale dependents.
- unresolved scoped Research Gaps continue blocking gates even when stale.
- Research Audit batch IDs are bound to exact batch SHA-256; changed content with a reused ID fails closed.

## Architecture
No frozen Schema v1 contract change.

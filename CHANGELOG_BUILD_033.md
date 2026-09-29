# GMK Schema v1 — Build 033 Changelog

## Added
- `DELIVERY_REVIEW_PACKAGE` artifact contract.
- `gmk_release.stage.DeliveryStageRuntime` with separate prepare/decide phases.
- CLI commands `gmk delivery-prepare` and `gmk delivery-decide`.
- Exact Delivery candidate hashing across Project Lock, Master Output, Full Film QA, Delivery Profile and metadata.
- Human delivery checklist and `RELEASE` approval bound to the exact Delivery Package + review context.
- Build 033 integration tests and Delivery Stage smoke test.
- `DELIVERY_STAGE_REPORT.md`.

## Erratum 033
`FULL_FILM_QA_PASSED → DELIVERY_READY` is a Human-Approval-required transition, but the generic `REVIEW_PACKAGE` contract is Scene-specific. Build 033 adds a delivery-specific review context rather than weakening the old contract. `RELEASE` approvals may use `DELIVERY_REVIEW_PACKAGE`; historical `REVIEW_PACKAGE` contexts remain valid.

No Core Object, Project State, Gate ID, or transition is added.

## State boundary
Build 033 prepares delivery evidence but does not publish. Human APPROVED may advance only:

`FULL_FILM_QA_PASSED → DELIVERY_READY`

External PUBLISH + immutable RELEASE + FINAL_PROJECT completion remain Build 034 work.

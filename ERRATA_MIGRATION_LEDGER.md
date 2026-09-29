# GMK Schema v1 — Errata & Migration Ledger

Schema status: `FROZEN_WITH_ERRATA_024_025_029_033`

This ledger records the only post-freeze contract additions accepted while completing the runtime. None added a Core Object, Project State, or Gate ID.

| Erratum | Added contract | Why it was required | Compatibility rule |
|---|---|---|---|
| 024 | `VOICE_REVIEW_PACKAGE` | Voice approval occurred before Scene Plan, while the generic `REVIEW_PACKAGE` required Scene Plan/Preview and created a deadlock. | Existing `REVIEW_PACKAGE` remains valid; only Voice approval may use the voice-specific context. |
| 025 | `DESIGN_DNA_REVIEW_PACKAGE` | Design approval also occurs before Scene Plan and had the same review-context deadlock. | Existing review contexts remain valid; Design DNA approval may use the design-specific context. |
| 029 | `PRODUCTION_LOCK_REVIEW_PACKAGE` | Project Production Lock approval needs exact project-level Shot/Layer/Cue closure, not a single Scene review package. | Scene Preview approvals remain unchanged; Production Lock uses the project-specific package. |
| 033 | `DELIVERY_REVIEW_PACKAGE` | Human Release approval needs the exact Delivery candidate/manifests/checkpoint before publication. | Existing Scene/Voice/Design/Production review contexts remain unchanged; Release approval may use the delivery-specific package. |

## Migration guidance

1. Workspaces created before an erratum remain readable because no existing contract was loosened or removed.
2. Do not synthesize missing review packages for historical approvals. New approval actions should use the stage-specific package required by the current runtime.
3. Historical immutable records remain authoritative for their original version. Migration must not rewrite prior Approval, Release, Checkpoint, or QA records.
4. If a workspace resumes at a pre-approval state, run the current stage `*-review-package`/prepare command and collect a new explicit human decision.
5. The P.T. pilot is intentionally not migrated past `ASSET_RECON`; two source-locked external videos are still pending.

## Legacy documentation note

Build 001 is recorded in README/build history but has no standalone `CHANGELOG_BUILD_001.md`. Build 035 treats this as a documented legacy gap rather than fabricating a retrospective changelog.

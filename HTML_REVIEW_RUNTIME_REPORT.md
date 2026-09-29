# GMK Build 028 — HTML Review Runtime Report

## Scope
Build 028 implements the frozen `SHOT_PLAN_READY → HTML_REVIEW → HTML_APPROVED` review path without adding or changing any schema contract.

## Runtime
`gmk_review.HTMLReviewRuntime` now:

- generates one deterministic HTML review file per active Scene under `review/html/`;
- creates one exact `SCENE_PREVIEW` per active Scene;
- creates one standard `REVIEW_PACKAGE` per Scene Preview;
- pins the exact current `SCENE_PLAN` and ordered Shot refs;
- records the generated HTML SHA-256 and workspace-relative path;
- enters `HTML_REVIEW` through the existing automatic predicate-only transition;
- accepts explicit HUMAN `APPROVED` / `REJECTED` decisions for current Scene Previews;
- enters `HTML_APPROVED` only when the existing `HTML_REVIEW` Gate has exact approval coverage for every current Scene Preview;
- replays prepare and repeated identical decisions idempotently.

## Human boundary
Build 028 does not auto-approve previews. A rejected Scene Preview leaves the project in `HTML_REVIEW`. The transition to `HTML_APPROVED` is made only by the State Engine with `actor_type=HUMAN` and `human_confirmed=true` after the frozen Gate evaluates PASS/WARN.

## Validation

```text
Schema / artifact contracts     78 PASS / unchanged
Semantic validation             PASS
Semantic smoke                  PASS
Build 028 tests                 4 PASS
Build 024–028 + Gate/Semantic   53 PASS
Python compileall               PASS
CLI html-review-prepare         REGISTERED
CLI html-review-decide          REGISTERED
```

## P.T. pilot boundary
The real P.T. pilot remains at `ASSET_RECON` because the two source-locked external videos are still pending. Build 028 proves the downstream review path only in isolated test workspaces; it does not write future-state artifacts into the real pilot.

## Next
The next frozen stage is `HTML_APPROVED → PRODUCTION_RENDER` through the `PRODUCTION_LOCK` Gate. The next implementation should compile exact Production Lock manifests from approved Scene Previews, Scene Plans, Shots, Layers, Cues, Design DNA, and Voice Lock, then require the existing HUMAN production-lock approval before final render begins.

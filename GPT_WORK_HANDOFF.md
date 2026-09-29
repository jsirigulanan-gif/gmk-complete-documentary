# Continuation Handoff — GMK Complete Documentary Maker

## Current continuation (Build 044)
The user chose to continue in this Codex session. Build 043 is preserved in Git tag `build-043`; current code is Build 044. Read `CHANGELOG_BUILD_044.md` and `BUILD_044_VALIDATION.md` for changes and current verification. Historical reports below describe the imported baseline.

Next: connect the existing automatic footage production runtime and optional explicitly configured vision provider to a supported CLI/operator command. Currently the CLI/operator expose footage research, while `AutomaticFootageProductionRuntime` is a Python API. Add integration tests; preserve source evidence, credits, unresolved-beat failures, and existing human review gates. Live source acquisition and Ollama inference have not been verified by this import.

## Repository target
`jsirigulanan-gif/gmk-complete-documentary`

## Imported baseline (tag `build-043`)
- Package/build: **Build 043**
- Schema: `FROZEN_WITH_ERRATA_024_025_029_033`
- Frozen Schema v1 contract count: **80**
- Core pipeline remains runtime-complete through `PROJECT_COMPLETED`.
- Build 043 adds the **Visual Semantic Footage Matcher** and keeps Build 042 source/provenance behavior.

## Product intent to preserve
GMK means **Complete Documentary Maker**: the system is expected to research, acquire/select source material, plan/edit, render/export, QA, and produce a completed documentary workflow — not merely generate a plan.

Footage acquisition priority must remain:
1. YouTube video first
2. Other web/archive video
3. Real stills/documents
4. AI-generated visuals last

Rights are **non-blocking workflow metadata**, not a hard acquisition gate. Preserve source URL, creator/title, timestamps, provenance and credits, and use statuses such as `PENDING_PERMISSION` where permission has not yet been verified. Do not bypass DRM, login/authentication, cookies/credentials, paywalls or access controls.

## Build 043 implementation
See `CHANGELOG_BUILD_043.md`. Key additions:
- `gmk_footage.visual_matcher` runtime
- pixel-grounded frame description provider interface
- local Ollama vision provider via explicit `GMK_VISION_MODEL`
- frame-to-Narration-Beat semantic scoring
- visual timestamp nomination and evidence manifests
- fallback order: transcript/caption timestamps -> visual-semantic evidence -> unresolved
- production manifests now record `selection_mode` and visual-match evidence

## Important compatibility note
`OPERATOR_HANDOFF.md` and `BUILD_REPORT.md` contain older Build 040/041 baseline labels. Treat them as historical/operator material, not the current build number. Build 043 is the authoritative imported baseline; the current continuation is recorded above. Do not delete those files unless intentionally replacing historical documentation.

## Current P.T. pilot boundary
The packaged P.T. workspace has historically been at `ASSET_RECON` and required two source-locked external videos:
- `LISA_X_DIRECT_VERIFIED`
- `TGA_VIDEO`

Do not substitute screenshots, metadata pages, fabricated bytes or unrelated reuploads for source-locked real media. Human approval boundaries must remain explicit.

## First verification commands
```bash
python -m gmk_cli audit --profile QUICK --json
python -m gmk_cli status --workspace pilot/PT_WORKSPACE --json
python -m gmk_cli doctor --workspace pilot/PT_WORKSPACE --json
python -m compileall -q .
```

Then run the Build 043 visual matcher tests and the compatible Build 042 footage suite in practical partitions if aggregate wall-clock limits still occur.

## Continuation objective for GPT Work
Continue from Build 043 carefully and incrementally. First audit the repository and reconcile stale handoff/report labels. Then identify the next smallest production-critical gap toward a true end-to-end Complete Documentary Maker that can automatically locate suitable footage, preserve provenance/credits, assemble/edit against narration/scene/shot plans, render/export, and fail closed when evidence is insufficient.

Do not rewrite the architecture wholesale. Preserve frozen Schema v1 contracts unless there is an explicit, documented migration. Add tests for every behavior change. Keep human approval gates where the current system requires them.

## Git hygiene
- Exclude `__pycache__/`, `.pytest_cache/`, `*.pyc`, `*.pyo`.
- Make small, descriptive commits.
- Update changelog/report for the new build number when work advances beyond Build 043.

# Continuation Handoff — GMK Complete Documentary Maker

## Current continuation (Build 048)

General document intake now uses the existing research runtime through `gmk_projects/research.py`. New imports automatically create canonical source/document evidence, UNREVIEWED claim review units and audit-blocking research gaps. Source links are unfetched leads in the intake log, not independently verified SOURCE objects. The local read-only review page and GUI actions expose exact scene/line locations and outstanding questions. Existing projects can run `python -m gmk_projects research-intake /path/to/project`; retries do not duplicate claims. A real source produced 13 review units and 7 source leads locally.

The next work is external evidence collection and editorial claim splitting/review, then narrative/script/beat/visual adapters. Current paragraphs can include multiple assertions or narrative devices; do not call them atomically extracted or verified facts. The full lifecycle remains incomplete; existing Drive quota and private-text TTS consent blockers remain unchanged.

## Previous continuation (Build 047)

The user's complete lifecycle is authoritative in `PRODUCT_REQUIREMENTS.md`; use `IMPLEMENTATION_ROADMAP.md` for the integration sequence. Do not equate a component runtime or fixture release with a completed documentary.

General Drive projects now have a `production/` StateEngine workspace. Its `CURRENT_MANIFEST.json` governs production state; `project.json` governs storage/catalog metadata. Original source imports are registered as RESEARCH_PACK, with Research Intake as the current real stage. `ProductionProject.checkpoint()` archives the persistent core records for Drive sync. This is the first integration step; parsed scripts/voice, claims, media selection, timeline, render and delivery still need canonical object adapters.

Build 046 added real Google Docs research intake, project asset storage, and optional free Edge TTS narration. A generic Thai sample was generated; private project narration still needs user consent for Edge TTS. Actual Drive upload hit the pre-existing shared rclone OAuth client's quota (403); local files remain available. Do not silently claim these blockers are resolved or move private research into Git.

Next: general research/evidence/claim intake and a project-specific beat/visual requirement pipeline, then footage/timeline/voice/render integration as described in the roadmap. Keep one production authority and require real output verification for final completion.

## Historical continuation (Build 045)
The Operator now has an overview and nests Lisa/TGA under the P.T. pilot. See `CHANGELOG_BUILD_045.md`. The next product gap is still a general-project GUI/workflow and a supported automatic production entry point.

## Previous continuation (Build 044)
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

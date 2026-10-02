# Continuation Handoff — GMK Complete Documentary Maker

## Current continuation (Build 055)

Continue GMK at `/home/keng/gmk-complete-documentary`, not Veocut/Sunshine. `gmk_projects/final_production.py` stages exact reviewed editor text in scene order into canonical final-script/TTS artifacts; refreshes promoted Beat refs throughout current story/media/coverage; carries forward the unchanged explicit library selection; and assembles actual mono 48 kHz PCM master bytes with per-block frame/sample timing. Scene audio is frozen and checked before conversion. A complete derived master is cached atomically, then the core manifest is published once after rechecking exact inputs. Failed staging may retain an unreferenced derived audio file, never a current approval or partial final master.

`ScriptRuntime` now orders by Act/Scene/Beat order rather than generated scene IDs. Existing frozen gates reach SCRIPT_READY/TTS_READY. No provider is called, no pronunciation terms invented, no private research approved, and per-scene listening never approves the whole master. An explicit exact-hash named human decision is required for VOICE_LOCKED. The GUI opens verified local audio, requires a listening checkbox and reviewer name, disables repeat decisions, and offers explicit rejection/reopen. CLI: final-inspect/final-prepare/final-voice-decide/final-reopen. Status exposes the current binding/master hash; guided readiness routes to FINAL_PRODUCTION before draft render. It remains a derived view, not another completion authority.

Owned early final stages can reopen for research/story/media changes. Only obsolete owned voice/coverage records are archived, with stable identities, historical decisions and all original files retained. Foreign data and later locks remain protected. Rejection requires reopening/new preparation before another decision. Current canonical integration reaches VOICE_LOCKED only; design → scene/shot/timeline → production lock → canonical render/QA/delivery/release remains next work. Local draft render/export does not establish final release. Real short/long film acceptance and live Drive delivery remain outstanding. See BUILD_055_VALIDATION.md for final verified results and failed/interrupted-run accounting.

Next adapter details: reuse `gmk_design.DesignRuntime` contracts, but stage changes through the project lock and one publication, rather than calling its persisted fixture flow directly. Derive an explicit design preview from actual editor title/subtitle/music settings, keep named human design approval, and bind it to exact voice/narrative/input refs. Its generic `prepare` replays any existing DESIGN_DNA without comparing a new plan, so the product wrapper must validate currentness/versioning and reject foreign state. Extend final-binding recognition beyond VOICE_LOCKED for read-only inspection once downstream stages exist; do not simply allow upstream mutation past design/production locks. Scene/shot planning must consume measured master timings and actual reviewed cuts, not arbitrary fixture plans. Preserve separate draft export until canonical final-film QA/release and verified Drive delivery are genuinely connected.

Real project remains RESEARCH_INTAKE with 13 UNREVIEWED claims; keep private project/research/media outside Git. The most recent live read-only Drive check was Build 054 on 2026-10-02, shared-client quota403, with no upload. Do not claim that client/account was fixed by this build. Private-text provider consent remains required by the app's existing flow.

## Previous continuation (Build 054)

`gmk_projects/coverage.py` measures current scratch voice and renderer-conformed used video ranges, unions overlaps by byte hash, verifies current exact picture/listening decisions and writes canonical ASSET_COVERAGE_REPORT with real MAJOR issues on failure. Explicit final-frame hold is disclosed separately; unused cuts do not count as semantic coverage. Relevant edits, voice bytes/listening decisions and hold/fps changes invalidate the binding. A default assessment never closes selection. Explicit human closure plus a nonempty reason records scoped HUMAN_STOP_WITH_REASON, retains inspected candidate status and unknown rights, and uses existing gates to reach VISUAL_COVERAGE_READY. No exhaustive internet-search, download Operation, origin authenticity or final release claim is created.

The GUI coverage dialog and guided COVERAGE action are usable; CLI inspect/record requires exact preview hashes, closure flag and reason. Frozen coverage/search payloads are validated. Versioned provenance retains rules, inputs, measurements and decisions. Staging publishes once; late failure leaves persisted core state unchanged. Exact replay is a no-op. Owned early media stages can reopen for research/story/claim revisions; only this adapter's obsolete QA is archived, never declared repaired. Foreign QA and later locks remain protected. The local planning compatibility extensions mark registered reviewed copies, with origin_bytes false and UNKNOWN rights; existing VisualCoverageRuntime replay reads them.

Validation and exact counts are in BUILD_054_VALIDATION.md. Live synthetic GUI passed guided media → coverage → explicit library closure → VISUAL_COVERAGE_READY → MP4 → eight-part review → exact ZIP, stopping at Drive/final release with completed false. No private facts were approved and no model/TTS provider was called. A separate read-only Drive account-quota check reconfirmed shared-client 403; it did not upload any file. Next work: final canonical script/voice/design/scene/shot/timeline/render/QA/release adapters and real 2–3 minute / 30 minute acceptance. Real project retains 13 UNREVIEWED claims / RESEARCH_INTAKE. Live read-only Drive quota failure was reconfirmed on 2026-10-02. Continue GMK despite unrelated IDE tabs; keep private project/media outside Git.

## Previous continuation (Build 053)

`gmk_projects/media_bridge.py` connects current reviewed local cuts to canonical Source/Search/Search Result/Asset/Segment records and per-scene PROVENANCE_MANIFEST receipts, stopping at ASSET_RECON. Actual files are referenced through project logical URIs, without duplicating footage into core checkpoints. GUI preview/connection and CLI `media-inspect`/`media-connect` require exact edit/core hashes. Readiness routes to PRODUCTION_MEDIA before render. History restores stable cut identities after removal; missing/corrupt files and old reviews/previews block registration.

Only owned editor media ASSET_RECON can reopen for explicit story/research/claim revisions; foreign/later stages retain their existing protections. Archived dependency heads are historical nodes, so upstream promotion/cold-start recomputation cannot overwrite their archive status. Active dependents still invalidate normally.

UNKNOWN source independence/rights are retained. CONTEXT cuts remain unverified in the frozen contract (MISMATCH mapping, original classification retained). No Search Completion Certificate, Visual Coverage QA, invented download operation, release approval or documentary completion is created. Next adapters must assess coverage and connect canonical script/voice/design/scene/shot/timeline/render/QA/delivery. Real input reviews and live Drive acceptance remain necessary. Validation: 43 core/media/state/dependency PASS, mocked discovery PASS, live synthetic GUI preview → canonical media → MP4 → eight checks → exact ZIP PASS, and QUICK 37 PASS / 0 FAIL / 0 TIMEOUT / 1 documented legacy WARN. See BUILD_053_VALIDATION.md for scopes and overlapping counts. Real project unchanged: 13 UNREVIEWED claims / RESEARCH_INTAKE.

## Previous continuation (Build 052)

The user asked to complete the documentary product and remove unrelated functions. The desktop app now exposes only general documentary projects and setup; P.T./Lisa/TGA UI, pilot path requirements, legacy media execution controls, duplicate raw-file/research/delivery controls and the separate Log tab were removed. Legacy core engines/fixtures remain available outside the product app. No private project/media files were deleted.

`brief.py`, `media_review.py` and `workflow.py` add editable topic/audience/question/length/scope, exact shot/listening review records, and a derived readiness view of all 20 requested lifecycle stages. It routes to the next task, accounts for voice timing before footage, rejects missing local bytes as ready, and never advances another state machine. Film approval optionally records the eight named checks; the GUI requires them. Existing legacy API approvals remain draft decisions and do not satisfy the new full-film readiness check.

CLI: `workflow`, `brief-save`, `shot-review`, `voice-review`, `research-add-claim`; `editorial-approve --review-check <key>` accepts the full named checklist. `gmk-operator --headless-status` lists user projects; `--project <directory>` inspects that project's canonical status. System checks concern actual production tools, not a bundled pilot. Tool installation does not prove live account/quota readiness.

`research_draft.py` closes the empty-claim UI dead end for unstructured research: select an excerpt from a registered original and create one UNREVIEWED assertion. Immutable JSON retains the original asset hash/path and exact excerpt; replay is idempotent, source-independence remains imported UNKNOWN, and script/edit files are preserved. Existing extraction questions remain open; this is partial explicit extraction, not a declaration that all research is extracted or verified. Live GUI interaction passed excerpt selection → claim creation with no provider calls.

Explicit research import can reopen the three early narrative stages within its registration transaction, preserving old research and the edit. It still rejects later locked production revisions. The general editor has a readiness page, scrollable story/footage forms, exact media review dialogs, an eight-part film review dialog and one delivery action. The installed launcher name was updated to GMK Documentary Maker.

Readiness includes `next_scene_id` for media recovery; missing bytes take priority over old approval hashes. Lost footage routes to acquisition, not review. Research forms scroll with save controls outside the viewport.

`Project.add_file` now restores missing registered bytes on exact-original reimport, retaining asset identity and scene/source refs. Previously the deduplication branch returned an absent file reference. Existing changed bytes fail explicitly and are preserved. Exact restored bytes can satisfy their original reviews again; changed narration/media still requires a new review.

Audit `_run` now handles byte/string partial output from `TimeoutExpired` without aborting the report. Build 052 workflow and extraction tests have separate FAST partitions. The initial aggregate run during overlapping targeted tests crashed in that old reporting branch; it is not a pass. Final results are in BUILD_052_VALIDATION.md.

Validation: initial affected regression 65 PASS; final workflow/recovery/storage 36 PASS, including all 15 Build 052 cases (overlapping runs are not added). QUICK after the timeout fix: 35 PASS / 0 FAIL / 0 TIMEOUT / 1 legacy WARN. The final storage changes are covered by the subsequent 36-case run. Live GUI interaction carried a synthetic project through readiness → render → eight-part review → exact local export, stopping at Drive pending; the extra research GUI check passed manual excerpt extraction. Full product completion remains unfinished: canonical asset/coverage/final script/voice/scene/shot/render/QA/release adapters and real provider/Drive/short-film/long-film acceptance remain needed. Do not claim a complete automatic documentary from this build. Continue GMK despite the Sunshine/Veocut files shown in the IDE; they were not edited.

## Previous continuation (Build 051)

`gmk_projects/production_bridge.py` connects explicitly reviewed draft scenes to the existing StateEngine: RESEARCH_AUDITED → ROUGH_NARRATIVE_READY → VISUAL_REQUIREMENTS_READY. `inspect_story` previews blockers and pins edit/manifest hashes. `connect_story` uses those tokens, validates every gate in memory, and persists only after success. It retains stable scene/beat IDs through reorder, exclusion and reinclusion. It does not grant final script, asset, shot, voice, render or release approval.

The editor exposes **เชื่อมบทเข้าระบบผลิต** with editable central question/narrative arc, readiness preview and an explicit connect action. CLI: `production-inspect` and `production-connect-story --edit-sha256 ... --manifest-sha256 ...`. Connected footage searches use canonical beat/claim versions; stale story bindings block automatic search. Saving prepared shots checks the production manifest under the project lock, preserving downloaded bytes when research changed in flight.

Explicit claim re-review can reopen the three early stages, retaining history and invalidating downstream story bindings; later locked stages remain blocked. StateTransaction promotion now reconciles derived dependencies from all exact refs, fixing cold-start registry drift when a dependent still pins a claim older than the previous active version. No schema changes or alternative state authority were introduced.

The actual 13-scene project remains RESEARCH_INTAKE: 29 readiness issues, including unreviewed scene/claim bindings and missing narrative inputs. Inspection left its canonical manifest unchanged. No private facts were approved, provider called, or Drive quota issue resolved. Next integration: selected/acquired assets → canonical coverage/script → scene/shot/timeline and render/QA/release receipts. Keep private projects/media outside Git and continue GMK despite the separate Veocut file shown in the IDE.

## Previous continuation (Build 050)

`gmk_projects/delivery.py` verifies archived render/QA/snapshot records, current editorial review, all ZIP member bytes, and exact Drive receipts. `export_delivery` writes deterministic ZIPs and an immutable registered delivery record referenced by `project.json.active_delivery_asset`. CLI `delivery-verify` is local/read-only; `delivery-sync` explicitly transfers the full project including retained candidates and validates the current draft afterward. Editor buttons expose both actions.

`Project.sync` now validates adapter receipts for both assets and the manifest snapshot before reporting VERIFIED. Failed transfers are retryable without recreating the package. Concurrent edits/research changes invalidate delivery; successful draft storage still returns `documentary_completed: false`. No new live Drive/TTS/model run was made. The final canonical production/release integration and real-film acceptance remain unfinished.

The user's IDE also references `/home/keng/โครงการ/Veocut/ui/static/index.html`, a separate non-Git project. The user explicitly confirmed continuing GMK Build 049 in this conversation; Build 050 continues that repository. Veocut was inspected read-only and was not changed. Do not ask which project to continue again unless the user changes scope.

## Previous continuation (Build 049)

The general workflow now has `gmk_projects/edit.py`, `story.py`, `evidence.py`, `script_review.py`, `footage.py`, `render.py`, and the Operator editor/research windows. See EDITOR_GUIDE_TH.md and CHANGELOG_BUILD_049.md. It preserves the canonical research StateEngine while connecting draft scene editing, opt-in Codex story generation, exact-text voice caching/import, manual or caption-nominated cuts, music, measured timeline conform, actual MP4 rendering, technical QA and explicitly reviewed local ZIP export.

Scene-to-claim review now compares exact narration and reference digests with current canonical claim versions. Preflight and exported `script-review.json` expose missing/stale/prohibited bindings. This derived report does not advance a second state machine.

The actual local project opens with 13 scenes, 13 claim review units and 7 source links. No private text was sent to Edge or a new Codex story invocation: provider selection/consent questions remain pending. Drive `about` was retried on 2026-09-30 and still returned quota 403 for the shared rclone client. Do not claim those live blockers or the real-film acceptance are resolved.

Important remaining integration: canonical final release/Drive completion, full visual-semantic shot validation, provider-backed narrative/audio/media acceptance. `documentary_completed` remains false; a reviewed local ZIP is not the frozen core's final release. Keep user work/private media outside Git. Never mark every imported paragraph as a verified atomic fact.

## Previous continuation (Build 048)

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

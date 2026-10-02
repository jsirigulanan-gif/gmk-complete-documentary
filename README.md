# GMK Complete Documentary Maker — Build 057

> **Current build:** Build 057 — Exact whole-plan human review, production locking and actual locked-master canonical render. **End-to-end automatic documentary production is not ready.** Schema status: `FROZEN_WITH_ERRATA_024_025_029_033`.

The final product requirement is a coherent **Topic / Brief → Research → Evidence / Claims → Narrative → Script → Narration Beats → Visual Requirements → Footage Research → Footage Selection → Footage Acquisition → Scene Planning → Shot Planning → Timeline / Edit Assembly → Voice / TTS → Design / Graphics → Render → Full-film QA → Delivery → Export → Completed Documentary** workflow. See [product requirements and acceptance criteria](PRODUCT_REQUIREMENTS.md) and [integration roadmap](IMPLEMENTATION_ROADMAP.md).

Build 057 connects every selected-cut scene plan to immutable local HTML review pages with actual source-interval video links and the reviewed master audio. Separate named human decisions approve the whole plan and freeze its exact production closure. The production renderer consumes the byte-verified approved PCM master and publishes real RENDER_JOB/RENDER_MANIFEST/RENDER_OUTPUT records only after full-file technical checks and late input revalidation. It remains at PRODUCTION_RENDER: Shot/Scene/Full-film QA and final release are still pending. Explicit reopening retains files/history and requires new approvals. See [changes](CHANGELOG_BUILD_057.md), [validation](BUILD_057_VALIDATION.md) and [editor guide](EDITOR_GUIDE_TH.md). Real film acceptance and verified live Drive delivery remain unfinished.

Build 056 connected actual renderer design settings/PNG review and exact selected-cut scene/shot plans through SHOT_PLAN_READY. Its validation remains historical in [Build 056 validation](BUILD_056_VALIDATION.md).

Build 055 connects the exact reviewed editor narration in scene order to final canonical script records, refreshes existing picture/coverage dependencies, and assembles an actual 48 kHz mono PCM master on the edit's frame/sample clock. The operator opens this master for listening; a separate named human decision is required for VOICE_LOCKED. Rejection and explicit early reopening preserve media/history and retire obsolete owned approvals. This uses already imported/generated scene audio and makes no provider call. See [changes](CHANGELOG_BUILD_055.md), [validation](BUILD_055_VALIDATION.md) and [editor guide](EDITOR_GUIDE_TH.md). Canonical design/scene/shot/render/QA/release and real-film acceptance remain unfinished.

Build 054 assesses the actual used picture ranges against measured current narration and exact visual/listening reviews. Repeated footage does not add unique duration; explicit final-frame holds are disclosed separately. The editor records canonical PASS/FAIL QA and missing coverage. An optional human library-selection stop with a reason advances existing gates to VISUAL_COVERAGE_READY, without certifying exhaustive search or rights. Relevant edits invalidate old results; explicit early revisions retain history and files. See [Build 054 changes](CHANGELOG_BUILD_054.md), [validation](BUILD_054_VALIDATION.md) and [editor guide](EDITOR_GUIDE_TH.md). Canonical final production and release remain unfinished.

Build 053 connects explicitly reviewed local footage to exact canonical Source/Search Result/Asset/Segment records, preserving byte hashes, original URLs and in/out ranges without copying large media into the production checkpoint. The editor previews and connects these records; readiness routes to that action before rendering. Trims require fresh picture review, revisions retain identities, and removed selections retain history and original files. Source independence, usage rights, search completeness and full-film canonical coverage are still pending. See [Build 053 changes](CHANGELOG_BUILD_053.md) and [validation](BUILD_053_VALIDATION.md).

Build 052 removes the P.T./Lisa/TGA demonstration UI and its workspace dependencies from the desktop app. The app opens general projects directly, supports new topic briefs, and shows readiness across all 20 lifecycle stages with a next action. Exact shot/listening reviews expire when relevant draft inputs change, and whole-film review records eight editorial checks before local delivery. See [Build 052 changes](CHANGELOG_BUILD_052.md), [validation](BUILD_052_VALIDATION.md) and [Thai startup guide](README_START_HERE_TH.md). The readiness view is derived from existing records; canonical final-release integration and real-film acceptance remain pending.

General research without script/claim markers can be reviewed by selecting original excerpts and creating UNREVIEWED assertions. The exact source and excerpt are retained, repeated selections do not duplicate claims, and existing scripts stay intact. Guided recovery selects the scene with missing media and requests reacquisition before picture review.

Build 051 connects reviewed editor scenes to canonical Acts, Scenes, Narration Beats and visual requirements through existing production gates. The editor previews missing evidence and narrative inputs before an explicit connection. Footage planning then uses those exact beat/claim versions; repeated evidence revisions remain reloadable. See [Build 051 changes](CHANGELOG_BUILD_051.md) and [validation](BUILD_051_VALIDATION.md). Canonical integration beyond visual requirements and real-film acceptance remain pending.

Build 050 validates every ZIP member against the exact rendered files and current reviewed edit/research. Repeat exports are byte-identical. The new delivery action uploads the project, validates Drive receipts for the package/master/manifest, and checks for changes after transfer. This is verified **draft storage**, not final documentary release. See [Build 050 changes](CHANGELOG_BUILD_050.md).

Build 049 adds a general editing desk for evidence review, opt-in Codex story drafts, narration, scene/cut editing, footage research/acquisition, caption-based shot proposals, measured audio timing, music ducking, titles/subtitles, technical QA and reviewed local delivery packages. See [Thai editor guide](EDITOR_GUIDE_TH.md) and [Build 049 changes](CHANGELOG_BUILD_049.md). Provider-backed real-film acceptance, complete visual-semantic automation, and canonical final Drive release remain incomplete.

Build 048 imports general documentary narration or explicitly labeled claims into canonical research records, preserving source locations and unverified bibliography links. The project panel can open a local research review showing imported paragraphs, source leads and unresolved questions. Paragraphs may require splitting; independent evidence verification and editorial decisions remain pending. See [Build 048 changelog](CHANGELOG_BUILD_048.md).

Build 047 binds each new Drive project to a persistent StateEngine workspace. Research import registers original bytes and enters Research Intake; it does not claim factual audit or downstream completion. Project status comes from the core manifest, and Drive sync includes a production-record checkpoint. Old projects can be connected through the project panel or `python -m gmk_projects connect-production /path/to/project`.

The **โปรเจกต์สารคดี** page imports LEMiNO Script documents, creates projects independently of P.T., generates Thai narration through optional Edge TTS, and uploads registered research/media files to a per-project Google Drive folder. It verifies uploaded sizes and MD5 checksums, keeps local files on failures, and records immutable manifest snapshots. See [Drive project usage and remaining work](DRIVE_PROJECTS.md). The new editor connects local editing/rendering; a real full-lifecycle documentary has not yet passed acceptance.

Build 045 added a purpose and scope overview in the Operator. The two source-locked Lisa/TGA video slots now live under the P.T. pilot. General project creation was added in Build 046; producing a full film with one click remains incomplete. See [Build 045 changelog](CHANGELOG_BUILD_045.md).

Build 044 fixes frame sampling at the end of a video and enables audits in Git checkouts. The imported baseline is preserved as tag `build-043`. See [Build 044 changelog](CHANGELOG_BUILD_044.md).

Build 043 adds pixel-grounded frame descriptions, visual timestamp matching, and an optional Ollama vision provider to the Build 042 footage runtime. Automatic production tries transcript timestamps first, then configured visual matching; insufficient evidence remains unresolved. See [Build 043 changelog](CHANGELOG_BUILD_043.md) and [continuation handoff](GPT_WORK_HANDOFF.md).

Physical runtime implementation of the GMK Schema v1 production pipeline.


## Complete Documentary Maker — Footage Core

Material priority is enforced as:

`YOUTUBE → WEB_VIDEO → STILL_DOCUMENT → AI_GENERATED (last resort)`

Build a non-network search plan:
```bash
python -c "from gmk_cli.cli import main; raise SystemExit(main(['footage-plan','--workspace','pilot/PT_WORKSPACE','--output','pilot/PT_FOOTAGE_RESEARCH/FOOTAGE_QUERY_PLAN.json','--json']))"
```

Run YouTube-first metadata/caption/timestamp research (requires `yt-dlp`):
```bash
python -c "from gmk_cli.cli import main; raise SystemExit(main(['footage-research','--workspace','pilot/PT_WORKSPACE','--output','pilot/PT_FOOTAGE_RESEARCH/FOOTAGE_RESEARCH_REPORT.json','--json']))"
```

Run the full real-material fallback search:
```bash
python -c "from gmk_cli.cli import main; raise SystemExit(main(['footage-material-research','--workspace','pilot/PT_WORKSPACE','--output','pilot/PT_FOOTAGE_RESEARCH/MATERIAL_RESEARCH_REPORT.json','--json']))"
```

The Operator GUI also exposes these under **Documentary Maker**. Build 042 can automatically acquire selected public candidates, cut timestamped segments, assemble an ordered rough-cut MP4, and emit timeline/credits sidecars. Visual-only videos without sufficient transcript evidence remain inspection-required rather than being guessed.

## Current P.T. pilot state
```text
State                         ASSET_RECON
Selected Assets               10
Cataloged Assets               8
Pending source-locked videos   2
Verified Segments              8
Pending keys                   LISA_X_DIRECT_VERIFIED, TGA_VIDEO
```

The P.T. pilot's immediate media-stage blocker is external media; the full documentary product also requires integrations described above. Build 036 generated `pilot/PT_EXECUTION_PACK/` directly from the durable workspace. Build 037 adds `pilot/PT_MEDIA_INTAKE/`, with one source-locked candidate slot per pending video. Build 038 adds `pilot-media-process`, which combines intake build + receipt + authoritative preflight in one command and mutates the workspace only when `--execute` is explicitly supplied. Build 039 adds `pilot-readiness`, a read-only dashboard plus packaged readiness snapshot under `pilot/PT_PILOT_READINESS/`.


## Start the Operator app on Windows

1. Extract the ZIP to a writable folder.
2. Run `INSTALL_GMK.cmd` once.
3. Run `START_GMK.cmd`.
4. If ffprobe is not found, open the System tab and choose `ffprobe.exe`.

See `README_START_HERE_TH.md` for the Thai quick-start.

## P.T. readiness command
```bash
python -m gmk_cli pilot-readiness \
  --workspace pilot/PT_WORKSPACE \
  --intake-dir pilot/PT_MEDIA_INTAKE \
  --output-dir pilot/PT_PILOT_READINESS \
  --json
```

Run this first. It is read-only and returns `BLOCKED_MEDIA`, `BLOCKED_INSPECTION`, `BLOCKED_PREFLIGHT`, `READY_TO_EXECUTE`, or `ALREADY_ADVANCED`.

## P.T. media intake commands
```bash
python -m gmk_cli pilot-media-intake-init \
  --workspace pilot/PT_WORKSPACE \
  --intake-dir pilot/PT_MEDIA_INTAKE \
  --json

# Put one authorized video in each candidate slot and fill the inspection worksheet.
# One-command build + receipt + preflight (default: non-mutating)
python -m gmk_cli pilot-media-process \
  --workspace pilot/PT_WORKSPACE \
  --intake-dir pilot/PT_MEDIA_INTAKE \
  --inspection pilot/PT_MEDIA_INTAKE/PT_MEDIA_INSPECTION_WORKSHEET.json \
  --json

# Only after reviewing the receipt/preflight, explicitly execute acquisition + visual coverage.
python -m gmk_cli pilot-media-process \
  --workspace pilot/PT_WORKSPACE \
  --intake-dir pilot/PT_MEDIA_INTAKE \
  --inspection pilot/PT_MEDIA_INTAKE/PT_MEDIA_INSPECTION_WORKSHEET.json \
  --execute \
  --json
```

The packaged input is intentionally incomplete until real local media is supplied. Never replace the pending videos with screenshots, page text, metadata, unrelated reuploads, or synthetic fixture media.

## Core pipeline
The isolated runtime is implemented and validated through:

`BOOTSTRAPPED → RESEARCH_INTAKE → RESEARCH_AUDITED → ROUGH_NARRATIVE_READY → VISUAL_REQUIREMENTS_READY → ASSET_RECON → ASSET_CATALOG_READY → VISUAL_COVERAGE_READY → SCRIPT_READY → TTS_READY → VOICE_LOCKED → DESIGN_DNA_APPROVED → SCENE_PLAN_READY → SHOT_PLAN_READY → HTML_REVIEW → HTML_APPROVED → PRODUCTION_RENDER → SHOT_QA_PASSED → SCENE_QA_PASSED → FULL_FILM_QA_PASSED → DELIVERY_READY → PROJECT_COMPLETED`

Human approvals remain mandatory at their frozen boundaries.

## Build milestones
- 001–010 — Schema, semantics, state/dependency/gate/runtime, production/render/QA, release/orchestrator, CLI/workspace foundation
- 011–017 — P.T. research through real-byte Asset acquisition boundary
- 018–020 — media handoff/source locks and Visual Coverage
- 021–023 — Script, TTS, Voice preparation
- 024–025 — Voice/Design review-context errata and Human approvals
- 026–028 — Scene Plan, Shot Plan, HTML Review
- 029 — Production Lock review erratum
- 030–032 — Render/Shot QA, Scene QA, Full Film QA
- 033 — Delivery review erratum
- 034 — Release/finalize through `PROJECT_COMPLETED`
- 035 — hardening/audit/migration/operator handoff
- 036 — real P.T. execution pack and non-mutating media preflight
- 037 — source-locked external media intake slots, inspection worksheet, checksum receipt, and handoff-plan compiler
- 038 — one-command media processor and reduced redundant Cold Start during pilot execution
- 039 — read-only P.T. readiness dashboard, packaged blocker snapshot, and guided next action
- 040 — Operator Release Candidate: desktop GUI, Windows launcher/setup, media-slot inspection UX, and shared ffprobe resolution
- 041 — CachyOS/Arch native installer and desktop launcher
- 042 — YouTube-first footage discovery, ranking, timestamp inspection, acquisition, web/still fallbacks, automatic rough-cut assembly and credits
- 043 — Visual semantic frame matching and evidence manifests for transcript-poor footage
- 044 — End-of-file frame sampling fix, Git checkout audit support, and regression coverage
- 045 — Operator overview and P.T. pilot navigation, with truthful scope labels

## Audit
```bash
python -m gmk_cli audit --profile QUICK --json
```

`FULL` runs heavy build partitions independently and reports `TIMEOUT` separately from `FAIL`/`PASS`.

## Repository status
Repository: [jsirigulanan-gif/gmk-complete-documentary](https://github.com/jsirigulanan-gif/gmk-complete-documentary). This repository import does not publish documentary outputs; the final built-in media delivery adapter remains `LOCAL_EXPORT`.

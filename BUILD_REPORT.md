# Gamer Must Know — GMK Schema v1 — Build 041

**Build focus:** Operator Release Candidate / Windows desktop surface  
**Schema:** `FROZEN_WITH_ERRATA_024_025_029_033` — 80 contracts

## Result
The core pipeline remains runtime-complete through `PROJECT_COMPLETED`. Build 040 adds no production stage and no schema contract. It packages the current real P.T. boundary behind an operator-facing desktop application while preserving the same authoritative runtimes and fail-closed rules.

### Real P.T. state
```text
Project State                 ASSET_RECON
Manifest Version              104
Cataloged Assets              8 / 10
Verified Segments             8
Pending Videos                2
Readiness                     BLOCKED_MEDIA
Workspace Mutation            NONE
```

## Added
- Tkinter desktop Operator app (`gmk_operator`).
- Windows install/start launchers.
- Thai start-here guide.
- GUI media slot selection + human inspection editor.
- readiness/preflight/execute controls.
- shared configurable ffprobe resolver.
- operator/release smoke coverage.

## Validation
- Build 040 Operator tests: **4/4 PASS**.
- Build 018 media handoff: **4/4 PASS**.
- Build 019 source lock: **3/3 PASS**.
- Build 023 Voice: **3/3 PASS**.
- Build 030 Render/Shot QA: **4/4 PASS**.
- Operator smoke: **PASS**.
- P.T. packaged readiness: **BLOCKED_MEDIA / non-mutating**.
- Schema: **80 contracts / unchanged**.

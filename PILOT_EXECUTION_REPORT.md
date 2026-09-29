# P.T. Pilot Execution Pack Report — Build 036

## Outcome
Build 036 converts the remaining real P.T. blocker from an operator-memory task into a deterministic execution package. The system now derives the exact two pending source-locked video requirements from the durable workspace, generates an input template/runbook, validates supplied files without mutation, and can execute acquisition plus Visual Coverage once the real files are supplied.

## Current durable state
```text
Project state                 ASSET_RECON
Cataloged Assets              8
Pending selected video Assets 2
Verified Segments             8
Pending source locks          LISA_X_DIRECT_VERIFIED, TGA_VIDEO
Schema contracts              80
Schema status                 FROZEN_WITH_ERRATA_024_025_029_033
```

## Generated operator package
`pilot/PT_EXECUTION_PACK/` contains:
- `PT_EXECUTION_MANIFEST.json` — exact current source locks/Asset refs/Search Result refs and blockers
- `PT_MEDIA_HANDOFF_INPUT.json` — fillable source-locked handoff plan
- `PT_EXECUTION_RUNBOOK.md` — exact operator sequence and hard boundaries

The Lisa requirement intentionally leaves its exact local-video time range blank because the durable source result locks the full original-creator post rather than a numerical clip range. The operator must inspect the actual acquired file and enter the usable range. The TGA candidate remains bounded to the previously inspected `0–135s` source range.

## Commands
```bash
python -m gmk_cli pilot-execution-pack \
  --workspace pilot/PT_WORKSPACE \
  --output-dir pilot/PT_EXECUTION_PACK \
  --json

python -m gmk_cli pilot-media-preflight \
  --workspace pilot/PT_WORKSPACE \
  --input pilot/PT_EXECUTION_PACK/PT_MEDIA_HANDOFF_INPUT.json \
  --json

python -m gmk_cli pilot-media-execute \
  --workspace pilot/PT_WORKSPACE \
  --input pilot/PT_EXECUTION_PACK/PT_MEDIA_HANDOFF_INPUT.json \
  --json
```

`pilot-media-preflight` is deliberately non-mutating. The packaged template currently fails preflight because it contains no real local video paths and Lisa's exact range remains unset.

## Proven execution boundary
Against an isolated copy of the real P.T. workspace, Build 036 proves:

`ASSET_RECON → source-locked media handoff → ASSET_CATALOG_READY → VISUAL_COVERAGE_READY`

using actual MP4 bytes in the test workspace. The test media is synthetic only for runtime validation and is never inserted into the durable P.T. pilot.

## Validation
- Build 036 integration: 6/6 PASS when heavy cases are run independently
- Build 018 Media Handoff regression: 4/4 PASS
- Build 019 Source Lock regression: 3/3 PASS
- Build 020 Visual Coverage regression: 3/3 PASS (heavy tests partitioned)
- Quick Audit: 16 PASS / 0 FAIL / 0 TIMEOUT / 1 WARN
- packaged-template preflight: fail-closed and non-mutating
- execution-pack smoke: PASS
- no schema change

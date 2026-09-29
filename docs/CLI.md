# GMK Runtime CLI — Build 013

The CLI is a thin operator surface over the frozen GMK runtime. It does not bypass the State Engine, Gate Engine, safety controller, Research boundary, or Cold Start integrity checks.

## Core commands

```bash
python -m gmk_cli init --workspace <path> --title "Project title" [--research-pack <file>]
python -m gmk_cli status --workspace <path>
python -m gmk_cli next-action --workspace <path>
python -m gmk_cli doctor [--workspace <path>]
python -m gmk_cli persist --workspace <path>
python -m gmk_cli pilot-preflight --research-pack <path>
python -m gmk_cli pilot-bootstrap --workspace <path> --research-pack <file>
python -m gmk_cli research-intake --workspace <path>
python -m gmk_cli research-audit --workspace <path> --input <audit.json>
python -m gmk_cli rough-narrative --workspace <path> --input <narrative-plan.json>
```

A package entry point is declared in `pyproject.toml` as `gmk = gmk_cli.cli:main`.

`rough-narrative` accepts an explicit plan but treats Research Audit as the truth boundary: every Claim binding must resolve to a current exact Claim version whose production-use policy permits narration. The command creates `ACT`, `SCENE`, `NARRATION_BEAT`, and `NARRATIVE_SPINE` through the authoritative runtime; it never writes identity/version fields directly.

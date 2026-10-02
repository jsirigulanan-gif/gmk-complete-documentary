# GMK Runtime CLI — Build 013

The CLI is a thin operator surface over the frozen GMK runtime. It does not bypass the State Engine, Gate Engine, safety controller, Research boundary, or Cold Start integrity checks.

## General documentary projects (Build 053)

These commands use the same project as the desktop documentary workspace:

```bash
python -m gmk_projects status /path/to/project
python -m gmk_projects workflow /path/to/project
python -m gmk_projects production-inspect /path/to/project
python -m gmk_projects media-inspect /path/to/project
python -m gmk_projects media-connect /path/to/project --edit-sha256 <preview-edit-hash> --manifest-sha256 <preview-core-hash>
python -m gmk_projects edit-preflight /path/to/project
python -m gmk_projects render /path/to/project
python -m gmk_projects delivery-verify /path/to/project
```

`media-connect` registers selected, explicitly reviewed existing files and time ranges. Exact preview hashes prevent connecting changed edits/evidence. Missing or corrupt bytes and expired picture reviews fail before publishing. These records do not grant rights or coverage approval; core registration stops at ASSET_RECON.

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

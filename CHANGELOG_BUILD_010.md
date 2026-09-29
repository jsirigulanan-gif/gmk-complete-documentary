# GMK Schema v1 — Changelog Build 010

## Added
- installable local CLI surface (`gmk_cli`);
- workspace bootstrapper that creates PROJECT / optional RESEARCH_PACK through the State Engine;
- immutable Research Pack input copy + SHA-256 registration;
- workspace doctor and Cold Start status commands;
- `next-action` operator command backed by Gate Engine;
- P.T. pilot input preflight command;
- runtime integration audit tool;
- repository layout audit tool;
- `pyproject.toml` and `.gitignore` for repository readiness;
- CLI/workspace/pilot documentation;
- Build 010 CLI/workspace integration tests.

## Architecture impact
None. No Core Object, authority rule, state, gate, dependency relation, or frozen Schema v1 contract was added or changed.

## Pilot evidence
The supplied P.T. Research Pack passed input integrity preflight and a real bootstrap/Cold Start smoke. This is bootstrap readiness only, not Research Audit approval.

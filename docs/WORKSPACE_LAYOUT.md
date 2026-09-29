# GMK Workspace Layout — Build 010

A runtime workspace is separate from the source/runtime package.

```text
<workspace>/
  CURRENT_MANIFEST.json          # authoritative resume pointer
  WORKSPACE.json                 # non-authoritative launcher metadata
  manifests/
  registries/
  objects/
  artifacts/records/
  configs/
  state/
  inputs/research/               # immutable bootstrap input copies
```

`WORKSPACE.json` is convenience metadata only. The Project Manifest plus pinned Registry snapshots remain the authority for Cold Start.

Committed object/artifact versions are immutable. New decisions create new versions; restore creates new current state without deleting history.

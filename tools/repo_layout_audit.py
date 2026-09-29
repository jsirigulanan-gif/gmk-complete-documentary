#!/usr/bin/env python3
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
required_dirs=['schema','artifacts/contracts','config','fixtures','gmk_state','gmk_semantics','gmk_dependency','gmk_gate','gmk_runtime','gmk_operations','gmk_incident','gmk_recovery','gmk_production','gmk_render','gmk_qa','gmk_release','gmk_orchestrator','gmk_cli','gmk_workspace','gmk_research','gmk_narrative','gmk_footage','gmk_pilot','gmk_operator','operator','tests','tools']
required_files=['pyproject.toml','START_GMK.cmd','INSTALL_GMK.cmd','START_GMK.sh','INSTALL_GMK.sh','QUICK_START_CACHYOS_TH.md','README_START_HERE_TH.md','schema/schema-registry.json','config/gmk_policy_bundle.yaml','README.md','BUILD_STATUS.json']
checks=[]
for rel in required_dirs:checks.append({'check':f'dir:{rel}','ok':(ROOT/rel).is_dir()})
for rel in required_files:checks.append({'check':f'file:{rel}','ok':(ROOT/rel).is_file()})
# GitHub/repo init is intentionally deferred; this audit only reviews local layout.
checks.append({'check':'git_metadata_absent','ok':not (ROOT/'.git').exists()})
# No runtime workspace is allowed in the source tree.
checks.append({'check':'no_current_manifest_in_source_root','ok':not (ROOT/'CURRENT_MANIFEST.json').exists()})
print(json.dumps({'ok':all(x['ok'] for x in checks),'checks':checks},indent=2))
raise SystemExit(0 if all(x['ok'] for x in checks) else 1)

from __future__ import annotations
from pathlib import Path
import json
import os
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from gmk_operator.app import system_check, headless_status
from gmk_runtime.media_tools import resolve_ffprobe


def main() -> int:
    check=system_check()
    assert check['build']=='041'
    assert any(x['check']=='workspace_present' and x['ok'] for x in check['checks'])
    assert any(x['check']=='intake_present' and x['ok'] for x in check['checks'])
    assert resolve_ffprobe()
    status=headless_status()
    assert status['project_state']=='ASSET_RECON'
    assert status['readiness']=='BLOCKED_MEDIA'
    print(json.dumps({'operator_system_check':check,'readiness':status['readiness']},ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())

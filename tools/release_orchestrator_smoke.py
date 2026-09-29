#!/usr/bin/env python3
from pathlib import Path
import subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
cmd=[sys.executable,'-m','pytest','-q','tests/build009/test_release_orchestrator_e2e.py::test_end_to_end_orchestrator_reaches_project_completed']
result=subprocess.run(cmd,cwd=ROOT)
if result.returncode:
    sys.exit(result.returncode)
print('PASS: Release / Delivery Runtime + End-to-End Orchestrator smoke completed through PROJECT_COMPLETED and cold-start recovery.')

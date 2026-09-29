from pathlib import Path
import subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
def test_schema_validation():
    subprocess.run([sys.executable,str(ROOT/'tools/validate_schemas.py')],check=True)
def test_semantic_smoke():
    subprocess.run([sys.executable,str(ROOT/'tools/semantic_smoke.py')],check=True)

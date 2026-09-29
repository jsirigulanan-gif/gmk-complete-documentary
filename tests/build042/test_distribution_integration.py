from pathlib import Path
from gmk_cli.cli import parser
from gmk_operator.app import system_check

ROOT=Path(__file__).resolve().parents[2]

def test_build_042_is_reported_and_yt_dlp_is_system_check():
 c=system_check();assert c['build']=='042'
 by={x['check']:x for x in c['checks']};assert 'yt_dlp' in by

def test_cachyos_installer_installs_yt_dlp():
 text=(ROOT/'INSTALL_GMK.sh').read_text()
 assert 'yt-dlp' in text and 'PACKAGES=' in text

def test_cli_exposes_footage_commands():
 p=parser()
 # argparse exposes choices through the subparser action.
 choices={}
 for a in p._actions:
  if hasattr(a,'choices') and isinstance(a.choices,dict): choices.update(a.choices)
 assert 'footage-plan' in choices and 'footage-research' in choices and 'footage-material-research' in choices

def test_operator_has_documentary_maker_tab_hooks():
 text=(ROOT/'gmk_operator/app.py').read_text()
 for token in ('Documentary Maker','generate_footage_plan','run_footage_research','run_material_research','PT_FOOTAGE_RESEARCH'):
  assert token in text

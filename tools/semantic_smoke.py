#!/usr/bin/env python3
from pathlib import Path
import json, sys
ROOT=Path(__file__).resolve().parents[1]
issues=[]

def load(rel): return json.loads((ROOT/rel).read_text())

def project_runtime(doc):
    r=doc['target']['runtime_minutes']
    if r['min']>r['max']: return 'PROJECT_RUNTIME_RANGE_INVALID'

def time_range(locator):
    if locator.get('type')=='VIDEO_TIME_RANGE' and locator['end_seconds']<=locator['start_seconds']:
        return 'EVIDENCE_LOCATOR_INVALID'

valid_project=load('fixtures/valid/project.json')
invalid_project=load('fixtures/invalid/project_runtime_range.json')
valid_evidence=load('fixtures/valid/evidence.json')
invalid_evidence=load('fixtures/invalid/evidence_time_range.json')

if project_runtime(valid_project): issues.append('valid project failed semantic check')
if project_runtime(invalid_project)!='PROJECT_RUNTIME_RANGE_INVALID': issues.append('invalid project not detected')
if time_range(valid_evidence['locator']): issues.append('valid evidence failed semantic check')
if time_range(invalid_evidence['locator'])!='EVIDENCE_LOCATOR_INVALID': issues.append('invalid evidence not detected')

if issues:
    print('FAIL'); [print('-',x) for x in issues]; sys.exit(1)
print('PASS: semantic smoke checks detected expected cross-field failures.')

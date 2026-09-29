#!/usr/bin/env python3
from pathlib import Path
import json, sys
from urllib.parse import urldefrag
from jsonschema import Draft202012Validator, FormatChecker

ROOT=Path(__file__).resolve().parents[1]
registry=json.loads((ROOT/'schema/schema-registry.json').read_text())['schemas']
loaded={sid:json.loads((ROOT/path).read_text()) for sid,path in registry.items()}
errors=[]

for sid,schema in loaded.items():
    try: Draft202012Validator.check_schema(schema)
    except Exception as e: errors.append(f'SCHEMA_INVALID {sid}: {e}')

def pointer(doc, frag):
    if not frag or frag=='#': return doc
    if frag.startswith('#'): frag=frag[1:]
    if not frag: return doc
    if not frag.startswith('/'): return None
    cur=doc
    for raw in frag.split('/')[1:]:
        key=raw.replace('~1','/').replace('~0','~')
        if isinstance(cur,list):
            try: cur=cur[int(key)]
            except: return None
        elif isinstance(cur,dict) and key in cur: cur=cur[key]
        else: return None
    return cur

def walk(x):
    if isinstance(x,dict):
        for k,v in x.items():
            if k=='$ref' and isinstance(v,str): yield v
            yield from walk(v)
    elif isinstance(x,list):
        for v in x: yield from walk(v)

for sid,schema in loaded.items():
    for ref in walk(schema):
        base,frag=urldefrag(ref)
        target=loaded.get(base) if base else schema
        if target is None:
            errors.append(f'UNRESOLVED_REF {sid} -> {ref}')
        elif frag and pointer(target,'#'+frag) is None:
            errors.append(f'BAD_FRAGMENT {sid} -> {ref}')

# Validate selected fixtures with a registry-aware resolver using referencing
try:
    from referencing import Registry, Resource
    reg=Registry()
    for sid,schema in loaded.items():
        reg=reg.with_resource(sid, Resource.from_contents(schema))
    cases=[
      ('gmk://schema/v1/project','fixtures/valid/project.json',True),
      ('gmk://schema/v1/claim','fixtures/valid/claim.json',True),
      ('gmk://schema/v1/evidence','fixtures/valid/evidence.json',True),
      ('gmk://schema/v1/search-result','fixtures/valid/search_result_human_injection.json',True),
      ('gmk://schema/v1/artifact/narrative-spine','fixtures/valid/narrative_spine.json',True),
    ]
    for sid,rel,expect in cases:
        data=json.loads((ROOT/rel).read_text())
        verr=list(Draft202012Validator(loaded[sid], registry=reg, format_checker=FormatChecker()).iter_errors(data))
        if bool(verr)==expect:
            errors.append(f'FIXTURE_EXPECTATION_FAILED {rel}: {[e.message for e in verr[:3]]}')
except Exception as e:
    errors.append(f'FIXTURE_VALIDATOR_SETUP_FAILED: {e}')

if errors:
    print('FAIL')
    for e in errors: print('-',e)
    sys.exit(1)
print(f'PASS: {len(loaded)} schemas/contracts structurally valid; all local $refs resolved; valid fixtures passed.')

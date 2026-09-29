#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from gmk_semantics import SemanticValidator, StateView


def load_many(paths):
    out=[]
    for p in paths:
        data=json.loads(Path(p).read_text(encoding="utf-8"))
        if isinstance(data,list): out.extend(data)
        else: out.append(data)
    return out


def main():
    ap=argparse.ArgumentParser(description="GMK Schema v1 semantic validator")
    ap.add_argument("--objects", nargs="*", default=[])
    ap.add_argument("--artifacts", nargs="*", default=[])
    ap.add_argument("--json", action="store_true")
    args=ap.parse_args()
    state=StateView.build(load_many(args.objects),load_many(args.artifacts))
    v=SemanticValidator(ROOT)
    issues=v.validate_state(state)
    if args.json:
        print(json.dumps([x.to_dict() for x in issues],ensure_ascii=False,indent=2))
    else:
        if not issues:
            print("PASS: no semantic issues")
        else:
            for x in issues:
                print(f"{x.severity} {x.code} {x.target or '-'} {x.path or '-'} :: {x.message}")
            print(f"FAIL: {len(issues)} semantic issue(s)")
    return 1 if any(x.severity in {"ERROR","CRITICAL"} for x in issues) else 0

if __name__=="__main__": raise SystemExit(main())

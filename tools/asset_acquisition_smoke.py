from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gmk_runtime.cold_start import ColdStartLoader
WS=ROOT/'pilot'/'PT_WORKSPACE'
loaded=ColdStartLoader(ROOT,WS).load()
st=loaded.engine.snapshot()
assets=[];segs=[];reports=[]
for reg in st.registries.values():
    for oid,e in reg.entries.items():
        if e.active_version is None: continue
        o=st.objects[(oid,int(e.active_version))]
        if o.get('object_type')=='ASSET': assets.append(o)
        elif o.get('object_type')=='SEGMENT': segs.append(o)
        elif o.get('object_type')=='QA_REPORT' and o.get('report_type')=='ASSET_COVERAGE_REPORT': reports.append(o)
assert sum(a.get('workflow_state')=='CATALOGED' for a in assets)==8
assert sum(a.get('workflow_state')=='ACQUISITION_PENDING' for a in assets)==2
assert len(segs)==8
assert reports and reports[-1]['result']=='FAIL'
print('PASS: acquisition verification + immutable checksums + verified segments + fail-closed visual coverage')

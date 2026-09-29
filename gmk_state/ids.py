from __future__ import annotations
from threading import Lock
import re
from .constants import ID_PREFIX_BY_OBJECT_TYPE
from .errors import StateEngineError

class IDAllocator:
    def __init__(self, existing_ids=()):
        self._lock=Lock(); self._counters={k:0 for k in ID_PREFIX_BY_OBJECT_TYPE}; ids=list(existing_ids)
        for typ,prefix in ID_PREFIX_BY_OBJECT_TYPE.items():
            pat=re.compile(rf"^{re.escape(prefix)}(\d+)$")
            for oid in ids:
                m=pat.match(str(oid))
                if m: self._counters[typ]=max(self._counters[typ],int(m.group(1)))
    def allocate(self, object_type:str, occupied:set[str])->str:
        if object_type not in ID_PREFIX_BY_OBJECT_TYPE:
            raise StateEngineError("UNKNOWN_OBJECT_TYPE",f"No system ID prefix is registered for {object_type}.")
        prefix=ID_PREFIX_BY_OBJECT_TYPE[object_type]
        with self._lock:
            while True:
                self._counters[object_type]+=1
                candidate=f"{prefix}{self._counters[object_type]:06d}"
                if candidate not in occupied: return candidate

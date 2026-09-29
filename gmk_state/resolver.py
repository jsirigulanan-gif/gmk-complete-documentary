from __future__ import annotations
from enum import Enum
from copy import deepcopy
from .errors import StateEngineError
from .registry import global_index
class ResolverMode(str,Enum): EXACT='EXACT'; ACTIVE='ACTIVE'; HEAD='HEAD'
class Resolver:
    def __init__(self,state): self._state=state; self._index=global_index(state.registries)
    def resolve(self,object_id:str,*,mode:ResolverMode=ResolverMode.EXACT,version:int|None=None):
        rid=self._index.get(object_id)
        if rid is None:return None
        entry=self._state.registries[rid].entries[object_id]
        if mode==ResolverMode.EXACT:
            if version is None: raise StateEngineError('EXACT_VERSION_REQUIRED','EXACT resolution requires an explicit integer version.')
            v=int(version)
        elif mode==ResolverMode.ACTIVE:
            if entry.active_version is None:return None
            v=entry.active_version
        elif mode==ResolverMode.HEAD:v=entry.head_version
        else: raise StateEngineError('RESOLVER_MODE_INVALID',f'Unknown resolver mode {mode}.')
        obj=self._state.objects.get((object_id,v)); return deepcopy(obj) if obj is not None else None
    def resolve_ref(self,ref):return self.resolve(ref['id'],mode=ResolverMode.EXACT,version=int(ref['version']))

from __future__ import annotations
from typing import Any
from gmk_semantics.model import sha256_json
from .constants import REGISTRY_BY_OBJECT_TYPE, STANDARD_REGISTRY_IDS
from .errors import StateEngineError
from .models import RegistrySnapshot, RegistryEntry, VersionLocator

def registry_id_for_type(object_type:str)->str:
    try: return REGISTRY_BY_OBJECT_TYPE[object_type]
    except KeyError as exc: raise StateEngineError('REGISTRY_MAPPING_MISSING',f'No registry mapping exists for object type {object_type}.') from exc

def object_uri(object_id:str,version:int)->str: return f'gmk://objects/{object_id}/v{version}'

def locator_for(obj:dict[str,Any],decision_sha256:str)->VersionLocator:
    return VersionLocator(int(obj['version']),object_uri(obj['id'],int(obj['version'])),decision_sha256,sha256_json(obj),obj['created_at'],obj['updated_at'])

def ensure_registry(registries:dict[str,RegistrySnapshot],registry_id:str)->RegistrySnapshot:
    if registry_id not in registries: registries[registry_id]=RegistrySnapshot(registry_id=registry_id,version=1,entries={})
    return registries[registry_id]

def build_registries(objects,decision_hasher):
    registries={rid:RegistrySnapshot(registry_id=rid,version=1,entries={}) for rid in STANDARD_REGISTRY_IDS}; grouped={}
    for obj in objects.values(): grouped.setdefault(obj['id'],[]).append(obj)
    for oid,versions in grouped.items():
        versions.sort(key=lambda x:int(x['version'])); typ=versions[-1]['object_type']; rid=registry_id_for_type(typ); reg=ensure_registry(registries,rid)
        locators={int(o['version']):locator_for(o,decision_hasher(o)) for o in versions}
        eligible=[o for o in versions if o.get('status') not in {'STALE','BLOCKED','ARCHIVED','REJECTED'} and not (o.get('stale') or {}).get('is_stale')]
        active=int(eligible[-1]['version']) if eligible else None
        reg.entries[oid]=RegistryEntry(oid,typ,int(versions[-1]['version']),active,locators)
    return registries

def global_index(registries):
    idx={}
    for rid,reg in registries.items():
        for oid in reg.entries:
            if oid in idx and idx[oid]!=rid: raise StateEngineError('GLOBAL_ID_COLLISION',f'Object ID {oid} appears in both {idx[oid]} and {rid}.')
            idx[oid]=rid
    return idx

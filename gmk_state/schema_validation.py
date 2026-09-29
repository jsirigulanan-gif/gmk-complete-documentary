from __future__ import annotations
from pathlib import Path
from typing import Any
import json
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from gmk_semantics.catalog import SchemaCatalog
from .errors import StateEngineIssue

class StructuralValidator:
    def __init__(self, root:Path):
        self.root=root; self.catalog=SchemaCatalog(root)
        registry_file=json.loads((root/'schema/schema-registry.json').read_text(encoding='utf-8'))['schemas']
        self.schemas={sid:json.loads((root/rel).read_text(encoding='utf-8')) for sid,rel in registry_file.items()}
        reg=Registry()
        for sid,schema in self.schemas.items(): reg=reg.with_resource(sid,Resource.from_contents(schema))
        self.registry=reg
    def validate_object(self,obj:dict[str,Any]):
        typ=str(obj.get('object_type','')); schema=self.catalog.schema_for_object_type(typ)
        if not schema: return [StateEngineIssue('OBJECT_SCHEMA_NOT_FOUND',f'No schema registered for Core Object type {typ}.')]
        validator=Draft202012Validator(schema,registry=self.registry,format_checker=FormatChecker())
        out=[]
        for err in sorted(validator.iter_errors(obj),key=lambda e:list(e.path)):
            path='/'+'/'.join(str(x) for x in err.path) if err.path else '/'
            out.append(StateEngineIssue('STRUCTURAL_SCHEMA_VIOLATION',err.message,path=path,target=f"{obj.get('id','?')}@{obj.get('version','?')}"))
        return out
    def validate_artifact(self, artifact:dict[str,Any]):
        sid=((artifact.get("schema_header") or {}).get("schema_id"))
        schema=self.schemas.get(str(sid)) if sid else None
        if not schema:
            return [StateEngineIssue("ARTIFACT_SCHEMA_NOT_FOUND",f"No schema registered for Artifact schema_id {sid}.",target=f"{artifact.get('artifact_id','?')}@{artifact.get('version','?')}")]
        validator=Draft202012Validator(schema,registry=self.registry,format_checker=FormatChecker())
        out=[]
        for err in sorted(validator.iter_errors(artifact),key=lambda e:list(e.path)):
            path='/'+'/'.join(str(x) for x in err.path) if err.path else '/'
            out.append(StateEngineIssue('STRUCTURAL_ARTIFACT_SCHEMA_VIOLATION',err.message,path=path,target=f"{artifact.get('artifact_id','?')}@{artifact.get('version','?')}"))
        return out

    def validate_manifest(self, manifest:dict[str,Any]):
        schema=self.schemas.get('gmk://schema/v1/project-manifest')
        if not schema:
            return [StateEngineIssue('MANIFEST_SCHEMA_NOT_FOUND','Project Manifest schema is not registered.')]
        validator=Draft202012Validator(schema,registry=self.registry,format_checker=FormatChecker())
        out=[]
        for err in sorted(validator.iter_errors(manifest),key=lambda e:list(e.path)):
            path='/'+'/'.join(str(x) for x in err.path) if err.path else '/'
            out.append(StateEngineIssue('STRUCTURAL_MANIFEST_SCHEMA_VIOLATION',err.message,path=path,target=f"{manifest.get('manifest_id','?')}@{manifest.get('manifest_version','?')}") )
        return out

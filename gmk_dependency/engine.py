from __future__ import annotations
from collections import deque
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from gmk_semantics.model import decision_projection, sha256_json
import hashlib
from .models import (
    NodeKey, NodeKind, DependencyEdge, ChangeSet, ImpactRecord,
    DependencyImpactReport, ImpactDisposition, max_disposition,
)
from .policy import DependencyPolicy
from .schema_projection import SchemaDependencyCompiler
from .graph import DependencyGraph


def _escape_pointer_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _diff_paths(a: Any, b: Any, path: str = "") -> list[str]:
    if type(a) is not type(b):
        return [path or "/"]
    if isinstance(a, dict):
        out=[]
        for key in sorted(set(a) | set(b)):
            p=f"{path}/{_escape_pointer_token(str(key))}" if path else f"/{_escape_pointer_token(str(key))}"
            if key not in a or key not in b: out.append(p)
            else: out.extend(_diff_paths(a[key], b[key], p))
        return out
    if isinstance(a, list):
        if a == b: return []
        # List element identity is domain-specific. The conservative v1 change set
        # marks the whole list as changed rather than inventing positional semantics.
        return [path or "/"]
    return [] if a == b else [path or "/"]


class DependencyEngine:
    def __init__(self, root: Path, semantic_catalog=None):
        self.root=Path(root)
        self.compiler=SchemaDependencyCompiler(self.root, semantic_catalog)
        self.policy=DependencyPolicy.load(self.root/'config/dependency_policies.yaml')

    @property
    def policy_ref(self) -> dict[str, Any]:
        path=self.root/'config/dependency_policies.yaml'
        return {"config_id": self.policy.config_id, "version": self.policy.version, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def compile_object_projection(self, obj: dict[str, Any]) -> list[dict[str, Any]]:
        return self.compiler.project_object(obj)

    @staticmethod
    def _norm_dependencies(items: Iterable[dict[str, Any]]) -> list[tuple[str,str,int,str]]:
        out=[]
        for d in items or []:
            t=d.get('target') or {}; rel=str(d.get('relation',''))
            if 'artifact_id' in t:
                out.append(('ARTIFACT',str(t.get('artifact_id')),int(t.get('version',0)),rel))
            elif 'id' in t:
                out.append(('OBJECT',str(t.get('id')),int(t.get('version',0)),rel))
        return sorted(out)

    def projection_mismatch(self, obj: dict[str, Any]) -> bool:
        expected=self.compile_object_projection(obj)
        return self._norm_dependencies(obj.get('dependencies',[])) != self._norm_dependencies(expected)

    def projection_issues(self, objects: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        issues=[]
        for obj in objects:
            expected=self.compile_object_projection(obj)
            if self._norm_dependencies(obj.get('dependencies',[])) != self._norm_dependencies(expected):
                issues.append({
                    'code':'DEPENDENCY_PROJECTION_MISMATCH',
                    'target':f"{obj.get('id')}@{obj.get('version')}",
                    'stored':deepcopy(obj.get('dependencies',[])),
                    'expected':expected,
                })
        return issues

    def build_graph(self, state) -> DependencyGraph:
        edges: list[DependencyEdge] = []
        for obj in state.objects.values():
            edges.extend(self.compiler.object_edges(obj))
        for art in state.artifacts.values():
            edges.extend(self.compiler.artifact_edges(art))
        return DependencyGraph.build(edges)

    def changes_between(self, before: dict[str,Any], after: dict[str,Any], semantic) -> ChangeSet:
        # decision_projection respects root-derived exclusions through the semantic hash catalog.
        derived=semantic.catalog.derived_root_fields(before.get('object_type',''))
        bp=decision_projection(before,derived)
        ap=decision_projection(after,derived)
        paths=tuple(sorted(set(_diff_paths(bp,ap))))
        # SEARCH_RESULT selection/promotion fields are lifecycle bookkeeping. They
        # record that a candidate was selected/promoted but do not change the
        # discovered source, inspection, or visual evidence that downstream Assets
        # were derived from. Treat lifecycle-only revisions as NON_PRODUCTION so an
        # Asset does not stale itself after its source candidate is promoted.
        if before.get('object_type') == 'SEARCH_RESULT' and paths:
            lifecycle_prefixes=(
                '/candidate_state',
                '/promoted_asset_ref',
                '/extensions/asset_recon/selection_',
                '/extensions/asset_recon/promoted',
            )
            if all(any(path.startswith(prefix) for prefix in lifecycle_prefixes) for path in paths):
                tags=('NON_PRODUCTION',)
            else:
                tags=tuple(sorted(self.policy.tags_for_paths(paths)))
        else:
            tags=tuple(sorted(self.policy.tags_for_paths(paths)))
        return ChangeSet(str(before['id']),int(before['version']),int(after['version']),paths,tags)

    def _node_record(self, state, node: NodeKey) -> dict[str,Any] | None:
        if node.kind==NodeKind.OBJECT:
            return state.objects.get((node.node_id,node.version))
        return state.artifacts.get((node.node_id,node.version))

    def _is_frozen_boundary(self, state, node: NodeKey) -> bool:
        rec=self._node_record(state,node)
        if not rec:return False
        if node.kind==NodeKind.OBJECT:
            # Operations are immutable/exact side-effect records whose subject is an
            # audit anchor, not a semantic production dependency. Treat them as a
            # propagation boundary to prevent operational lifecycle versions from
            # creating circular stale chains back into their subject Asset.
            if str(rec.get('object_type')) == 'OPERATION':
                return True
            return self.policy.is_frozen_object(rec)
        # Dependency impact reports are immutable audit snapshots of a past
        # promotion analysis. They must remain historical truth rather than
        # becoming a live dependent of the very change they document.
        if str(rec.get('artifact_type')) == 'DEPENDENCY_IMPACT_REPORT':
            return True
        return self.policy.is_frozen_artifact(rec)

    def _is_live_node(self,state,node:NodeKey)->bool:
        if node.kind==NodeKind.ARTIFACT:
            # Artifact Registry lifecycle is implemented later; immutable artifacts
            # remain graph-addressable in Build 004 and frozen boundaries stop history.
            return True
        from gmk_state.registry import global_index
        rid=global_index(state.registries).get(node.node_id)
        if not rid:return False
        entry=state.registries[rid].entries.get(node.node_id)
        return bool(entry and node.version in {entry.head_version,entry.active_version})

    @staticmethod
    def _blast_for(node_record: dict[str,Any] | None, depth:int) -> str:
        if not node_record:return 'PROJECT' if depth>3 else 'LOCAL'
        typ=str(node_record.get('object_type') or node_record.get('artifact_type') or '')
        if typ in {'LAYER','CUE','SHOT','MOTION_PREVIS','THREE_D_PREVIS'}: return 'LOCAL'
        if typ in {'SCENE','SCENE_PLAN','SCENE_PREVIEW','REVIEW_PACKAGE'}: return 'SCENE'
        if typ in {'ACT'}: return 'ACT'
        return 'PROJECT' if depth>1 else 'LOCAL'

    def analyze_version_change(self,state,object_id:str,previous_version:int,new_version:int,semantic)->DependencyImpactReport:
        before=state.objects[(object_id,int(previous_version))]; after=state.objects[(object_id,int(new_version))]
        cs=self.changes_between(before,after,semantic)
        old_node=NodeKey(NodeKind.OBJECT,object_id,int(previous_version)); new_node=NodeKey(NodeKind.OBJECT,object_id,int(new_version))
        report=DependencyImpactReport(old_node,new_node,cs,policy_ref=self.policy_ref)
        if not cs.changed_paths:
            return report
        graph=self.build_graph(state)
        q=deque([(old_node,0,ImpactDisposition.UNAFFECTED)])
        best: dict[NodeKey,ImpactDisposition]={old_node:ImpactDisposition.UNAFFECTED}
        root_tags=set(cs.impact_tags)
        seen_edges=set()
        while q:
            upstream,depth,parent_disp=q.popleft()
            for edge in graph.dependents_of(upstream):
                # SUPERSEDES is lineage, not a production dependency. A new
                # version necessarily points at the version it supersedes; an
                # ACTIVE promotion must never invalidate the new version through
                # that lineage edge, nor propagate impact across it.
                if edge.relation == 'SUPERSEDES':
                    continue
                ek=(edge.dependent,edge.target,edge.relation,edge.source_path)
                if ek in seen_edges: continue
                seen_edges.add(ek)
                if not self._is_live_node(state,edge.dependent):
                    continue
                if self._is_frozen_boundary(state,edge.dependent):
                    report.frozen_stops.append(edge.dependent)
                    continue
                direct=self.policy.disposition_for(edge.relation,root_tags)
                disp=max_disposition(parent_disp,direct)
                existing=best.get(edge.dependent)
                if existing is not None:
                    stronger=max_disposition(existing,disp)
                    if stronger==existing: continue
                    best[edge.dependent]=stronger
                    disp=stronger
                else:
                    best[edge.dependent]=disp
                rec=self._node_record(state,edge.dependent)
                blast=self._blast_for(rec,depth+1)
                reason='DEPENDENCY_REVALIDATION_REQUIRED' if disp==ImpactDisposition.REVALIDATE else (
                    'DEPENDENCY_BLOCKED' if disp==ImpactDisposition.BLOCKED else ('DEPENDENCY_STALE' if disp==ImpactDisposition.STALE else 'DEPENDENCY_UNAFFECTED')
                )
                report.impacts.append(ImpactRecord(
                    node=edge.dependent,disposition=disp,relation=edge.relation,depth=depth+1,
                    immediate_dependency=upstream,root_previous=old_node,root_new=new_node,
                    reason_code=reason,
                    message=(f"{edge.dependent.label()} depends on {upstream.label()} via {edge.relation}; "
                             f"ACTIVE root changed {old_node.label()} -> {new_node.label()} ({', '.join(cs.impact_tags)})."),
                    blast_radius=blast,path=edge.source_path,
                ))
                if disp != ImpactDisposition.UNAFFECTED:
                    q.append((edge.dependent,depth+1,disp))
        report.impacts.sort(key=lambda x:(x.depth,x.node.label(),x.relation,x.path or ''))
        report.frozen_stops=sorted(set(report.frozen_stops))
        return report

    def analyze_promotion(self, state, object_id:str, new_version:int, semantic) -> DependencyImpactReport:
        # The root event is ACTIVE old -> ACTIVE new. If there is no old ACTIVE,
        # activation establishes trust but does not invalidate anything.
        from gmk_state.registry import global_index
        idx=global_index(state.registries); rid=idx.get(object_id)
        if not rid: raise KeyError(object_id)
        entry=state.registries[rid].entries[object_id]
        old=entry.active_version
        if old is None or int(old)==int(new_version):
            cs=ChangeSet(object_id,int(new_version),int(new_version),(),())
            node=NodeKey(NodeKind.OBJECT,object_id,int(new_version))
            return DependencyImpactReport(node,node,cs,policy_ref=self.policy_ref)
        return self.analyze_version_change(state,object_id,int(old),int(new_version),semantic)

    def recompute_live_state(self,state,semantic,now:str)->dict[str,Any]:
        """Full cold-start recompute from exact refs versus reconstructed ACTIVE heads.

        Stored dependency projections are checked separately. This routine rebuilds
        effective invalidation state; it never retargets exact references. A clean
        persisted live-derived envelope must be idempotent: recomputing the same
        dependency facts must not refresh timestamps or registry record hashes.
        """
        state.dependency_invalidations={}

        # Snapshot live derived envelopes so equivalent recomputation can preserve
        # their historical detected_at/updated_at timestamps byte-for-byte.
        original={}
        for key,obj in state.objects.items():
            node=NodeKey(NodeKind.OBJECT,str(obj.get('id')),int(obj.get('version',0)))
            if self._is_live_node(state,node):
                original[key]={
                    'stale':deepcopy(obj.get('stale')),
                    'status':obj.get('status'),
                    'approval_summary':deepcopy(obj.get('approval_summary')),
                    'updated_at':obj.get('updated_at'),
                }

        # Clear only dependency-derived state on live nodes. Historical versions
        # remain audit history and are never rewritten by cold-start recompute.
        for key,snap in original.items():
            obj=state.objects[key]
            reasons=list((obj.get('stale') or {}).get('reasons') or [])
            other=[r for r in reasons if not str(r.get('code','')).startswith('DEPENDENCY_')]
            if len(other)!=len(reasons):
                obj['stale']={'is_stale':bool(other),'reasons':other}
                if not other and obj.get('status') in {'STALE','BLOCKED'}:
                    obj['status']='CURRENT'

        graph=self.build_graph(state)
        from gmk_state.registry import global_index
        idx=global_index(state.registries)
        drifts=set()
        for dependent,edges in graph.forward.items():
            if not self._is_live_node(state,dependent):
                continue
            for edge in edges:
                if edge.target.kind!=NodeKind.OBJECT:
                    continue
                # Lineage and frozen historical snapshots are not live drift.
                if edge.relation == 'SUPERSEDES' or self._is_frozen_boundary(state,dependent):
                    continue
                rid=idx.get(edge.target.node_id)
                if not rid:
                    continue
                entry=state.registries[rid].entries[edge.target.node_id]
                av=entry.active_version
                if av is not None and int(av)!=edge.target.version and (edge.target.node_id,edge.target.version) in state.objects and (edge.target.node_id,int(av)) in state.objects:
                    drifts.add((edge.target.node_id,edge.target.version,int(av)))

        reports=[]
        for oid,old,new in sorted(drifts):
            report=self.analyze_version_change(state,oid,old,new,semantic)
            reports.append(report)
            self.apply_report(state,report,now)

        def reason_sig(reason):
            dep=reason.get('dependency') or {}
            return (
                reason.get('code'),
                str(dep.get('target')),
                dep.get('relation'),
                reason.get('message'),
            )

        changed=set()
        for key,snap in original.items():
            obj=state.objects[key]
            old_stale=snap.get('stale') or {'is_stale':False,'reasons':[]}
            new_stale=obj.get('stale') or {'is_stale':False,'reasons':[]}
            old_sig=(bool(old_stale.get('is_stale')),sorted(reason_sig(r) for r in old_stale.get('reasons',[])))
            new_sig=(bool(new_stale.get('is_stale')),sorted(reason_sig(r) for r in new_stale.get('reasons',[])))
            equivalent=(
                old_sig==new_sig and
                snap.get('status')==obj.get('status') and
                snap.get('approval_summary')==obj.get('approval_summary')
            )
            if equivalent:
                # Preserve exact prior records, including original reason timestamps.
                obj['stale']=deepcopy(snap.get('stale'))
                obj['status']=snap.get('status')
                obj['approval_summary']=deepcopy(snap.get('approval_summary'))
                obj['updated_at']=snap.get('updated_at')
            else:
                obj['updated_at']=now
                changed.add(key)

        return {'changed_objects':sorted(changed),'reports':reports,'drift_roots':len(drifts),'invalidations':len(state.dependency_invalidations)}

    def apply_report(self, state, report: DependencyImpactReport, now: str) -> dict[str,Any]:
        """Apply live derived invalidation without changing authoritative decisions.

        Core Object STALE/BLOCKED is persisted in live-derived envelope fields.
        REVALIDATE and Artifact invalidations live in runtime infrastructure.
        Frozen nodes are intentionally untouched.
        """
        changed_objects=[]
        state.dependency_invalidations = dict(getattr(state,'dependency_invalidations',{}))
        for impact in report.impacts:
            n=impact.node
            if impact.disposition==ImpactDisposition.UNAFFECTED:
                continue
            state.dependency_invalidations[n]=impact.to_dict()
            if n.kind!=NodeKind.OBJECT: continue
            key=(n.node_id,n.version); obj=state.objects.get(key)
            if not obj: continue
            if impact.disposition==ImpactDisposition.REVALIDATE:
                continue
            if impact.disposition not in {ImpactDisposition.STALE,ImpactDisposition.BLOCKED}:
                continue
            reason={
                'code':impact.reason_code,
                'message':impact.message,
                'dependency':{'target':impact.immediate_dependency.to_ref(),'relation':impact.relation},
                'detected_at':now,
            }
            reasons=list((obj.get('stale') or {}).get('reasons') or [])
            sig=(reason['code'], str(reason['dependency']['target']), reason['dependency']['relation'])
            have={(r.get('code'),str((r.get('dependency') or {}).get('target')),((r.get('dependency') or {}).get('relation'))) for r in reasons}
            before=(deepcopy(obj.get('stale')),obj.get('status'),deepcopy(obj.get('approval_summary')))
            if sig not in have:
                reasons.append(reason)
            obj['stale']={'is_stale':True,'reasons':reasons}
            obj['status']='BLOCKED' if impact.disposition==ImpactDisposition.BLOCKED else 'STALE'
            if (obj.get('approval_summary') or {}).get('state') not in {'NOT_REQUIRED','REQUIRED'}:
                obj['approval_summary']={'state':'INVALIDATED','approval_refs':list((obj.get('approval_summary') or {}).get('approval_refs') or [])}
            after=(obj.get('stale'),obj.get('status'),obj.get('approval_summary'))
            if before != after:
                obj['updated_at']=now
                changed_objects.append(key)
        return {'changed_objects':changed_objects,'runtime_invalidations':len(report.impacts)}

    def revalidate_node(self, state, node: NodeKey, now: str) -> bool:
        """Clear derived invalidation only when direct exact dependencies are resolvable
        and none is currently stale/blocked/invalidated. Decision version is unchanged.
        """
        graph=self.build_graph(state)
        for edge in graph.dependencies_of(node):
            target=self._node_record(state,edge.target)
            if target is None:return False
            if edge.target in getattr(state,'dependency_invalidations',{}): return False
            if edge.target.kind==NodeKind.OBJECT:
                if target.get('status') in {'STALE','BLOCKED','ARCHIVED','REJECTED'}: return False
                if (target.get('stale') or {}).get('is_stale'): return False
        if hasattr(state,'dependency_invalidations'):
            state.dependency_invalidations.pop(node,None)
        if node.kind==NodeKind.OBJECT:
            obj=state.objects.get((node.node_id,node.version))
            if obj is None:return False
            dep_reasons=[r for r in (obj.get('stale') or {}).get('reasons',[]) if str(r.get('code','')).startswith('DEPENDENCY_')]
            other=[r for r in (obj.get('stale') or {}).get('reasons',[]) if r not in dep_reasons]
            before=(deepcopy(obj.get('stale')),obj.get('status'))
            obj['stale']={'is_stale':bool(other),'reasons':other}
            if not other and obj.get('status') in {'STALE','BLOCKED'}: obj['status']='CURRENT'
            if before != (obj.get('stale'),obj.get('status')):
                obj['updated_at']=now
        return True

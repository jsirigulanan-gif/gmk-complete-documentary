from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json
import subprocess

from gmk_runtime.media_tools import resolve_ffprobe, MediaToolNotFound
from gmk_assets import MediaHandoffRuntime, MediaHandoffError


class PilotMediaIntakeError(RuntimeError):
    pass


def _stable_sha(payload: Any) -> str:
    raw=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def _sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: Path,payload: Any) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')


def _probe(path: Path) -> dict[str,Any]:
    try:
        cp=subprocess.run([
            resolve_ffprobe(),'-v','error','-print_format','json','-show_format','-show_streams',str(path)
        ],check=True,capture_output=True,text=True)
    except (FileNotFoundError, MediaToolNotFound) as exc:
        raise PilotMediaIntakeError('PILOT_INTAKE_FFPROBE_NOT_INSTALLED') from exc
    except subprocess.CalledProcessError as exc:
        msg=(exc.stderr or exc.stdout or '').strip()
        raise PilotMediaIntakeError(f'PILOT_INTAKE_FFPROBE_FAILED: {path}: {msg[:300]}') from exc
    try:
        raw=json.loads(cp.stdout)
    except json.JSONDecodeError as exc:
        raise PilotMediaIntakeError(f'PILOT_INTAKE_FFPROBE_INVALID_JSON: {path}') from exc
    streams=raw.get('streams') or []
    video=next((s for s in streams if s.get('codec_type')=='video'),None)
    if video is None:
        raise PilotMediaIntakeError(f'PILOT_INTAKE_VIDEO_STREAM_REQUIRED: {path}')
    fmt=raw.get('format') or {}
    try:duration=float(fmt.get('duration'))
    except (TypeError,ValueError):duration=0.0
    if duration<=0:
        vals=[]
        for s in streams:
            if s.get('codec_type')!='video':continue
            try:vals.append(float(s.get('duration')))
            except (TypeError,ValueError):pass
        duration=max(vals) if vals else 0.0
    if duration<=0:
        raise PilotMediaIntakeError(f'PILOT_INTAKE_DURATION_REQUIRED: {path}')
    return {
        'container':str(fmt.get('format_name') or 'unknown'),
        'duration_seconds':round(duration,6),
        'codec':str(video.get('codec_name') or 'unknown'),
        'width':int(video.get('width') or 1),
        'height':int(video.get('height') or 1),
        'audio_present':any(s.get('codec_type')=='audio' for s in streams),
    }


@dataclass(frozen=True)
class PilotMediaIntakeInitResult:
    intake_dir: Path
    requirement_count: int
    slots: tuple[dict[str,Any],...]
    manifest_path: Path
    worksheet_path: Path
    readme_path: Path
    manifest_sha256: str

    def to_dict(self)->dict[str,Any]:
        return {
            'intake_dir':str(self.intake_dir),'requirement_count':self.requirement_count,
            'slots':[deepcopy(x) for x in self.slots],
            'manifest_path':str(self.manifest_path),'worksheet_path':str(self.worksheet_path),
            'readme_path':str(self.readme_path),'manifest_sha256':self.manifest_sha256,
        }


@dataclass(frozen=True)
class PilotMediaIntakeBuildResult:
    intake_dir: Path
    ready: bool
    item_count: int
    handoff_plan_path: Path
    receipt_path: Path
    plan_sha256: str
    receipt_sha256: str
    items: tuple[dict[str,Any],...]

    def to_dict(self)->dict[str,Any]:
        return {
            'intake_dir':str(self.intake_dir),'ready':self.ready,'item_count':self.item_count,
            'handoff_plan_path':str(self.handoff_plan_path),'receipt_path':str(self.receipt_path),
            'plan_sha256':self.plan_sha256,'receipt_sha256':self.receipt_sha256,
            'items':[deepcopy(x) for x in self.items],
        }


class PilotMediaIntakeRuntime:
    """Non-mutating operator UX for P.T. source-locked external video intake.

    The runtime never downloads media and never decides content identity from a
    filename alone. Each pending candidate receives a dedicated slot whose source
    identity is derived from the authoritative MediaHandoff requirement. The
    operator supplies exactly one authorized local video per slot and an explicit
    inspection worksheet. Build then probes/hashes the bytes, compiles a complete
    handoff plan, and asks MediaHandoffRuntime to validate that exact plan without
    mutating the workspace.
    """

    _IGNORED={'README.txt','.DS_Store','Thumbs.db'}

    def __init__(self,schema_root: Path,workspace: Path):
        self.root=Path(schema_root);self.workspace=Path(workspace)

    def _requirements(self)->tuple[dict[str,Any],...]:
        reqs=MediaHandoffRuntime(self.root,self.workspace).requirements()
        if not reqs:
            raise PilotMediaIntakeError('PILOT_INTAKE_NO_PENDING_VIDEO_REQUIREMENTS')
        return tuple(r.to_dict() for r in reqs)

    def init(self,intake_dir: Path)->PilotMediaIntakeInitResult:
        intake=Path(intake_dir);intake.mkdir(parents=True,exist_ok=True)
        reqs=self._requirements();slots=[];worksheet=[]
        for req in reqs:
            key=req['candidate_key'];slot=intake/key;slot.mkdir(parents=True,exist_ok=True)
            marker=slot/'README.txt'
            marker.write_text(
                'Place exactly ONE authorized local video file in this directory.\n'
                f'Candidate: {key}\nCanonical source: {req["canonical_source_url"]}\n'
                'Do not place screenshots, webpage exports, synthetic fixtures, or unrelated reuploads here.\n',
                encoding='utf-8')
            slot_info={
                'candidate_key':key,'slot_dir':str(slot),
                'canonical_source_url':req['canonical_source_url'],
                'source_result_ref':deepcopy(req['source_result_ref']),
                'asset_ref':deepcopy(req['asset_ref']),
                'locked_locator':deepcopy(req['candidate_locator']),
                'rights_status':req['rights_status'],'attribution_required':req['attribution_required'],
            }
            slots.append(slot_info)
            locked=req.get('candidate_locator') or {}
            worksheet.append({
                'candidate_key':key,
                'source_url':req['canonical_source_url'],
                'operator':'',
                'inspection_note':'',
                'start_seconds':locked.get('start_seconds') if locked.get('type')=='VIDEO_TIME_RANGE' else None,
                'end_seconds':locked.get('end_seconds') if locked.get('type')=='VIDEO_TIME_RANGE' else None,
                'key_seconds':locked.get('key_seconds') if locked.get('type')=='VIDEO_TIME_RANGE' else None,
                'visual_content':'',
                'match_reason':'',
            })
        manifest={
            'build':'037','purpose':'P.T. authorized external-media intake slots',
            'workspace':str(self.workspace),'requirements':slots,
            'hard_boundary':'One authorized local video per source-locked candidate slot. Slot identity does not prove content; operator inspection remains mandatory.',
        }
        manifest['manifest_sha256']=_stable_sha(manifest)
        manifest_path=intake/'PT_MEDIA_INTAKE_MANIFEST.json';worksheet_path=intake/'PT_MEDIA_INSPECTION_WORKSHEET.json';readme=intake/'README.md'
        _write_json(manifest_path,manifest)
        _write_json(worksheet_path,{'batch_id':'PT_MEDIA_HANDOFF_037','items':worksheet})
        readme.write_text(self._readme(reqs),encoding='utf-8')
        return PilotMediaIntakeInitResult(intake,len(reqs),tuple(slots),manifest_path,worksheet_path,readme,manifest['manifest_sha256'])

    def _readme(self,reqs: tuple[dict[str,Any],...])->str:
        lines=['# P.T. External Media Intake — Build 037','',
               'This directory is a non-authoritative staging area. Adding files here does **not** mutate `PT_WORKSPACE`.','',
               '## Workflow','',
               '1. Put exactly one authorized video in each candidate directory.',
               '2. Fill `PT_MEDIA_INSPECTION_WORKSHEET.json` after inspecting the actual media.',
               '3. Run `pilot-media-intake-build`; it probes, hashes, creates a receipt, compiles the handoff plan, and performs the same non-mutating handoff validation used by execution.',
               '4. Review the receipt. Only then run the existing `pilot-media-execute` with the generated handoff plan.','',
               '## Source locks','']
        for r in reqs:
            lines += [f"- `{r['candidate_key']}` → {r['canonical_source_url']}"]
        lines += ['','A directory name or checksum never proves visual identity by itself. The human inspection worksheet is required.','']
        return '\n'.join(lines)

    @staticmethod
    def _slot_file(slot: Path)->Path:
        if not slot.exists() or not slot.is_dir():
            raise PilotMediaIntakeError(f'PILOT_INTAKE_SLOT_MISSING: {slot}')
        files=[p for p in slot.iterdir() if p.is_file() and p.name not in PilotMediaIntakeRuntime._IGNORED and not p.name.startswith('.')]
        if not files:
            raise PilotMediaIntakeError(f'PILOT_INTAKE_MEDIA_MISSING: {slot.name}')
        if len(files)>1:
            raise PilotMediaIntakeError(f'PILOT_INTAKE_EXACTLY_ONE_MEDIA_REQUIRED: {slot.name} count={len(files)}')
        return files[0]

    @staticmethod
    def _inspection_map(inspection: dict[str,Any])->tuple[str,dict[str,dict[str,Any]]]:
        batch=str(inspection.get('batch_id') or '').strip()
        if not batch:raise PilotMediaIntakeError('PILOT_INTAKE_BATCH_ID_REQUIRED')
        items=inspection.get('items') or []
        by={}
        for item in items:
            key=str(item.get('candidate_key') or '').strip()
            if not key or key in by:raise PilotMediaIntakeError(f'PILOT_INTAKE_INSPECTION_KEY_INVALID:{key}')
            by[key]=item
        return batch,by

    def build(self,intake_dir: Path,inspection: dict[str,Any],output_dir: Path|None=None)->PilotMediaIntakeBuildResult:
        intake=Path(intake_dir);out=Path(output_dir) if output_dir else intake
        reqs=self._requirements();batch,inspections=self._inspection_map(inspection)
        expected={r['candidate_key'] for r in reqs}
        if set(inspections)!=expected:
            raise PilotMediaIntakeError(f'PILOT_INTAKE_COMPLETE_INSPECTION_SET_REQUIRED: expected={sorted(expected)} got={sorted(inspections)}')
        plan_items=[];receipt_items=[]
        for req in reqs:
            key=req['candidate_key'];ins=inspections[key];media=self._slot_file(intake/key)
            technical=_probe(media);checksum=_sha256(media)
            operator=str(ins.get('operator') or '').strip();note=str(ins.get('inspection_note') or '').strip()
            visual=str(ins.get('visual_content') or '').strip();reason=str(ins.get('match_reason') or '').strip()
            if not operator:raise PilotMediaIntakeError(f'PILOT_INTAKE_OPERATOR_REQUIRED:{key}')
            if not note:raise PilotMediaIntakeError(f'PILOT_INTAKE_INSPECTION_NOTE_REQUIRED:{key}')
            if not visual:raise PilotMediaIntakeError(f'PILOT_INTAKE_VISUAL_CONTENT_REQUIRED:{key}')
            if not reason:raise PilotMediaIntakeError(f'PILOT_INTAKE_MATCH_REASON_REQUIRED:{key}')
            selector={'type':'VIDEO_TIME_RANGE','start_seconds':ins.get('start_seconds'),'end_seconds':ins.get('end_seconds'),'key_seconds':ins.get('key_seconds')}
            plan_items.append({
                'candidate_key':key,'local_path':str(media.resolve()),
                'source_url':req['canonical_source_url'],'acquisition_method':'AUTHORIZED_MANUAL_IMPORT',
                'expected_sha256':checksum,
                'segment':{
                    'selector':selector,'source_locator':{'type':'FULL_SOURCE'},
                    'visual_content':visual,'match_type':'DIRECT','match_reason':reason,
                },
            })
            receipt_items.append({
                'candidate_key':key,'file_name':media.name,'local_path':str(media.resolve()),
                'size_bytes':media.stat().st_size,'sha256':checksum,'technical':technical,
                'canonical_source_url':req['canonical_source_url'],'source_result_ref':deepcopy(req['source_result_ref']),
                'asset_ref':deepcopy(req['asset_ref']),'locked_locator':deepcopy(req['candidate_locator']),
                'operator':operator,'inspection_note':note,'selector':selector,
            })
        plan={'batch_id':batch,'items':plan_items}
        # The existing handoff validator remains authoritative for source-lock/range/checksum validity.
        try:
            _,compiled=MediaHandoffRuntime(self.root,self.workspace).validate_plan(plan)
        except MediaHandoffError as exc:
            raise PilotMediaIntakeError(f'PILOT_INTAKE_HANDOFF_VALIDATION_FAILED: {exc}') from exc
        plan_sha=_stable_sha(plan)
        receipt={
            'build':'037','workspace':str(self.workspace),'intake_dir':str(intake.resolve()),
            'batch_id':batch,'plan_sha256':plan_sha,'items':receipt_items,
            'validated_items':[{
                'candidate_key':x['candidate_key'],'technical':deepcopy(x['technical']),
                'selector':deepcopy(x['segment']['selector']),'source_url':x['source_url'],
            } for x in compiled],
            'statement':'Receipt proves local bytes/technical metadata/checksum and records human inspection. It does not independently prove publisher-origin provenance beyond the source-locked operator declaration.',
        }
        receipt['receipt_sha256']=_stable_sha(receipt)
        plan_path=out/'PT_MEDIA_HANDOFF_READY.json';receipt_path=out/'PT_MEDIA_INTAKE_RECEIPT.json'
        _write_json(plan_path,plan);_write_json(receipt_path,receipt)
        return PilotMediaIntakeBuildResult(intake,True,len(plan_items),plan_path,receipt_path,plan_sha,receipt['receipt_sha256'],tuple(receipt_items))

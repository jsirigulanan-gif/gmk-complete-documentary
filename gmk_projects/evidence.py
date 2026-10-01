"""Archived public source text and explicit editorial decisions on canonical claims."""
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
import socket
from urllib.parse import urlparse
from urllib.request import Request, HTTPRedirectHandler, ProxyHandler, build_opener

from gmk_research.audit import ResearchAuditRuntime
from .edit import EditError, asset_file, fingerprint, media_ref
from .production import ProductionProject, RUNTIME_ROOT
from .storage import atomic_json


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript'):self.skip+=1
        if not self.skip and tag in ('p','div','br','li','h1','h2','h3'):self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript'):self.skip=max(0,self.skip-1)
        if not self.skip and tag in ('p','div','li','h1','h2','h3'):self.parts.append('\n')
    def handle_data(self,data):
        if not self.skip:self.parts.append(data)
    def text(self):
        return '\n'.join(line.strip() for line in ''.join(self.parts).splitlines() if line.strip())


def public_url(url):
    parsed=urlparse(url)
    if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,80,443):
        raise EditError('ต้องเป็น URL เว็บสาธารณะ http/https ที่ไม่ใส่รหัสผ่าน')
    addresses=socket.getaddrinfo(parsed.hostname,parsed.port or (443 if parsed.scheme=='https' else 80),type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise EditError('ไม่อ่านแหล่งข้อมูลจากเครือข่ายภายในหรือที่อยู่เครื่องนี้')
    return url


class PublicRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return super().redirect_request(req,fp,code,msg,headers,public_url(newurl))


def collect_source(project,url: str) -> dict:
    opener=build_opener(ProxyHandler({}),PublicRedirect())
    request=Request(public_url(url.strip()),headers={'User-Agent':'GMKDocumentary/1.0 (research archive)','Accept':'text/html,text/plain'})
    with opener.open(request,timeout=30) as response:
        content_type=response.headers.get_content_type()
        if content_type not in ('text/html','text/plain','application/xhtml+xml'):
            raise EditError('แหล่งนี้ไม่ใช่หน้าเว็บข้อความ โปรดเปิดตรวจด้วยเบราว์เซอร์และนำเข้าข้อมูลที่เกี่ยวข้อง')
        raw=response.read(3_000_001)
        if len(raw)>3_000_000:raise EditError('หน้าเว็บใหญ่เกิน 3 MB กรุณาเลือกแหล่งข้อความขนาดเล็กลง')
        encoding=response.headers.get_content_charset() or 'utf-8'
        final_url=response.geturl()
    decoded=raw.decode(encoding,errors='replace')
    if content_type!='text/plain':
        parser=PageText();parser.feed(decoded);text=parser.text()
    else:text=decoded
    if not text.strip():raise EditError('ไม่พบข้อความในหน้าเว็บนี้ อาจต้องเปิดด้วยเบราว์เซอร์')
    directory=project.root/'external_sources';directory.mkdir(exist_ok=True)
    key=fingerprint({'url':final_url,'raw':decoded})
    source=directory/(key+'.html' if content_type!='text/plain' else key+'.raw.txt')
    source.write_bytes(raw)
    raw_asset=project.add_file(source,'research',source_url=final_url)
    extracted=directory/(key+'.txt');extracted.write_text(text,encoding='utf-8')
    text_asset=project.add_file(extracted,'research',source_url=final_url)
    record={'url':final_url,'requested_url':url,'title':text.splitlines()[0][:200],
            'raw':media_ref(raw_asset),'text':media_ref(text_asset),'verification_status':'NOT_REVIEWED'}
    atomic_json(directory/(key+'.json'),record)
    return record


def review_claim(project,claim_id: str,expected_version: int,claim_text: str,*,source: dict|None=None,
                 excerpt='',disposition='INSUFFICIENT',note='') -> dict:
    if disposition not in ('SUPPORTED','CONTRADICTED','INSUFFICIENT') or not claim_text.strip():
        raise EditError('เลือกผลตรวจและใส่ข้อความข้อกล่าวอ้างให้ชัดเจน')
    batch={'provider':'GMK_OPERATOR_EVIDENCE_REVIEW','query':'Explicit editorial review of archived source text',
           'sources':[],'evidence':[],'claims':[],'limitations':['Source authority and independence are not automatically inferred.']}
    links=[]
    if disposition!='INSUFFICIENT':
        if not source or not excerpt.strip():raise EditError('ต้องเลือกแหล่งข้อมูลที่เก็บไว้และข้อความหลักฐาน')
        archived=asset_file(project,source['text'],'research').read_text(encoding='utf-8')
        asset_file(project,source['raw'],'research')
        if excerpt not in archived:raise EditError('ข้อความหลักฐานต้องตรงกับข้อความในแหล่งที่เก็บไว้')
        sources=project.read()['assets']
        text_asset=next(a for a in sources if a['path']==source['text']['path'])
        if source['url'] not in text_asset['source_urls']:raise EditError('URL ไม่ตรงกับแหล่งข้อมูลที่ลงทะเบียน')
        batch['sources']=[{'key':'S1','title':source['title'],'url':source['url'],'authority_class':'UNKNOWN',
                           'independence_group':'SRCGRP_UNCONFIRMED_EXTERNAL','independence_relationship':'UNKNOWN',
                           'availability':'ARCHIVED','language':'und',
                           'notes':'raw_sha256='+source['raw']['sha256']+'; extracted_text_sha256='+source['text']['sha256']}]
        batch['evidence']=[{'key':'E1','source_key':'S1','content_summary':excerpt,
                            'locator':{'type':'TEXT_RANGE','section':'Archived extracted source text','quote_anchor':excerpt[:200]},
                            'evidence_kind':'DOCUMENT_EXCERPT'}]
        links=[{'evidence_key':'E1','relation':'SUPPORTS' if disposition=='SUPPORTED' else 'CONTRADICTS',
                'strength':'STRONG','scope':['EVENT']}]
    batch['claims']=[{'claim_id':claim_id,'claim_text':claim_text.strip(),'evidence_links':links,
                      'force_prohibit':disposition!='SUPPORTED','audit_note':note,
                      'prohibit_reason':'Editorial review found insufficient or conflicting support.'}]
    production=ProductionProject(project)
    with project._lock():
        loaded=production._load()
        candidates=[o for o in loaded.engine.snapshot().objects.values() if o.get('id')==claim_id and o.get('object_type')=='CLAIM']
        if not candidates or max(c['version'] for c in candidates)!=expected_version:
            raise EditError('ข้อกล่าวอ้างเปลี่ยนรุ่นแล้ว กรุณาโหลดใหม่ก่อนตรวจ')
        current=max(candidates,key=lambda c:c['version'])
        batch['claims'][0]['replace_external_evidence_links'] = claim_text.strip()!=current['claim_text'] or disposition=='INSUFFICIENT'
        batch['batch_id']='OPERATOR_REVIEW_'+fingerprint({**batch,'expected_version':expected_version})[:20].upper()
        result=ResearchAuditRuntime(RUNTIME_ROOT,production.workspace).run(batch,transition_if_ready=False).to_dict()
        data=project.read();data['storage_status']='PENDING_UPLOAD';atomic_json(project.manifest,data)
    return result

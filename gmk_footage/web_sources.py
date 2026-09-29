from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import html
import json
import re


class WebSourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class WebSourceCandidate:
    provider: str
    media_kind: str
    title: str
    page_url: str
    media_url: str | None
    creator: str
    description: str
    license_text: str | None
    source_priority: str
    provider_rank: int

    def to_dict(self)->dict[str,Any]:
        return {
            'provider':self.provider,'media_kind':self.media_kind,'title':self.title,
            'page_url':self.page_url,'media_url':self.media_url,'creator':self.creator,
            'description':self.description,'license_text':self.license_text,
            'source_priority':self.source_priority,'provider_rank':self.provider_rank,
        }


def _default_json(url:str)->dict[str,Any]:
    req=Request(url,headers={'User-Agent':'GMK-Documentary-Maker/0.2'})
    with urlopen(req,timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))


def _plain(value:Any)->str:
    s=str(value or '')
    s=re.sub(r'<[^>]+>',' ',s)
    return re.sub(r'\s+',' ',html.unescape(s)).strip()


class NasaMediaProvider:
    ENDPOINT='https://images-api.nasa.gov/search'
    def __init__(self,fetch_json:Callable[[str],dict[str,Any]]=_default_json):self.fetch_json=fetch_json
    def search(self,query:str,*,media_type:str='video',limit:int=10)->tuple[WebSourceCandidate,...]:
        if media_type not in {'video','image'}:raise WebSourceError('NASA_MEDIA_TYPE_INVALID')
        url=self.ENDPOINT+'?'+urlencode({'q':query,'media_type':media_type,'page_size':min(max(limit,1),100)})
        data=self.fetch_json(url);items=(((data.get('collection') or {}).get('items')) or [])[:limit];out=[]
        for i,item in enumerate(items,1):
            meta=((item.get('data') or [{}])[0] or {});links=item.get('links') or []
            href=None
            for link in links:
                if link.get('href') and (link.get('render') in {'image','video'} or not href):href=link.get('href')
            nasa_id=str(meta.get('nasa_id') or '').strip();page=f'https://images.nasa.gov/details/{nasa_id}' if nasa_id else str(item.get('href') or '')
            out.append(WebSourceCandidate('NASA',media_type.upper(),_plain(meta.get('title')),page,href,_plain(meta.get('photographer') or meta.get('secondary_creator') or 'NASA'),_plain(meta.get('description')),'NASA media usage guidelines','WEB_VIDEO' if media_type=='video' else 'STILL_DOCUMENT',i))
        return tuple(x for x in out if x.title and x.page_url)


class InternetArchiveProvider:
    ENDPOINT='https://archive.org/advancedsearch.php'
    def __init__(self,fetch_json:Callable[[str],dict[str,Any]]=_default_json):self.fetch_json=fetch_json
    def search(self,query:str,*,limit:int=10)->tuple[WebSourceCandidate,...]:
        params=[('q',f'({query}) AND mediatype:(movies)'),('fl[]','identifier'),('fl[]','title'),('fl[]','creator'),('fl[]','description'),('rows',str(min(max(limit,1),50))),('page','1'),('output','json')]
        url=self.ENDPOINT+'?'+urlencode(params)
        docs=(((self.fetch_json(url).get('response') or {}).get('docs')) or [])[:limit];out=[]
        for i,d in enumerate(docs,1):
            ident=str(d.get('identifier') or '').strip()
            if not ident:continue
            out.append(WebSourceCandidate('INTERNET_ARCHIVE','VIDEO',_plain(d.get('title')),f'https://archive.org/details/{ident}',None,_plain(d.get('creator')),_plain(d.get('description')),None,'WEB_VIDEO',i))
        return tuple(x for x in out if x.title)


class WikimediaStillProvider:
    ENDPOINT='https://commons.wikimedia.org/w/api.php'
    def __init__(self,fetch_json:Callable[[str],dict[str,Any]]=_default_json):self.fetch_json=fetch_json
    def search(self,query:str,*,limit:int=10)->tuple[WebSourceCandidate,...]:
        params={'action':'query','format':'json','generator':'search','gsrsearch':query,'gsrnamespace':'6','gsrlimit':min(max(limit,1),20),'prop':'imageinfo','iiprop':'url|extmetadata'}
        pages=((self.fetch_json(self.ENDPOINT+'?'+urlencode(params)).get('query') or {}).get('pages')) or {}
        rows=sorted(pages.values(),key=lambda x:int(x.get('index',999999)))[:limit];out=[]
        for i,p in enumerate(rows,1):
            info=((p.get('imageinfo') or [{}])[0] or {});ext=info.get('extmetadata') or {}
            def ev(k):return _plain((ext.get(k) or {}).get('value'))
            title=_plain(p.get('title')).removeprefix('File:')
            page='https://commons.wikimedia.org/wiki/'+str(p.get('title') or '').replace(' ','_')
            out.append(WebSourceCandidate('WIKIMEDIA_COMMONS','IMAGE',title,page,info.get('url'),ev('Artist') or ev('Credit'),ev('ImageDescription'),ev('LicenseShortName') or ev('UsageTerms'),'STILL_DOCUMENT',i))
        return tuple(x for x in out if x.title and x.media_url)

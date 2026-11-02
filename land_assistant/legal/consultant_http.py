"""Bounded HTTPS reads, restricted to registered Consultant document paths."""
import asyncio,re,time
from datetime import datetime,timezone
from urllib.parse import urlsplit,urljoin
import httpx
from .consultant_types import DocumentPage,SourceError

def allowed_url(url):
    if not isinstance(url,str) or len(url)>1000:raise SourceError('source_url_rejected')
    parts=urlsplit(url)
    if parts.scheme!='https' or parts.hostname not in ('consultant.ru','www.consultant.ru') or parts.username or parts.password or parts.port not in (None,443) or parts.query or not re.fullmatch(r'/document/cons_doc_LAW_\d+/(?:[a-f0-9]{40}/)?',parts.path):raise SourceError('source_url_rejected')
    return 'https://www.consultant.ru'+parts.path

class ConsultantHTTP:
    def __init__(self,transport=None,pace=1):self.transport=transport;self.pace=pace;self.last_start=0
    async def fetch(self,url,*,budget,conditional_headers=None):
        url=allowed_url(url);budget.require();started=time.monotonic()
        try:
            async with asyncio.timeout(min(25,budget.network_seconds_left,max(.01,budget.deadline-time.monotonic()))):
                async with httpx.AsyncClient(transport=self.transport,follow_redirects=False,trust_env=False,timeout=10) as client:
                    for _ in range(4):
                        budget.require();await asyncio.sleep(max(0,self.pace-(time.monotonic()-self.last_start)))
                        self.last_start=time.monotonic()
                        async with client.stream('GET',url,headers={'User-Agent':'GroundAndLaw/0.1 public legal reference reader',**(conditional_headers or {})}) as response:
                            if response.status_code in (301,302,303,307,308):url=allowed_url(urljoin(url,response.headers.get('location','')));continue
                            if response.status_code==429:budget.rate_limited=True;raise SourceError('source_rate_limit',http_status=429)
                            if response.status_code in (401,403):raise SourceError('source_access_restricted',http_status=response.status_code)
                            if response.status_code not in (200,304):raise SourceError('source_unavailable',http_status=response.status_code)
                            body=bytearray()
                            async for chunk in response.aiter_bytes():
                                body.extend(chunk)
                                if len(body)>2*1024*1024:raise SourceError('source_size_limit')
                            text=bytes(body).decode(response.encoding or 'utf-8',errors='replace')
                            return DocumentPage(url,response.status_code,dict(response.headers),text,datetime.now(timezone.utc).isoformat())
                    raise SourceError('source_redirect_limit')
        except (httpx.HTTPError,TimeoutError) as exc:raise SourceError('source_unavailable') from exc
        finally:budget.network_seconds_left-=time.monotonic()-started

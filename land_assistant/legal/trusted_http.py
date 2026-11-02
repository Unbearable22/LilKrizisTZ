"""Direct bounded HTTPS with DNS-pinned sockets, verified TLS and no proxy env."""
import asyncio
from datetime import datetime,timezone
import http.client
import ipaddress
import socket
import ssl
import time
from urllib.parse import urlsplit,urljoin
from .trusted_sources import FetchedDocument,validate_source_url
from .consultant_types import SourceError

def resolve_public(host):
    addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
    if not addresses:raise SourceError('source_dns_rejected')
    for row in addresses:
        ip=ipaddress.ip_address(row[4][0])
        if not ip.is_global or (ip.version==6 and ip.ipv4_mapped and not ip.ipv4_mapped.is_global):raise SourceError('source_dns_rejected')
    return addresses[0][4][0]

class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self,host,ip,timeout):
        super().__init__(host,timeout=timeout);self.pinned_ip=ip
    def connect(self):
        sock=socket.create_connection((self.pinned_ip,443),self.timeout)
        try:self.sock=ssl.create_default_context().wrap_socket(sock,server_hostname=self.host)
        except BaseException:sock.close();raise

def request_once(url,ip,timeout):
    p=urlsplit(url);conn=PinnedHTTPS(p.hostname,ip,timeout)
    try:
        headers={'User-Agent':'GroundAndLaw/0.2 verified public document reader','Accept-Encoding':'identity'}
        if p.path=='/search/':headers['X-Requested-With']='XMLHttpRequest'
        conn.request('GET',p.path+('?' + p.query if p.query else ''),headers=headers)
        r=conn.getresponse();headers={k.lower():v for k,v in r.getheaders()}
        limit=8*1024*1024 if headers.get('content-type','').split(';')[0]=='application/pdf' else 2*1024*1024
        data=bytearray();end=time.monotonic()+timeout
        while True:
            if time.monotonic()>=end:raise SourceError('source_budget_exhausted')
            chunk=r.read(min(65536,limit+1-len(data)))
            if not chunk:break
            data.extend(chunk)
            if len(data)>limit:raise SourceError('source_size_limit')
        return r.status,headers,bytes(data)
    finally:conn.close()

async def fetch_document(url: str, *, deadline: float, discovery: bool=False) -> FetchedDocument:
    for _ in range(4):
        if discovery:
            from .web_discovery import validate_search_url
            validate_search_url(url)
        else:validate_source_url(url)
        remaining=min(10,deadline-time.monotonic())
        if remaining<=0:raise SourceError('source_budget_exhausted')
        try:
            ip=await asyncio.wait_for(asyncio.to_thread(resolve_public,urlsplit(url).hostname),remaining)
            remaining=min(10,deadline-time.monotonic())
            if remaining<=0:raise SourceError('source_budget_exhausted')
            status,headers,body=await asyncio.wait_for(asyncio.to_thread(request_once,url,ip,remaining),remaining)
        except (OSError,TimeoutError,http.client.HTTPException) as exc:raise SourceError('source_unavailable') from exc
        if status in (301,302,303,307,308):
            location=headers.get('location')
            if not location:raise SourceError('source_url_rejected')
            url=urljoin(url,location);continue
        if status==429:raise SourceError('source_rate_limit',http_status=429)
        if status in (401,403):raise SourceError('source_access_restricted',http_status=status)
        if status!=200:raise SourceError('source_unavailable',http_status=status)
        return FetchedDocument(url,headers.get('content-type','').split(';')[0],body,datetime.now(timezone.utc).isoformat())
    raise SourceError('source_redirect_limit')

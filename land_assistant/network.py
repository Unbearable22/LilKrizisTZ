import ipaddress
import http.client
import json
import socket
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urljoin

MAX_DOWNLOAD = 12 * 1024 * 1024

def resolve_public_url(url):
    p = urlsplit(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None,443):
        raise ValueError('Источник должен быть публичным HTTPS URL без учётных данных.')
    try:
        addresses = socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError('Не удалось разрешить адрес источника.') from exc
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Доступ к внутренним адресам запрещён.')
    return p,addresses[0][4][0]

def validate_public_url(url):
    resolve_public_url(url)
    return url

class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self,hostname,address):
        super().__init__(hostname,timeout=30)
        self.address=address
    def connect(self):
        # Pin the validated IP, retain TLS certificate and hostname verification.
        # A second DNS resolution must not enable rebinding to an internal host.
        self.sock=socket.create_connection((self.address,443),self.timeout)
        try:
            self.sock=self._context.wrap_socket(self.sock,server_hostname=self.host)
        except Exception:
            self.sock.close()
            raise

def fetch_public(url):
    for _ in range(6):
        p,address=resolve_public_url(url)
        connection=PinnedHTTPSConnection(p.hostname,address)
        try:
            target=(p.path or '/')+('?' + p.query if p.query else '')
            connection.request('GET',target,headers={'User-Agent':'ZemlyaPravoMonitor/0.1','Accept-Encoding':'identity'})
            response=connection.getresponse()
            if response.status in (301,302,303,307,308):
                location=response.getheader('Location')
                if not location:
                    raise ValueError('Перенаправление не содержит адреса.')
                url=urljoin(url,location)
                continue
            if response.status!=200:
                raise ValueError(f'Источник вернул HTTP {response.status}.')
            data=response.read(MAX_DOWNLOAD+1)
            if len(data)>MAX_DOWNLOAD:
                raise ValueError('Источник превышает 12 МБ.')
            return data,response.getheader('Content-Type',''),response.headers.get_content_charset() or 'utf-8'
        finally:
            connection.close()
    raise ValueError('Слишком много перенаправлений источника.')

def request_json(url, payload=None, key='', timeout=45):
    headers = {'Content-Type':'application/json'}
    if key:
        headers['Authorization'] = 'Bearer '+key
    req = urllib.request.Request(url, data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
    # URL is operator-configured, supporting a local model and local NSPD adapter.
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:
            data = response.read(MAX_DOWNLOAD+1)
            if len(data)>MAX_DOWNLOAD:
                raise ValueError('Ответ API превышает лимит.')
            return json.loads(data)
    except urllib.error.URLError as exc:
        raise ValueError('Внешний API недоступен. Проверьте конфигурацию и доступ.') from exc

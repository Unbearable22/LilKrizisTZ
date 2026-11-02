"""Explicit source policy. Being on a government domain is not sufficient."""
from dataclasses import dataclass
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from .consultant_types import SourceError

@dataclass(frozen=True)
class SourcePolicy:
    publisher: str
    source_kind: str
    adapter: str

@dataclass(frozen=True)
class FetchedDocument:
    final_url: str
    content_type: str
    body: bytes
    fetched_at: str

def validate_source_url(url: str) -> SourcePolicy:
    try:
        if not isinstance(url,str) or len(url)>1000 or any(ord(c)<33 for c in url):raise ValueError()
        p=urlsplit(url)
        if p.scheme!='https' or p.username or p.password or p.port not in (None,443) or p.query or p.fragment or '%' in p.path:raise ValueError()
        registry=json.loads((Path(__file__).resolve().parents[2]/'knowledge/trusted_sources.json').read_text())
        for row in registry['sources']:
            if p.hostname in row['hosts'] and re.fullmatch(row['path'],p.path):return SourcePolicy(row['publisher'],row['source_kind'],row['adapter'])
    except (ValueError,TypeError):pass
    raise SourceError('source_url_rejected')

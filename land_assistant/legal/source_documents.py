"""Document identity and extraction. Retrieval time never proves legal force."""
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
import io
from .trusted_sources import validate_source_url
from .consultant_types import DocumentPage,SourceError

@dataclass
class VerifiedDocument:
    url: str
    title: str
    publisher: str
    source_kind: str
    applicability: str
    revision: str
    checked_at: str
    fragments: list[dict]

def extract_document(fetched,policy):
    validate_source_url(fetched.final_url)
    day=datetime.fromisoformat(fetched.fetched_at).astimezone(ZoneInfo('Europe/Moscow')).date().isoformat()
    if fetched.content_type=='application/pdf':
        try:
            from pypdf import PdfReader
            reader=PdfReader(io.BytesIO(fetched.body))
            if reader.is_encrypted or len(reader.pages)>30:raise SourceError('source_unreadable')
            parts=[{'text':page.extract_text() or '', 'citation':f'Страница {i+1}'} for i,page in enumerate(reader.pages)]
            if not parts or any(len(p['text'].strip())<30 for p in parts):raise SourceError('source_unreadable')
            # No connected PDF source policy yet: extracted text is not proof of edition.
            raise SourceError('source_edition_unknown')
        except SourceError:raise
        except Exception as exc:raise SourceError('source_unreadable') from exc
    if fetched.content_type not in ('text/html','application/xhtml+xml'):raise SourceError('source_unreadable')
    try:text=fetched.body.decode('utf-8',errors='strict')
    except UnicodeError:raise SourceError('source_unreadable') from None
    if policy.adapter=='fns_sale':
        from .public_sources import parse_fns,FNS_TITLE
        body=parse_fns(text,day)
        return VerifiedDocument(fetched.final_url,FNS_TITLE,policy.publisher,policy.source_kind,'guidance','Дата редакции нормы не установлена',fetched.fetched_at,[{'text':body,'citation':'Официальное разъяснение, не нормативный акт'}])
    from .consultant_parser import parse_document
    parsed=parse_document(DocumentPage(fetched.final_url,200,{},text,fetched.fetched_at),as_of_date=day)
    if not parsed['normative_headings']:raise SourceError('source_parse_error')
    return VerifiedDocument(fetched.final_url,parsed['title'],policy.publisher,policy.source_kind,'current',parsed['edition_label'],fetched.fetched_at,[{'text':parsed['text'],'citation':parsed['normative_headings'][0]}])

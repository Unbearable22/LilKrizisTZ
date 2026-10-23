"""Keep evidence private while preserving internal grounding checks."""
import re

REFERENCE_PATTERN = re.compile(
    r'№\s*\d|(?:постановлен\w*|приказ\w*|распоряжен\w*|указ\w*)\s+(?:Правительств\w*|Мин\w*|Президент\w*|[«"])|'
    r'https?://|www\.|consultant\.ru|garant\.ru|pravo\.gov\.ru|'
    r'\b(?:ЗК|ГрК|ГПК|ГК|ТК|СК|ЖК|НК|УК|УПК|АПК|КАС|КоАП)\s*РФ\b|'
    r'\b(?:земельн\w*|градостроительн\w*|трудов\w*|семейн\w*|жилищн\w*|налогов\w*|уголовн\w*|арбитражн\w*|гражданск\w*(?:\s+процессуальн\w*)?)\s+кодекс\w*|'
    r'\b(?:пункт\w*|подпункт\w*|часть|части|п\.)\s*\d|'
    r'закон\w*\s+(?:[«"]|от\s+\d|№\s*\d|(?:о|об|РФ|Российск\w*)\b)|'
    r'\b(?:статья|статьи|статье|статью|статей|ст\.)\s*\d|'
    r'(?:№\s*)?\b\d+\s*[-‑–]\s*ФЗ\b|'
    r'\[[^\]\n]{1,100}\]|【[^】]+】|'
    r'\b[a-z0-9_-]{1,60}:[a-f0-9]{16}:\d+\b|'
    r'(?:источники|нормативные основания)\s*:|'
    r'КонсультантПлюс|\bГАРАНТ\b', re.IGNORECASE,
)


CODE_PATTERN=r'\b(?:(?:ЗК|ГрК|ГПК|ГК|ТК|СК|ЖК|НК|УК|УПК|АПК|КАС|КоАП)\s*РФ|(?:земельн\w*|градостроительн\w*|трудов\w*|семейн\w*|жилищн\w*|налогов\w*|уголовно[- ]процессуальн\w*|уголовн\w*|(?:арбитражн\w*|гражданск\w*)(?:\s+процессуальн\w*)?)\s+кодекс\w*(?:\s+Российской\s+Федерации|\s+РФ)?|кодекс\w*(?:\s+Российск\w*\s+Федерац\w*|\s+РФ)?\s+(?:об\s+административн\w*\s+правонарушен\w*|административн\w*\s+судопроизводств\w*))'
REFERENCE_PATTERN=re.compile(REFERENCE_PATTERN.pattern+'|'+CODE_PATTERN,re.I)
def code_family(text):
    text=text.casefold()
    abbreviations={'зк':'land','грк':'urban','гпк':'civil_procedure','гк':'civil','тк':'labor','ск':'family','жк':'housing','нк':'tax','ук':'criminal','упк':'criminal_procedure','апк':'arbitration','кас':'administrative_procedure','коап':'offenses'}
    for abbreviation,family in abbreviations.items():
        if re.search(r'\b'+abbreviation+r'\s*рф\b',text):return family
    if 'правонарушен' in text:return 'offenses'
    if 'судопроизводств' in text:return 'administrative_procedure'
    if 'арбитражн' in text:return 'arbitration'
    for marker,family in [('гражданск','civil'),('уголовн','criminal')]:
        if marker in text:return family+('_procedure' if 'процессуальн' in text else '')
    for marker,family in [('земельн','land'),('градостроительн','urban'),('трудов','labor'),('семейн','family'),('жилищн','housing'),('налогов','tax')]:
        if marker in text:return family
    return None


def has_references(text, fragments=()):
    if not isinstance(text, str):return True
    if REFERENCE_PATTERN.search(text):return True
    folded=text.casefold()
    for fragment in fragments:
        for key in ('id','source_url','title'):
            value=fragment.get(key,'').split(' — часть')[0]
            if value and value.casefold() in folded:return True
    return False


def public_result(result):
    """Explicit boundary: future internal metadata cannot leak by default."""
    return {key:result[key] for key in ('status','answer','missing_fields','limitations','mode','chat_id','legal_bases','source_checked_at','task_outcomes') if key in result}


def has_unverified_references(text, fragments=()):
    """Allow named acts/articles from selected, read evidence; keep IDs/URLs private."""
    if not isinstance(text,str):return True
    remaining=text
    if any(f.get('id') and f['id'] in text for f in fragments):return True
    for f in fragments:
        title=f.get('title','').split(' — часть')[0]
        if title:remaining=re.sub(re.escape(title),' ',remaining,flags=re.I)
    code_pattern=CODE_PATTERN
    def code(match):
        family=code_family(match.group())
        return ' ' if family and any(code_family(f.get('title',''))==family for f in fragments) else match.group()
    remaining=re.sub(code_pattern,code,remaining,flags=re.I)
    articles={m.group(1) for f in fragments if (m:=re.search(r'(?:Статья|ст\.)\s*(\d+(?:\.\d+)*)',f.get('citation',''),re.I))}
    remaining=re.sub(r'\b(?:статья|статьи|статье|статью|статей|ст\.)\s*(\d+(?:\.\d+)*)',lambda m:' ' if m.group(1) in articles else m.group(),remaining,flags=re.I)
    numbers={m.group(1) for f in fragments for m in re.finditer(r'(\d+)\s*[-‑–]\s*ФЗ',f.get('act_designation','')+' '+f.get('title',''),re.I)}
    remaining=re.sub(r'(?:№\s*)?\b(\d+)\s*[-‑–]\s*ФЗ\b',lambda m:' ' if m.group(1) in numbers else m.group(),remaining,flags=re.I)
    return has_references(remaining)

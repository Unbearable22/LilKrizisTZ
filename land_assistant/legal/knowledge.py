import hashlib
import json
import math
from collections import Counter
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

STOP={'как','что','это','для','или','при','мне','его','она','нужно','можно','пожалуйста','какие','какой','каков','обычно','общий','общая','справка','объясните','вопрос','имеют','сведения','содержит'}
SUFFIX=re.compile(r'(ами|ями|ого|ему|ому|ыми|ими|иях|ий|ый|ой|ая|яя|ое|ее|ые|ие|ов|ев|ам|ям|ах|ях|ом|ем|а|я|ы|и|у|ю|е|о)$')


def tokens(text):
    result=[]
    for word in re.findall(r'[а-яёa-z0-9]{3,}',text.lower().replace('ё','е')):
        if word in STOP:continue
        if re.fullmatch(r'участ(?:ок|к[а-я]*)',word):word='участок'
        elif len(word)>4 and re.fullmatch(r'[а-я]+',word):word=SUFFIX.sub('',word)
        result.append(word[:6] if len(word)>6 else word)
    return result


def terms(text):return set(tokens(text))


class Knowledge:
    def __init__(self,root,demo=False):
        self.root=Path(root).resolve(strict=True)
        self.demo=demo

    def _text(self,directory,name,suffix):
        base=self.root/directory
        if not isinstance(name,str) or Path(name).name!=name or not name.endswith(suffix):
            raise ValueError('Недопустимый путь нормативного файла.')
        path=base/name
        resolved=path.resolve(strict=True)
        if not resolved.is_relative_to(base.resolve()) or base.is_symlink() or resolved!=path.absolute():
            raise ValueError('Ссылки за пределы нормативного каталога запрещены.')
        if resolved.stat().st_size>1024*1024:
            raise ValueError('Нормативный файл превышает 1 МиБ.')
        return resolved.read_text(encoding='utf-8')

    def prompt(self):
        text=self._text('prompts','legal_help.txt','.txt').strip()
        if not text or len(text)>20000:raise ValueError('Мастер-промпт отсутствует или превышает лимит.')
        return text

    def _fragments(self):
        manifest=json.loads(self._text('laws','manifest.json','.json'))
        docs=manifest.get('documents')
        if not isinstance(docs,list) or len(docs)>100:raise ValueError('Некорректный реестр источников.')
        today=datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat()
        fragments=[];seen=set()
        for doc in docs:
            did=doc.get('id','')
            if not isinstance(did,str) or not re.fullmatch(r'[a-z0-9_-]{1,60}',did) or did in seen:raise ValueError('Некорректный или повторный ID документа.')
            seen.add(did)
            # Validate paths even for nonactive records: configuration must not hide unsafe references.
            text=self._text('laws',doc['path'],'.md')
            if not self.demo and doc.get('demo',True):continue
            if not doc.get('verified_by') or not doc.get('valid_until') or doc['valid_until']<today:continue
            if doc.get('effective_from',today)>today:continue
            if not all(isinstance(doc.get(k),str) and doc[k] for k in ('title','version','source_url')):raise ValueError('У источника отсутствуют реквизиты.')
            if urlsplit(doc['source_url']).scheme!='https':raise ValueError('Источник требует HTTPS-ссылку.')
            digest=hashlib.sha256(text.encode()).hexdigest()
            if doc.get('sha256') and doc['sha256']!=digest:raise ValueError('Содержимое документа изменено после проверки.')
            designation=re.search(r'(?m)^(\d+[-‑–]ФЗ от \d{2}\.\d{2}\.\d{4})',text)
            act_designation=designation.group(1) if designation else ''
            parts=re.split(r'(?m)^(#{1,6} .+)$',text)
            heading=doc['title'];index=0
            for part in parts:
                if part.startswith('#') and '\n' not in part:
                    heading=part.lstrip('# ').strip();continue
                if not part.strip():continue
                # Chunk is explicitly a fragment, never represented as the complete article.
                paragraphs=re.split(r'\n\s*\n',part.strip())
                pieces=[];current=''
                for paragraph in paragraphs:
                    for start in range(0,len(paragraph),3800):
                        piece=paragraph[start:start+3800]
                        if len(current)+len(piece)+2>4000 and current:pieces.append(current);current=''
                        current=(current+'\n\n'+piece).strip()
                if current:pieces.append(current)
                for piece in pieces:
                    fragments.append({'id':f'{did}:{digest[:16]}:{index}','document_id':did,'act_designation':act_designation,'title':doc['title'],'version':doc['version'],'citation':heading,'source_url':doc['source_url'],'sha256':digest,'demo':bool(doc.get('demo',True)),'text':piece,'partial':len(pieces)>1})
                    index+=1
        return fragments

    def search(self,query):
        if not isinstance(query,str) or not query.strip() or len(query)>8000:raise ValueError('Некорректный поисковый запрос.')
        words=terms(query)
        # A small legal vocabulary expands intent, never supplies an answer or law ID.
        facets=set();folded=query.lower().replace('ё','е')
        if re.search(r'\bснт\b',folded):
            folded=re.sub(r'\bснт\b','товарищество',folded)
            words|=terms('товарищество')
        if 'товарищ' in folded and re.search(r'документ|ознаком|копи',folded) and re.search(r'вправ|прав[ао]|член|ознаком|копи',folded):
            facets=terms('права обязанности члена товарищества')
        if 'товарищ' in folded and re.search(r'не.{0,25}(?:вступ|член)|без.{0,15}(?:участи|член)',folded):
            facets=terms('ведение садоводства без участия членства товариществе')
        if re.search(r'\b(?:строит\w*|постро\w*|реконструк\w*)',folded):
            facets|=terms('строительство разрешение')
            if re.search(r'жил|дом|ижс',folded):facets|=terms('уведомление индивидуального жилого дома')
        if re.search(r'сосед|смещен|передвин',folded) and re.search(r'забор|границ|заня|захват',folded):
            facets|=terms('восстановление положения нарушение права самовольное занятие земельные споры')
        words|=facets
        fragments=self._fragments()
        bags=[Counter(tokens(f['text'])) for f in fragments]
        headings=[terms(f['citation']) for f in fragments]
        titles=[terms(f['title']) for f in fragments]
        frequencies=Counter(word for bag,heading,title in zip(bags,headings,titles) for word in set(bag)|heading|title)
        average=sum(sum(b.values()) for b in bags)/max(1,len(bags))
        ranked=[]
        for fragment,bag,heading,title in zip(fragments,bags,headings,titles):
            score=0.0;length=sum(bag.values())
            for word in words:
                if word not in bag and word not in heading and word not in title:continue
                weight=math.log(1+(len(fragments)-frequencies[word]+.5)/(frequencies[word]+.5))
                count=bag[word]
                score+=weight*(count*2.2/(count+1.2*(.25+.75*length/max(1,average))) if count else 0)
                if word in heading:score+=(8 if word in facets else 4)*weight
                if word in title:score+=1.5*weight
            if score:ranked.append((score,fragment))
        ranked.sort(key=lambda pair:(-pair[0],pair[1]['id']))
        # Select articles before chunks: otherwise a repeated phrase in the middle
        # crowds out the start of the same procedure. Keep full chunks and a hard cap.
        groups={}
        for score,fragment in ranked:
            key=(fragment['document_id'],fragment['citation'])
            groups.setdefault(key,[]).append((score,fragment))
        selected=[]
        for key,hits in groups.items():
            article=[f for f in fragments if (f['document_id'],f['citation'])==key]
            quota=min(4 if not selected else 6-len(selected),len(article))
            if quota<=0:break
            chosen=article[:min(2,quota)]
            for _,fragment in hits:
                if len(chosen)>=quota:break
                if fragment not in chosen:chosen.append(fragment)
            # Original order makes temporal conditions and exceptions intelligible.
            chosen.sort(key=lambda f:int(f['id'].rsplit(':',1)[1]))
            selected.extend(chosen)
            if len(selected)>=6:break
        return [{k:v for k,v in f.items() if k!='text'} for f in selected]

    def read(self,fragment_id):
        if not isinstance(fragment_id,str) or not re.fullmatch(r'[a-z0-9_-]{1,60}:[a-f0-9]{16}:\d{1,5}',fragment_id):
            raise ValueError('Недопустимый ID фрагмента.')
        for fragment in self._fragments():
            if fragment['id']==fragment_id:return fragment
        raise ValueError('Фрагмент отсутствует, изменён или неактуален.')

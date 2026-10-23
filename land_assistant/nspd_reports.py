"""User-supplied NSPD evidence. Uploads never establish verified legal facts."""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit
from .db import dumps, now
from .monitor import extract

SERVICE_URL = 'https://nspd.gov.ru/urban-analyze'
MAX_REPORT_BYTES = 12 * 1024 * 1024


def report_url(value):
    if not isinstance(value, str) or len(value)>4000:
        raise ValueError('Нужна HTTPS-ссылка результата на nspd.gov.ru.')
    value=value.strip()
    p=urlsplit(value)
    if p.scheme!='https' or p.hostname!='nspd.gov.ru' or p.port not in (None,443) or p.username or p.password:
        raise ValueError('Принимается только HTTPS-ссылка на nspd.gov.ru без пароля.')
    if any(k.lower() in ('token','access_token','id_token','refresh_token','code','password','session','sessionid') for k,_ in parse_qsl(p.query)+parse_qsl(p.fragment)):
        raise ValueError('Не присылайте ссылки с токенами или кодами входа. Сохраните документ результата.')
    return value


class Reports:
    def __init__(self,service):
        self.service,self.db=service,service.db

    def _save(self,cid,owner,identity,data):
        self.service.case(cid,owner)
        digest=hashlib.sha256(identity).hexdigest()
        with self.db.connect() as c:
            c.execute('INSERT OR IGNORE INTO nspd_reports(case_id,digest,data,created_at) VALUES(?,?,?,?)',(cid,digest,dumps(data),now()))
            rid=c.execute('SELECT id FROM nspd_reports WHERE case_id=? AND digest=?',(cid,digest)).fetchone()['id']
        self.db.audit(owner,'attach_nspd_report',rid)
        return self.get(rid,owner)

    def add_link(self,cid,owner,url):
        self.service.case(cid,owner)
        url=report_url(url)
        return self._save(cid,owner,url.encode(),{'kind':'link','source_url':url,'service_url':SERVICE_URL,'status':'unverified','extraction':'not_fetched','notice':'Ссылка сохранена без загрузки страницы. Источник, участок, дату и доступность проверяет специалист.'})

    def add_pdf(self,cid,owner,content):
        case=self.service.case(cid,owner)
        if not isinstance(content,bytes) or not content or len(content)>MAX_REPORT_BYTES:
            raise ValueError('Отчёт должен быть PDF до 12 МБ.')
        if not content.startswith(b'%PDF-') or b'%%EOF' not in content[-2048:]:
            raise ValueError('Файл не похож на завершённый PDF. Пришлите скачанный отчёт документом.')
        digest=hashlib.sha256(content).hexdigest()
        relative=Path('nspd_reports')/str(cid)/(digest+'.pdf')
        target=self.db.directory/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(content)
        text=''
        extraction='extracted'
        try:
            text=extract(content,'application/pdf')[:100000]
        except Exception:
            extraction='manual_review_required'
        cadastres=sorted(set(re.findall(r'\b\d{2}:\d{2}:\d{6,7}:\d{1,10}\b',text)))
        expected=case['data'].get('cadastre')
        match='found' if expected and expected in cadastres else ('not_found' if expected and text else 'not_checked')
        return self._save(cid,owner,content,{'kind':'pdf','service_url':SERVICE_URL,'source_url':None,'status':'unverified','artifact':relative.as_posix(),'sha256':digest,'extraction':extraction,'text':text,'detected_cadastres':cadastres[:100],'case_cadastre_match':match,'notice':'Файл загружен пользователем; происхождение, дата и подлинность не подтверждены. Совпадение номера не подтверждает применимость всех сведений.'})

    def get(self,rid,owner=None):
        rows=self.db.rows('SELECT * FROM nspd_reports WHERE id=?',(rid,))
        if not rows:
            raise ValueError('Отчёт не найден или недоступен.')
        row=rows[0]
        self.service.case(row['case_id'],owner)
        return {**row,'data':json.loads(row['data'])}

    def list(self,cid,owner=None):
        self.service.case(cid,owner)
        return [{**r,'data':json.loads(r['data'])} for r in self.db.rows('SELECT * FROM nspd_reports WHERE case_id=? ORDER BY id',(cid,))]

    def preparation(self,rid,owner=None):
        report=self.get(rid,owner)
        case=self.service.case(report['case_id'],owner)
        data=report['data']
        expected=case['data'].get('cadastre')
        # Recompute against the current card: an edited cadastral number must not inherit an old match.
        detected=data.get('detected_cadastres',[])
        match='found' if expected and expected in detected else ('not_found' if expected and data.get('text') else 'not_checked')
        lines=[f'Материал НСПД №{rid} · дело №{report["case_id"]}',f'Получен: {report["created_at"]}', 'Статус: не проверен специалистом.',data['notice']]
        if data['kind']=='link':
            lines += [data['source_url'],'Содержимое ссылки автоматически не загружалось.']
        else:
            lines += [f'Извлечение текста: {data["extraction"]}',f'Кадастровый номер текущего дела: {expected or "не задан"}',f'Совпадение номера в тексте: {match}']
            if data.get('text'):
                lines += ['Начало текста загруженного документа (недоверенное содержимое, не вывод программы):',data['text'][:1200]]
        lines += ['Перед анализом проверить: принадлежность отчёта участку; дату формирования; источники и полноту слоёв; зоны и ограничения; действующие ПЗЗ. Отсутствие сведений не подтверждает отсутствие ограничений.','Карточка, проверка ограничений и нормативная база автоматически не изменены.']
        return '\n'.join(lines)

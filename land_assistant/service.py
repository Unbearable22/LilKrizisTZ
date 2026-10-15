import json
import math
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo
from .db import dumps, now
from .geometry import polygon, covers, area

CADASTRE = re.compile(r'^\d{2}:\d{2}:\d{6,7}:\d{1,10}$')
NUMBERS = ('area_m2','building_area_m2','floor_area_m2','height_m')
PURPOSES = {'housing':'Жилая недвижимость', 'commercial':'Коммерческая недвижимость', 'agriculture':'Сельское хозяйство'}

def required_text(value, name, limit=2000):
    if not isinstance(value,str) or not value.strip() or len(value)>limit:
        raise ValueError(f'Поле {name}: непустой текст до {limit} символов.')
    return value.strip()

def positive(value, name, zero=False):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value < 0 or (not zero and value == 0):
        raise ValueError(f'Поле {name}: положительное конечное число.')
    return value

class Service:
    def __init__(self, db):
        self.db = db

    def import_municipality(self, payload, actor='admin'):
        mid = required_text(payload.get('id'),'id',100)
        name = required_text(payload.get('name'),'name',300)
        boundary = polygon(payload['boundary']) if payload.get('boundary') else None
        source = payload.get('source_url')
        verified = payload.get('verified_at')
        if boundary and (not source or not verified):
            raise ValueError('Граница требует source_url и verified_at.')
        if verified:
            date.fromisoformat(verified)
        self.db.execute('INSERT INTO municipalities VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,boundary=excluded.boundary,source_url=excluded.source_url,verified_at=excluded.verified_at', (mid,name,dumps(boundary) if boundary else None,source,verified))
        self.db.audit(actor,'import_municipality',mid)
        return mid

    def import_rule(self, payload, actor='admin'):
        p = dict(payload)
        for k in ('municipality_id','zone','version','source_url','citation','effective_from','valid_until'):
            required_text(p.get(k),k)
        if not self.db.rows('SELECT id FROM municipalities WHERE id=?',(p['municipality_id'],)):
            raise ValueError('Сначала импортируйте муниципалитет.')
        start,end = date.fromisoformat(p['effective_from']),date.fromisoformat(p['valid_until'])
        if end < start:
            raise ValueError('valid_until раньше effective_from.')
        if not isinstance(p.get('allowed_uses'),list) or not p['allowed_uses'] or any(not isinstance(x,str) for x in p['allowed_uses']):
            raise ValueError('allowed_uses: непустой список кодов ВРИ.')
        if any(k not in p for k in ('min_area_m2','max_area_m2','max_coverage_pct','max_density','setback_m','max_height_m')):
            raise ValueError('Нужны все числовые ограничения; null означает неизвестное ограничение.')
        for k in ('min_area_m2','max_area_m2','max_coverage_pct','max_density','setback_m','max_height_m'):
            if p[k] is not None:
                positive(p[k],k,zero=True)
        if p['max_coverage_pct'] is not None and p['max_coverage_pct'] > 100:
            raise ValueError('Процент застройки не может превышать 100.')
        if p['min_area_m2'] is not None and p['max_area_m2'] is not None and p['min_area_m2'] > p['max_area_m2']:
            raise ValueError('Минимальная площадь больше максимальной.')
        verified = bool(p.get('verified_by'))
        with self.db.connect() as c:
            if verified:
                c.execute('UPDATE rules SET active=0 WHERE municipality_id=? AND zone=?',(p['municipality_id'],p['zone']))
            rid = c.execute('INSERT INTO rules(municipality_id,zone,version,data,verified_by,verified_at,active) VALUES(?,?,?,?,?,?,?)',(p['municipality_id'],p['zone'],p['version'],dumps(p),p.get('verified_by'),now() if verified else None,int(verified))).lastrowid
        self.db.audit(actor,'import_rule',rid)
        return rid

    def validate_case(self, payload):
        allowed = {'client','address','cadastre','purpose','use_code','municipality_id','zone','coordinates','area_m2','building_area_m2','floor_area_m2','height_m','setback_m','ownership','restrictions_checked','restrictions','nspd_evidence','zone_source','zone_verified_by','category','utilities','preferences'}
        if not isinstance(payload,dict) or set(payload)-allowed:
            raise ValueError('Неизвестные поля карточки участка.')
        p = dict(payload)
        p['client'] = required_text(p.get('client'),'client',300)
        p['address'] = required_text(p.get('address'),'address',1000)
        for key in ('cadastre','use_code','municipality_id','zone','ownership','nspd_evidence','zone_source','zone_verified_by','category','preferences'):
            if key in p and p[key] is not None and not isinstance(p[key],str):
                raise ValueError(f'Поле {key} должно быть строкой.')
            if isinstance(p.get(key),str) and len(p[key])>2000:
                raise ValueError(f'Поле {key} превышает 2000 символов.')
        if 'utilities' in p and not isinstance(p['utilities'],dict):
            raise ValueError('utilities: объект с подтверждёнными исходными данными коммуникаций.')
        if p.get('cadastre') and not CADASTRE.fullmatch(p['cadastre']):
            raise ValueError('Кадастровый номер: 90:12:172201:102; для образуемого участка поле можно не заполнять.')
        if p.get('purpose') not in PURPOSES:
            raise ValueError('purpose: housing, commercial или agriculture.')
        for k in NUMBERS:
            if k in p:
                positive(p[k],k)
        if 'setback_m' in p:
            positive(p['setback_m'],'setback_m',zero=True)
        if 'restrictions_checked' in p and not isinstance(p['restrictions_checked'],bool):
            raise ValueError('restrictions_checked: true/false.')
        if 'restrictions' in p and (not isinstance(p['restrictions'],list) or any(not isinstance(x,str) for x in p['restrictions'])):
            raise ValueError('restrictions: список описаний ограничений.')
        if p.get('coordinates'):
            p['coordinates'] = polygon(p['coordinates'])
            matches = [m['id'] for m in self.db.rows('SELECT * FROM municipalities WHERE boundary IS NOT NULL') if covers(json.loads(m['boundary']),p['coordinates'])]
            if len(matches)==1:
                if p.get('municipality_id') and p['municipality_id'] != matches[0]:
                    raise ValueError('Заданный муниципалитет не совпадает с проверенной границей.')
                p['municipality_id'] = matches[0]
                p['municipality_resolution'] = 'boundary'
            else:
                p['municipality_resolution'] = 'ambiguous' if len(matches)>1 else 'unresolved'
            p['approximate_area_m2'] = round(area(p['coordinates']),2)
        else:
            p['municipality_resolution'] = 'manual_unverified'
        return p

    def create_case(self, owner, payload):
        p = self.validate_case(payload)
        cid = self.db.execute('INSERT INTO cases(owner_id,data,created_at,updated_at) VALUES(?,?,?,?)',(owner,dumps(p),now(),now()))
        self.db.audit(owner,'create_case',cid)
        return cid

    def update_case(self, cid, owner, patch):
        case = self.case(cid,owner)
        base = {k:v for k,v in case['data'].items() if k not in ('municipality_resolution','approximate_area_m2')}
        p = self.validate_case({**base,**patch})
        self.db.execute('UPDATE cases SET data=?,updated_at=? WHERE id=? AND owner_id=?',(dumps(p),now(),cid,owner))
        self.db.audit(owner,'update_case',cid)
        return cid

    def case(self, cid, owner=None):
        args = (cid,) if owner is None else (cid,owner)
        rows = self.db.rows('SELECT * FROM cases WHERE id=?' + ('' if owner is None else ' AND owner_id=?'),args)
        if not rows:
            raise ValueError('Участок не найден или недоступен.')
        return {**rows[0], 'data':json.loads(rows[0]['data'])}

    def cases(self, owner):
        return [{**r,'data':json.loads(r['data'])} for r in self.db.rows('SELECT * FROM cases WHERE owner_id=? ORDER BY id DESC',(owner,))]

    def analyze(self, cid, owner=None):
        case = self.case(cid,owner)
        original = case['data']
        p = self.validate_case({k:v for k,v in original.items() if k not in ('municipality_resolution','approximate_area_m2')})
        missing, failures, checks, citations = [],[],[],[]
        for k,title in {'coordinates':'Координаты WGS84','area_m2':'Площадь по исходному документу','use_code':'Код ВРИ','zone':'Территориальная зона','ownership':'Право на участок','category':'Категория земель'}.items():
            if not p.get(k):
                missing.append(title)
        if p.get('municipality_resolution') != 'boundary':
            missing.append('Однозначное определение муниципалитета по проверенной границе')
        if not p.get('zone_source') or not p.get('zone_verified_by'):
            missing.append('Источник и подтверждение специалистом территориальной зоны')
        if not p.get('restrictions_checked') or not p.get('nspd_evidence'):
            missing.append('Проверка ограничений и документ-основание (НСПД/ЕГРН/ЗОУИТ)')
        if p.get('restrictions'):
            missing.append('Оценка специалистом выявленных ограничений: '+ '; '.join(p['restrictions']))
        rows = self.db.rows('SELECT * FROM rules WHERE municipality_id=? AND zone=? AND active=1 AND verified_by IS NOT NULL ORDER BY id DESC LIMIT 1',(p.get('municipality_id'),p.get('zone')))
        rule = json.loads(rows[0]['data']) if rows else None
        if not rule:
            missing.append('Проверенная действующая редакция ПЗЗ для муниципалитета и зоны')
        elif not rule['effective_from'] <= datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat() <= rule['valid_until']:
            missing.append('Актуализация редакции ПЗЗ: вне подтверждённого срока действия')
        else:
            citations.append({'rule_id':rows[0]['id'],'version':rule['version'],'url':rule['source_url'],'citation':rule['citation'],'verified_by':rows[0]['verified_by'],'verified_at':rows[0]['verified_at']})
            if p.get('use_code'):
                ok = p['use_code'] in rule['allowed_uses']
                checks.append({'parameter':'ВРИ','actual':p['use_code'],'allowed':rule['allowed_uses'],'ok':ok})
                if not ok:
                    failures.append('Запрошенный ВРИ отсутствует в перечне основных разрешённых видов; требуется проверка условно разрешённых видов или изменения ПЗЗ.')
            def compare(label, field, limit, direction):
                if rule.get(limit) is None:
                    missing.append('Норматив: '+label)
                elif field not in p:
                    missing.append('Параметр проекта: '+label)
                else:
                    ok = p[field] <= rule[limit] if direction=='max' else p[field] >= rule[limit]
                    checks.append({'parameter':label,'actual':p[field],'limit':rule[limit],'direction':direction,'ok':ok})
                    if not ok:
                        failures.append(f'{label}: {p[field]} не соответствует ограничению {rule[limit]}.')
            compare('Минимальная площадь, м²','area_m2','min_area_m2','min')
            compare('Максимальная площадь, м²','area_m2','max_area_m2','max')
            compare('Высота, м','height_m','max_height_m','max')
            compare('Минимальный отступ, м','setback_m','setback_m','min')
            if p.get('area_m2'):
                for label,field,limit,mult in [('Процент застройки','building_area_m2','max_coverage_pct',100),('Плотность застройки','floor_area_m2','max_density',1)]:
                    if field not in p or rule.get(limit) is None:
                        missing.append('Данные для расчёта: '+label)
                    else:
                        value = p[field]/p['area_m2']*mult
                        ok = value <= rule[limit]
                        checks.append({'parameter':label,'actual':round(value,4),'limit':rule[limit],'ok':ok})
                        if not ok:
                            failures.append(f'{label} превышает {rule[limit]}.')
                if 'approximate_area_m2' in p and abs(p['approximate_area_m2']-p['area_m2'])/p['area_m2'] > .05:
                    missing.append('Расхождение геометрии и документальной площади более 5%')
        status = 'conflicts' if failures else ('insufficient_data' if missing else 'preliminary_compliant')
        result = {'case_id':cid,'status':status,'created_at':now(),'checks':checks,'conflicts':failures,'missing':list(dict.fromkeys(missing)),'citations':citations,'classification':PURPOSES[p['purpose']], 'notice':'Предварительная проверка загруженных параметров. Не разрешение на строительство и не окончательный вывод о возможности образования участка. Нужны проверка всех применимых норм и заключение специалиста.'}
        aid = self.db.execute('INSERT INTO analyses(case_id,data,created_at) VALUES(?,?,?)',(cid,dumps(result),now()))
        self.db.audit(owner if owner is not None else 'admin','analyze',cid)
        return {**result,'analysis_id':aid}

    def source(self, p):
        from .network import validate_public_url
        validate_public_url(p['url'])
        if p.get('kind') not in ('pzz','land_code','town_code','civil_procedure','101-fz','217-fz'):
            raise ValueError('Неизвестный вид нормативного источника.')
        return self.db.execute('INSERT INTO sources(title,url,municipality_id,kind) VALUES(?,?,?,?)',(required_text(p.get('title'),'title'),p['url'],p.get('municipality_id'),p['kind']))

    def import_legal_document(self, p, actor='admin'):
        kinds = ('land_code','town_code','civil_procedure','101-fz','217-fz')
        if p.get('kind') not in kinds:
            raise ValueError('Документ должен относиться к одному из пяти нормативных актов ТЗ.')
        for field in ('title','version','source_url','citation','content','valid_until','verified_by'):
            required_text(p.get(field),field,200000 if field=='content' else 2000)
        date.fromisoformat(p['valid_until'])
        with self.db.connect() as c:
            c.execute('UPDATE legal_documents SET active=0 WHERE kind=? AND citation=?',(p['kind'],p['citation']))
            lid=c.execute('INSERT INTO legal_documents(kind,title,version,source_url,citation,content,valid_until,verified_by,verified_at) VALUES(?,?,?,?,?,?,?,?,?)',tuple(p[k] for k in ('kind','title','version','source_url','citation','content','valid_until','verified_by'))+(now(),)).lastrowid
        self.db.audit(actor,'import_legal_document',lid)
        return lid

    def legal_search(self, kind, query):
        if kind not in ('land_code','town_code','civil_procedure','101-fz','217-fz'):
            raise ValueError('Выберите нормативный акт: land_code, town_code, civil_procedure, 101-fz, 217-fz.')
        query = required_text(query,'query',500)
        terms = set(re.findall(r'[а-яёa-z0-9]{2,}',query.lower()))
        today = datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat()
        matches = []
        for row in self.db.rows('SELECT * FROM legal_documents WHERE kind=? AND active=1 AND valid_until>=?',(kind,today)):
            content = row['citation']+' '+row['title']+' '+row['content']
            score = sum(term in content.lower() for term in terms)
            if score:
                # Return the complete verified excerpt, never an invented paraphrase.
                matches.append((score,row))
        matches.sort(key=lambda pair:pair[0],reverse=True)
        return {'status':'found' if matches else 'insufficient_data','results':[r for _,r in matches[:5]],'notice':'Справка по проверенным загруженным выдержкам, не исчерпывающий поиск всех применимых норм. При отсутствии актуальной редакции требуется её загрузка специалистом.'}

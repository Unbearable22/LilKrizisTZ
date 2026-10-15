import json
import logging
import time
import threading
import urllib.request
import uuid
from .db import dumps, now
from .documents import package, STATUS
from .integrations import Integrations
from .monitor import Monitor
from .network import request_json

LOG=logging.getLogger(__name__)
MENU={'keyboard':[['📐 Новый участок','📁 Мои дела'],['🔔 Уведомления','❓ Помощь']],'resize_keyboard':True}
HELP='''ООО «Земля и право» · юридический ассистент
/new — пошаговая карточка
/new {JSON} — полная карточка (см. examples/case.json)
/cases — ваши дела
/edit ID {JSON} — дополнить поля дела
/analyze ID — проверка параметров
/docs ID — ZIP: анализ, перечень, проект обращения, схема
/nspd ID — предварительные сведения
/explain ID — пояснение LLM по результатам расчёта
/law land_code|town_code|civil_procedure|101-fz|217-fz вопрос — справка по проверенным нормам
/concept ID building|interior пожелания — концепция; затем можно отправить фото или план
/alerts — изменения источников
/cancel — отмена текущего ввода
Свободный текст: «анализ 1», «документы 1», «НСПД 1».
Расчёты предварительные; ПЗЗ и документы проверяет специалист.'''

class Telegram:
    def __init__(self,settings,service):
        self.s,self.service=settings,service
        self.db=service.db
        self.integrations=Integrations(settings,service)
        self.alert_lock=threading.RLock()
        self.base='https://api.telegram.org/bot'+settings.telegram_token+'/'

    def call(self,method,payload):
        result=request_json(self.base+method,payload,timeout=40)
        if not result.get('ok'):
            raise ValueError('Telegram не принял запрос.')
        return result['result']

    def say(self,owner,text):
        for start in range(0,len(text),3800):
            self.call('sendMessage',{'chat_id':owner,'text':text[start:start+3800],'reply_markup':MENU})

    def send_file(self,owner,name,data):
        boundary='----'+uuid.uuid4().hex
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{owner}\r\n--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()+data+f'\r\n--{boundary}--\r\n'.encode()
        request=urllib.request.Request(self.base+'sendDocument',body,{'Content-Type':'multipart/form-data; boundary='+boundary})
        with urllib.request.urlopen(request,timeout=45) as response:
            if not json.load(response).get('ok'):
                raise ValueError('Telegram не принял документ.')

    def alerts(self,owner):
        with self.alert_lock:
            return self._alerts(owner)

    def _alerts(self,owner):
        rows=self.db.rows('SELECT * FROM notifications WHERE owner_id=? AND delivered_at IS NULL ORDER BY id',(owner,))
        for row in rows:
            p=json.loads(row['data'])
            self.say(owner,f'🔔 {p["title"]}\nКлиент: {p["client"]}\n{p["address"]}\nКН: {p.get("cadastre") or "не присвоен"}\n{p["source_title"]}\n{p["source_url"]}\nСвязь: {p["match"]}\n{p["notice"]}\n{p["diff"][:1800]}')
            from pathlib import Path
            artifact=Path(p['artifact'])
            self.send_file(owner,f'change-{row["revision_id"]}{artifact.suffix}',artifact.read_bytes())
            self.db.execute('UPDATE notifications SET delivered_at=? WHERE id=?',(now(),row['id']))
        return len(rows)

    def photo(self,owner,message,session):
        if session.get('step')!='concept_reference':
            self.say(owner,'Для фото/плана сначала используйте /concept ID building|interior пожелания.')
            return
        item=(message.get('photo') or [message.get('document')])[-1]
        if not item or item.get('file_size',0)>8*1024*1024:
            raise ValueError('Фото или план должны быть PNG/JPEG до 8 МБ.')
        info=self.call('getFile',{'file_id':item['file_id']})
        path=info['file_path']
        if not path.lower().endswith(('.png','.jpg','.jpeg')):
            raise ValueError('Для концепции отправьте PNG или JPEG.')
        with urllib.request.urlopen('https://api.telegram.org/file/bot'+self.s.telegram_token+'/'+path,timeout=30) as response:
            image=response.read(8*1024*1024+1)
        if len(image)>8*1024*1024:
            raise ValueError('Изображение превышает 8 МБ.')
        self.say(owner,'Создаю концепцию по фото/плану и проверенным параметрам…')
        data=self.integrations.concept(session['case_id'],owner,session['kind'],session['preferences'],image)
        self.send_file(owner,'concept-PRELIMINARY.png',data)
        self.db.session(owner,{})
        self.say(owner,'Концепция не является проектной документацией; подключения требуют технических условий.')

    def handle(self,update):
        message=update.get('message',{})
        owner=message.get('from',{}).get('id')
        if owner not in self.s.allowed_users or message.get('chat',{}).get('type')!='private' or message.get('chat',{}).get('id')!=owner:
            return
        self.alerts(owner)  # Notifications take precedence over menu state.
        session=self.db.session(owner)
        text=message.get('text','').strip()
        if message.get('photo') or message.get('document'):
            self.photo(owner,message,session)
            return
        text={'📐 Новый участок':'/new','📁 Мои дела':'/cases','🔔 Уведомления':'/alerts','❓ Помощь':'/help'}.get(text,text)
        if text in ('/start','/help'):
            self.say(owner,HELP)
            return
        if text=='/cancel':
            self.db.session(owner,{})
            self.say(owner,'Ввод отменён.')
            return
        if session.get('step') in ('client','address','cadastre','purpose','coordinates') and not text.startswith('/'):
            self.wizard(owner,text,session)
            return
        if text=='/new':
            self.db.session(owner,{'step':'client','payload':{}})
            self.say(owner,'Введите ФИО или наименование клиента. /cancel — отмена.')
            return
        if text.startswith('/new '):
            cid=self.service.create_case(owner,json.loads(text[5:]))
            self.db.session(owner,{})
            self.say(owner,f'Дело №{cid} создано. /analyze {cid}')
            return
        if text=='/cases':
            rows=self.service.cases(owner)
            self.say(owner,'\n'.join(f'№{r["id"]} · {r["data"]["client"]} · {r["data"]["address"]}' for r in rows) or 'Дел пока нет. /new')
            return
        if text=='/alerts':
            self.say(owner,'Новых уведомлений нет: все ожидающие уведомления показаны перед меню.')
            return
        parts=text.split(maxsplit=2)
        if len(parts)<2:
            self.say(owner,'Выберите типовую задачу в меню или /help.')
            return
        command={'анализ':'/analyze','документы':'/docs','нспд':'/nspd','поясни':'/explain'}.get(parts[0].lower(),parts[0].lower())
        if command=='/law':
            result=self.service.legal_search(parts[1],parts[2] if len(parts)>2 else '')
            self.say(owner,result['notice'])
            for row in result['results']:
                self.say(owner,f'{row["title"]} · {row["citation"]}\nРедакция: {row["version"]}\n{row["content"][:9000]}\n{row["source_url"]}')
            if not result['results']:
                self.say(owner,'Проверенные актуальные выдержки не найдены. Загрузите их через администратора.')
            return
        cid=int(parts[1])
        if command=='/edit':
            self.service.update_case(cid,owner,json.loads(parts[2]))
            self.say(owner,f'Дело №{cid} обновлено. /analyze {cid}')
        elif command=='/analyze':
            r=self.service.analyze(cid,owner)
            text=f'Дело №{cid} · {STATUS[r["status"]]}\n'+r['notice']
            text+='\n\nПроверки:\n'+'\n'.join(f'{x["parameter"]}: {x["actual"]} — {"✓" if x["ok"] else "несоответствие"}' for x in r['checks'])
            if r['conflicts']:
                text+='\n\nНесоответствия:\n'+'\n'.join(r['conflicts'])
            if r['missing']:
                text+='\n\nНужны данные:\n'+'\n'.join(r['missing'])
            text+='\n\nОснования:\n'+'\n'.join(c['citation']+' '+c['url'] for c in r['citations'])
            self.say(owner,text)
        elif command=='/docs':
            self.send_file(owner,f'case-{cid}.zip',package(self.service,cid,owner))
        elif command=='/nspd':
            self.say(owner,dumps(self.integrations.nspd(cid,owner)))
        elif command=='/explain':
            self.say(owner,dumps(self.integrations.explain(cid,owner)))
        elif command=='/concept':
            self.service.case(cid,owner)
            if len(parts)<3 or parts[2].split()[0] not in ('building','interior'):
                raise ValueError('/concept ID building|interior пожелания')
            extra=parts[2].split(maxsplit=1)
            self.db.session(owner,{'step':'concept_reference','case_id':cid,'kind':extra[0],'preferences':extra[1] if len(extra)>1 else ''})
            self.say(owner,'Отправьте фото участка/помещения или план здания (PNG/JPEG). /generate — без фото, /cancel — отмена.')
        else:
            self.say(owner,'Задача не распознана. /help')

    def wizard(self,owner,text,s):
        step,p=s['step'],s['payload']
        prompts={'client':('address','Введите адрес участка.'),'address':('cadastre','Введите кадастровый номер или «нет» для образуемого участка.'),'cadastre':('purpose','Назначение: housing — жильё, commercial — коммерция, agriculture — сельское хозяйство.'),'purpose':('coordinates','Введите координаты WGS84 в JSON: [[долгота,широта], ...] либо «нет».')}
        if step=='coordinates':
            if text.lower()!='нет':
                p['coordinates']=json.loads(text)
            cid=self.service.create_case(owner,p)
            self.db.session(owner,{})
            self.say(owner,f'Создано дело №{cid}. /analyze {cid}\nДополняйте карточку: /edit {cid} {{"area_m2": 1000, "zone": "Ж-1"}}')
            return
        if step=='cadastre':
            from .service import CADASTRE
            if text.lower()!='нет':
                if not CADASTRE.fullmatch(text):
                    raise ValueError('Неверный кадастровый номер; пример: 90:12:172201:102.')
                p[step]=text
        elif step=='purpose':
            if text not in ('housing','commercial','agriculture'):
                raise ValueError('Введите housing, commercial или agriculture.')
            p[step]=text
        else:
            p[step]=text
        next_step,prompt=prompts[step]
        self.db.session(owner,{'step':next_step,'payload':p})
        self.say(owner,prompt)

    def run(self):
        if not self.s.telegram_token or not self.s.allowed_users:
            raise ValueError('Задайте TELEGRAM_BOT_TOKEN и ALLOWED_TELEGRAM_IDS. Пустой список запрещает доступ всем.')
        stop=threading.Event()
        def background():
            last_monitor=0
            while not stop.is_set():
                try:
                    if time.monotonic()-last_monitor>=self.s.monitor_seconds:
                        Monitor(self.db).run()
                        last_monitor=time.monotonic()
                    for owner in self.s.allowed_users:
                        self.alerts(owner)
                except Exception as exc:
                    LOG.error('Фоновый мониторинг: %s',type(exc).__name__)
                stop.wait(5)
        threading.Thread(target=background,daemon=True,name='monitor-alerts').start()
        try:
            self._poll()
        finally:
            stop.set()

    def _poll(self):
        while True:
            try:
                updates=self.call('getUpdates',{'offset':int(self.db.state('telegram_offset') or 0),'timeout':20,'allowed_updates':['message']})
                for update in updates:
                    owner=update.get('message',{}).get('from',{}).get('id')
                    try:
                        text=update.get('message',{}).get('text','')
                        session=self.db.session(owner) if owner in self.s.allowed_users else {}
                        if text=='/generate' and session.get('step')=='concept_reference' and update['message'].get('chat',{}).get('type')=='private':
                            self.alerts(owner)
                            data=self.integrations.concept(session['case_id'],owner,session['kind'],session['preferences'])
                            self.send_file(owner,'concept-PRELIMINARY.png',data)
                            self.db.session(owner,{})
                        else:
                            self.handle(update)
                    except (ValueError,KeyError,IndexError,TypeError) as exc:
                        if owner in self.s.allowed_users and update.get('message',{}).get('chat',{}).get('type')=='private':
                            detail=str(exc)[:250] if isinstance(exc,ValueError) else 'Проверьте формат команды и обязательные поля.'
                            self.say(owner,'Не удалось выполнить запрос: '+detail+'\n/help; /cancel — сброс ввода.')
                    self.db.state('telegram_offset',update['update_id']+1)
            except Exception as exc:
                LOG.error('Цикл Telegram: %s',type(exc).__name__)
                time.sleep(3)

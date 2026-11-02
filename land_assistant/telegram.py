import json
import logging
import time
import threading
import urllib.request
import uuid
from .db import dumps, now
from .documents import package, STATUS
from .integrations import Integrations, NSPD_URBAN_URL
from .nspd_reports import Reports, MAX_REPORT_BYTES
from .monitor import Monitor
from .network import request_json
from .button_ui import ButtonUI, button

LOG=logging.getLogger(__name__)
MENU={'keyboard':[['📐 Новый участок','📁 Мои дела'],['🌐 НСПД','📚 Законодательство'],['🔔 Уведомления','❓ Помощь'],['🏠 Главное меню','❌ Отмена']],'resize_keyboard':True}
HELP='Выберите действие кнопкой в меню. Создайте участок и откройте дело: анализ, документы, НСПД, редактирование и концепции доступны в его карточке.'

class Telegram(ButtonUI):
    def __init__(self,settings,service):
        self.s,self.service=settings,service
        self.db=service.db
        self.integrations=Integrations(settings,service)
        self.reports=Reports(service)
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

    def nspd_button(self,owner):
        if self.s.telegram_token:
            self.call('sendMessage',{'chat_id':owner,'text':'Откройте сервис, войдите на портале и сохраните результат. Затем отправьте сюда PDF или ссылку НСПД. Для отмены нажмите кнопку.', 'reply_markup':{'inline_keyboard':[[{'text':'Открыть градостроительную проработку НСПД','url':NSPD_URBAN_URL}],[button('Отмена','home')]]}})
        else:
            self.say(owner,NSPD_URBAN_URL+'\nОтправьте PDF или ссылку результата. Для отмены нажмите кнопку.')

    def download_report(self,item):
        size=item.get('file_size',0)
        if not isinstance(size,int) or size<0 or size>MAX_REPORT_BYTES:
            raise ValueError('PDF должен быть до 12 МБ.')
        if not item.get('file_name','').lower().endswith('.pdf'):
            raise ValueError('Сохраните результат как PDF и отправьте документом, либо пришлите ссылку НСПД.')
        info=self.call('getFile',{'file_id':item['file_id']})
        # The path is supplied by Telegram, never use the user's original filename as a local path.
        path=info['file_path']
        if not isinstance(path,str) or path.startswith('/') or '..' in path.split('/') or any(c in path for c in ('?', '#', '\\')):
            raise ValueError('Некорректный путь файла Telegram.')
        with urllib.request.urlopen('https://api.telegram.org/file/bot'+self.s.telegram_token+'/'+path,timeout=30) as response:
            data=response.read(MAX_REPORT_BYTES+1)
        if len(data)>MAX_REPORT_BYTES:
            raise ValueError('PDF превышает 12 МБ.')
        return data

    def receive_nspd(self,owner,message,session):
        cid=session['case_id']
        self.service.case(cid,owner)
        if message.get('document'):
            report=self.reports.add_pdf(cid,owner,self.download_report(message['document']))
        elif message.get('photo'):
            raise ValueError('Пришлите исходный PDF документом или ссылку результата НСПД. Фото отчёта не импортируется.')
        else:
            report=self.reports.add_link(cid,owner,message.get('text','').strip())
        self.db.session(owner,{})
        self.panel(owner,self.reports.preparation(report['id'],owner),[[button('Материалы дела',f'reports:{cid}:0')],[button('Вернуться к делу',f'case:{cid}')]])

    def photo(self,owner,message,session):
        if session.get('step')!='concept_reference':
            self.say(owner,'Для отчёта выберите «НСПД» в деле; для фото или плана — «Концепция».')
            self.choose_case(owner)
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
        self.case_panel(owner,session['case_id'],'Концепция не является проектной документацией; подключения требуют технических условий.')

    def handle(self,update):
        callback=update.get('callback_query')
        message=callback.get('message',{}) if callback else update.get('message',{})
        actor=callback.get('from',{}) if callback else message.get('from',{})
        owner=actor.get('id')
        if owner not in self.s.allowed_users:
            if owner is not None:LOG.warning('Доступ отклонён: Telegram ID %s отсутствует в ALLOWED_TELEGRAM_IDS.',owner)
            return
        if message.get('chat',{}).get('type')!='private' or message.get('chat',{}).get('id')!=owner:
            return
        try:
            if callback:
                if self.s.telegram_token:
                    self.call('answerCallbackQuery',{'callback_query_id':callback['id']})
                self.alerts(owner)
                self.ui_callback(owner,callback.get('data',''))
            elif not (message.get('document') or message.get('photo')):
                self.alerts(owner)
                if not self.ui_message(owner,message.get('text','').strip()):self._handle_message(update)
            else:self._handle_message(update)
        except (ValueError,KeyError,IndexError,TypeError) as exc:
            detail=str(exc)[:300] if isinstance(exc,ValueError) else 'Кнопка устарела или данные имеют неверный формат.'
            session=self.db.session(owner)
            back=f'case:{session["case_id"]}' if session.get('case_id') else 'home'
            self.panel(owner,'Не удалось выполнить действие: '+detail+'\nИсправьте значение или выберите другое действие.',[[button('Отмена',back),button('Главное меню','home')]])

    def _handle_message(self,update):
        message=update.get('message',{})
        owner=message.get('from',{}).get('id')
        if not message:
            return
        if owner not in self.s.allowed_users:
            LOG.warning('Доступ отклонён: Telegram ID %s отсутствует в ALLOWED_TELEGRAM_IDS. Текст сообщения не записан.',owner)
            return
        if message.get('chat',{}).get('type')!='private' or message.get('chat',{}).get('id')!=owner:
            LOG.warning('Доступ отклонён: используйте личный чат с ботом.')
            return
        self.alerts(owner)  # Notifications take precedence over menu state.
        session=self.db.session(owner)
        text=message.get('text','').strip()
        if session.get('step')=='nspd_result' and (message.get('document') or message.get('photo') or text.startswith('https://')):
            self.receive_nspd(owner,message,session)
            return
        if message.get('photo') or message.get('document'):
            self.photo(owner,message,session)
            return
        text={'📐 Новый участок':'/new','📁 Мои дела':'/cases','🔔 Уведомления':'/alerts','❓ Помощь':'/help','🌐 НСПД':'/nspd'}.get(text,text)
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
            self.start_new(owner)
            return
        if text.startswith('/new '):
            cid=self.service.create_case(owner,json.loads(text[5:]))
            self.db.session(owner,{})
            self.case_panel(owner,cid,'Дело создано.')
            return
        if text=='/cases':
            self.choose_case(owner)
            return
        if text=='/alerts':
            self.say(owner,'Новых уведомлений нет: все ожидающие уведомления показаны перед меню.')
            return
        if text=='/nspd':
            self.choose_case(owner,'nspd')
            return
        parts=text.split(maxsplit=2)
        if len(parts)<2:
            self.home(owner)
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
        if command=='/nspd_import':
            self.service.case(cid,owner)
            self.db.session(owner,{'step':'nspd_result','case_id':cid})
            self.panel(owner,f'Прикрепление к делу №{cid}. Пришлите PDF до 12 МБ или HTTPS-ссылку результата на nspd.gov.ru.',[[button('Отмена',f'case:{cid}')]])
        elif command=='/nspd_reports':
            self.reports_panel(owner,cid)
        elif command=='/nspd_report':
            self.ui_callback(owner,f'report:{cid}')
        elif command=='/edit':
            self.service.update_case(cid,owner,json.loads(parts[2]))
            self.case_panel(owner,cid,'Данные обновлены.')
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
            self.service.case(cid,owner)
            self.db.session(owner,{'step':'nspd_result','case_id':cid})
            self.nspd_button(owner)
            result=self.integrations.nspd(cid,owner)
            if result['status']=='manual_action_required':
                self.say(owner,result['notice']+'\n'+result['service_url']+'\nКадастровый номер: '+(result['cadastre'] or 'не задан')+'\n\n'+'\n'.join(f'{i}. {step}' for i,step in enumerate(result['steps'],1)))
                if result['contour_geojson']:
                    self.send_file(owner,f'case-{cid}-nspd.geojson',json.dumps(result['contour_geojson'],ensure_ascii=False).encode())
            else:
                self.say(owner,dumps(result))
        elif command=='/explain':
            self.say(owner,dumps(self.integrations.explain(cid,owner)))
        elif command=='/concept':
            self.service.case(cid,owner)
            if len(parts)<3 or parts[2].split()[0] not in ('building','interior'):
                raise ValueError('Выберите вид концепции в карточке дела.')
            extra=parts[2].split(maxsplit=1)
            self.db.session(owner,{'step':'concept_reference','case_id':cid,'kind':extra[0],'preferences':extra[1] if len(extra)>1 else ''})
            self.panel(owner,'Отправьте фото участка/помещения или план (PNG/JPEG).',[[button('Создать без фото',f'generate:{cid}')],[button('Отмена',f'case:{cid}')]])
        else:
            self.home(owner)

    def run(self):
        if not self.s.telegram_token or not self.s.allowed_users:
            raise ValueError('Задайте TELEGRAM_BOT_TOKEN и ALLOWED_TELEGRAM_IDS. Пустой список запрещает доступ всем.')
        LOG.info('Бот запущен; разрешённых пользователей: %s. Ожидание сообщений…',len(self.s.allowed_users))
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
                updates=self.call('getUpdates',{'offset':int(self.db.state('telegram_offset') or 0),'timeout':20,'allowed_updates':['message','callback_query']})
                for update in updates:
                    self.handle(update)
                    self.db.state('telegram_offset',update['update_id']+1)
            except Exception as exc:
                LOG.error('Цикл Telegram: %s',type(exc).__name__)
                time.sleep(3)

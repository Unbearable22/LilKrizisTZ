"""Button navigation for all employee tasks; commands remain backward compatible."""
import json
import secrets
from .service import PURPOSES, CADASTRE, required_text

FIELDS = {
    'client':'Клиент', 'address':'Адрес', 'cadastre':'Кадастровый номер',
    'purpose':'Назначение', 'coordinates':'Координаты', 'area_m2':'Площадь участка, м²',
    'use_code':'Код ВРИ', 'zone':'Территориальная зона', 'municipality_id':'Муниципалитет',
    'category':'Категория земель', 'ownership':'Право на участок',
    'building_area_m2':'Площадь застройки, м²', 'floor_area_m2':'Площадь этажей, м²',
    'height_m':'Высота, м', 'setback_m':'Минимальный отступ, м',
    'zone_source':'Источник территориальной зоны', 'zone_verified_by':'Кто проверил зону',
    'restrictions_checked':'Проверены ли ограничения', 'restrictions':'Выявленные ограничения',
    'nspd_evidence':'Основание проверки НСПД/ЕГРН', 'utilities':'Данные коммуникаций',
    'preferences':'Пожелания к проекту',
}
NUMERIC={'area_m2','building_area_m2','floor_area_m2','height_m','setback_m'}
LAWS={'land_code':'Земельный кодекс','town_code':'Градостроительный кодекс',
      'civil_procedure':'Гражданский процессуальный кодекс','101-fz':'101-ФЗ','217-fz':'217-ФЗ'}


def button(text,data):
    return {'text':text,'callback_data':data}


def parse_coordinates(text):
    if text.lstrip().startswith('['):
        return json.loads(text)
    # One vertex per line: longitude latitude. Accept comma or semicolon separators.
    result=[]
    for line in text.strip().splitlines():
        pair=line.replace(';',' ').replace(',',' ').split()
        if len(pair)!=2:
            raise ValueError('Каждая вершина — отдельная строка: долгота широта. Например: 34.1004 45.0003')
        result.append([float(v) for v in pair])
    return result


class ButtonUI:
    def panel(self,owner,text,rows):
        if not self.s.telegram_token:
            self.say(owner,text+'\n'+' · '.join(b['text'] for row in rows for b in row))
            return
        # Keep keyboard on the final text chunk, without exposing commands.
        for start in range(0,len(text),3800):
            payload={'chat_id':owner,'text':text[start:start+3800]}
            if start+3800>=len(text):payload['reply_markup']={'inline_keyboard':rows}
            self.call('sendMessage',payload)

    def home(self,owner):
        self.db.session(owner,{})
        self.say(owner,'Выберите действие кнопкой в меню. Данные участка вводятся по подсказкам.')
        self.panel(owner,'Главное меню',[
            [button('📐 Новый участок','new'),button('📁 Мои дела','pick:case:0')],
            [button('🌐 НСПД','pick:nspd:0'),button('📚 Законодательство','laws')],
            [button('🔔 Уведомления','alerts'),button('❓ Помощь','help')]])

    def choose_case(self,owner,action='case',page=0):
        if action not in ('case','nspd'):raise ValueError('Неизвестное действие.')
        cases=self.service.cases(owner)
        if not cases:
            self.panel(owner,'Дел пока нет. Создайте участок.',[[button('📐 Новый участок','new')],[button('Главное меню','home')]])
            return
        page=max(0,min(page,(len(cases)-1)//8))
        rows=[[button(f'№{c["id"]} · {c["data"]["client"][:30]} · {c["data"]["address"][:35]}',f'{action}:{c["id"]}')] for c in cases[page*8:page*8+8]]
        nav=[]
        if page:nav.append(button('← Назад',f'pick:{action}:{page-1}'))
        if (page+1)*8<len(cases):nav.append(button('Далее →',f'pick:{action}:{page+1}'))
        if nav:rows.append(nav)
        rows.append([button('Главное меню','home')])
        self.panel(owner,f'Выберите дело · страница {page+1}',rows)

    def case_panel(self,owner,cid,prefix=''):
        case=self.service.case(cid,owner)
        p=case['data']
        self.db.session(owner,{})
        text=prefix+f'\nДело №{cid}\nКлиент: {p["client"]}\nАдрес: {p["address"]}\nКадастровый номер: {p.get("cadastre") or "не задан"}\nНазначение: {PURPOSES[p["purpose"]]}'
        text+='\n'+'\n'.join(f'{FIELDS[k]}: {p[k]}' for k in ('area_m2','zone','use_code','height_m','setback_m') if k in p)
        self.panel(owner,text.strip(),[
            [button('✏️ Изменить данные',f'fields:{cid}:0')],
            [button('📊 Анализ',f'analyze:{cid}'),button('📄 Документы',f'docs:{cid}')],
            [button('🌐 НСПД',f'nspd:{cid}'),button('📎 Материалы НСПД',f'reports:{cid}:0')],
            [button('💬 Пояснение',f'explain:{cid}'),button('🎨 Концепция',f'concepts:{cid}')],
            [button('Все дела','pick:case:0'),button('Главное меню','home')]])

    def fields_panel(self,owner,cid,page=0):
        self.service.case(cid,owner)
        self.db.session(owner,{})
        keys=list(FIELDS)
        page=max(0,min(page,(len(keys)-1)//8))
        rows=[[button(FIELDS[k],f'field:{cid}:{k}')] for k in keys[page*8:page*8+8]]
        nav=[]
        if page:nav.append(button('← Назад',f'fields:{cid}:{page-1}'))
        if (page+1)*8<len(keys):nav.append(button('Далее →',f'fields:{cid}:{page+1}'))
        if nav:rows.append(nav)
        rows.append([button('Вернуться к делу',f'case:{cid}'),button('Главное меню','home')])
        self.panel(owner,'Какое поле изменить?',rows)

    def input_panel(self,owner,s,prompt,options=None,skip=False):
        s={**s,'ui_token':secrets.token_hex(5)}
        self.db.session(owner,s)
        rows=[[button(label,f'value:{s["ui_token"]}:{i}')] for i,(label,_) in enumerate(options or [])]
        if options:
            s['options']=[v for _,v in options]
            self.db.session(owner,s)
        if skip:rows.append([button('Пропустить',f'skip:{s["ui_token"]}')])
        back=f'case:{s["case_id"]}' if s.get('case_id') else 'home'
        rows.append([button('Отмена',back),button('Главное меню','home')])
        self.panel(owner,prompt,rows)

    def field_input(self,owner,cid,key):
        if key not in FIELDS:raise ValueError('Поле недоступно.')
        if key=='municipality_id':
            self.municipality_panel(owner,cid)
            return
        p=self.service.case(cid,owner)['data']
        s={'step':'edit_field','case_id':cid,'field':key}
        options=None
        if key=='purpose':options=list((label,value) for value,label in PURPOSES.items())
        if key=='restrictions_checked':options=[('Да, проверены специалистом',True),('Нет',False)]
        current=p.get(key,'не заполнено')
        prompt=f'{FIELDS[key]}\nСейчас: {str(current)[:600]}\nВведите новое значение.'
        if key=='coordinates':prompt+='\nКаждая вершина на новой строке: долгота широта (WGS84).'
        elif key=='restrictions':prompt+='\nРазделите ограничения точкой с запятой; если не выявлены — выберите кнопку.';options=[('Не выявлены',[])]
        elif key in NUMERIC:prompt+='\nВведите число, например 150 или 3,5.'
        self.input_panel(owner,s,prompt,options)

    def municipality_panel(self,owner,cid,page=0):
        self.service.case(cid,owner)
        items=self.db.rows('SELECT id,name FROM municipalities ORDER BY name,id')
        page=max(0,min(page,max(0,(len(items)-1)//8)))
        options=items[page*8:page*8+8]
        token=secrets.token_hex(5)
        self.db.session(owner,{'step':'edit_field','case_id':cid,'field':'municipality_id','ui_token':token,'options':[m['id'] for m in options]})
        rows=[[button(m['name'],f'value:{token}:{i}')] for i,m in enumerate(options)]
        nav=[]
        if page:nav.append(button('← Назад',f'municipal:{cid}:{page-1}'))
        if (page+1)*8<len(items):nav.append(button('Далее →',f'municipal:{cid}:{page+1}'))
        if nav:rows.append(nav)
        rows.append([button('Вернуться к делу',f'case:{cid}')])
        self.panel(owner,'Выберите муниципалитет из справочника.' if items else 'Справочник муниципалитетов пуст. Администратору нужно добавить официальные данные.',rows)

    def start_new(self,owner):
        self.input_panel(owner,{'step':'client','payload':{}},'Введите ФИО или наименование клиента.')

    def wizard(self,owner,text,s):
        step,p=s['step'],dict(s['payload'])
        if step=='coordinates':
            if text is not None and str(text).lower()!='нет':p['coordinates']=parse_coordinates(text)
            cid=self.service.create_case(owner,p)
            self.case_panel(owner,cid,'Создано дело. Дополните параметры через кнопку «Изменить данные».')
            return
        if step=='cadastre':
            if text is not None and str(text).lower()!='нет':
                if not isinstance(text,str) or not CADASTRE.fullmatch(text):raise ValueError('Неверный кадастровый номер. Пример: 90:12:172201:102.')
                p[step]=text
        elif step=='purpose':
            if text not in PURPOSES:raise ValueError('Выберите назначение кнопкой.')
            p[step]=text
        else:p[step]=required_text(text,FIELDS[step],300 if step=='client' else 1000)
        next_step={'client':'address','address':'cadastre','cadastre':'purpose','purpose':'coordinates'}[step]
        prompt={'address':'Введите адрес участка.','cadastre':'Введите кадастровый номер. Если участок ещё не образован, нажмите «Пропустить».','purpose':'Выберите назначение участка.','coordinates':'Введите координаты WGS84: каждая вершина на новой строке в виде «долгота широта». Если координат пока нет, нажмите «Пропустить».'}[next_step]
        self.input_panel(owner,{'step':next_step,'payload':p},prompt,list((label,value) for value,label in PURPOSES.items()) if next_step=='purpose' else None,next_step in ('cadastre','coordinates'))

    def input_value(self,owner,value,s):
        step=s.get('step')
        if step in ('client','address','cadastre','purpose','coordinates'):
            self.wizard(owner,value,s)
        elif step=='edit_field':
            key=s['field']
            if key in NUMERIC and isinstance(value,str):value=float(value.strip().replace(',','.'))
            elif key=='coordinates' and isinstance(value,str):value=parse_coordinates(value)
            elif key=='restrictions' and isinstance(value,str):value=[v.strip() for v in value.split(';') if v.strip()]
            elif key=='utilities' and isinstance(value,str):value={'description':value}
            elif key=='restrictions_checked' and not isinstance(value,bool):raise ValueError('Выберите «Да» или «Нет» кнопкой.')
            self.service.update_case(s['case_id'],owner,{key:value})
            self.case_panel(owner,s['case_id'],'Данные обновлены.')
        elif step=='law_query':
            r=self.service.legal_search(s['kind'],value)
            self.say(owner,r['notice'])
            for row in r['results']:self.say(owner,f'{row["title"]} · {row["citation"]}\n{row["content"][:9000]}\n{row["source_url"]}')
            self.panel(owner,'Найденные проверенные выдержки показаны выше.' if r['results'] else 'Проверенные выдержки не найдены.',[[button('Другой вопрос',f'law:{s["kind"]}')],[button('Выбрать закон','laws'),button('Главное меню','home')]])
            self.db.session(owner,{})
        elif step=='concept_preferences':
            self.service.case(s['case_id'],owner)
            self.input_panel(owner,{'step':'concept_reference','case_id':s['case_id'],'kind':s['kind'],'preferences':value or ''},'Отправьте фото или план (PNG/JPEG) либо создайте концепцию без фото.')
            # Generation choice is a separate callback, never a typed command.
            self.panel(owner,'Как создать концепцию?',[[button('Создать без фото',f'generate:{s["case_id"]}')],[button('Вернуться к делу',f'case:{s["case_id"]}')]])
        else:raise ValueError('Сначала выберите действие в меню.')

    def reports_panel(self,owner,cid,page=0):
        reports=self.reports.list(cid,owner)
        page=max(0,min(page,max(0,(len(reports)-1)//8)))
        rows=[[button(f'Материал №{r["id"]} · {r["data"]["kind"]}',f'report:{r["id"]}')] for r in reports[page*8:page*8+8]]
        nav=[]
        if page:nav.append(button('← Назад',f'reports:{cid}:{page-1}'))
        if (page+1)*8<len(reports):nav.append(button('Далее →',f'reports:{cid}:{page+1}'))
        if nav:rows.append(nav)
        rows += [[button('📎 Прикрепить результат',f'import:{cid}')],[button('Вернуться к делу',f'case:{cid}')]]
        self.panel(owner,'Выберите материал для просмотра.' if reports else 'Материалов пока нет.',rows)

    def ui_callback(self,owner,data):
        parts=data.split(':')
        action=parts[0]
        if action in ('value','skip'):
            s=self.db.session(owner)
            if not s.get('ui_token') or len(parts)<2 or parts[1]!=s['ui_token']:
                self.panel(owner,'Эта кнопка относится к предыдущему шагу. Используйте последнее сообщение.',[[button('Главное меню','home')]])
                return
            if action=='skip':
                if s.get('step') not in ('cadastre','coordinates','concept_preferences'):raise ValueError('Этот шаг нельзя пропустить.')
                value=None
            else:value=s['options'][int(parts[2])]
            self.input_value(owner,value,s)
            return
        if action=='home':self.home(owner);return
        if action=='new':self.start_new(owner);return
        if action=='pick':self.db.session(owner,{});self.choose_case(owner,parts[1],int(parts[2]));return
        if action=='help':
            self.panel(owner,'Создайте участок, выберите дело и действие. Данные вводите по подсказкам. Для НСПД откройте портал кнопкой, войдите там и отправьте сюда результат. Все расчёты предварительные; материалы проверяет специалист.',[[button('Главное меню','home')]])
            return
        if action=='alerts':
            self.db.session(owner,{})
            self.panel(owner,'Ожидающие уведомления показаны перед меню. Новых уведомлений нет.',[[button('Главное меню','home')]])
            return
        if action=='laws':
            self.db.session(owner,{})
            self.panel(owner,'Выберите нормативный акт.',[[button(label,f'law:{kind}')] for kind,label in LAWS.items()]+[[button('Главное меню','home')]])
            return
        if action=='law':
            if parts[1] not in LAWS:raise ValueError('Неизвестный нормативный акт.')
            self.input_panel(owner,{'step':'law_query','kind':parts[1]},f'{LAWS[parts[1]]}\nВведите вопрос или слова для поиска.')
            return
        cid=int(parts[1])
        if action=='report':
            row=self.reports.get(cid,owner)
            self.panel(owner,self.reports.preparation(cid,owner),[[button('Материалы дела',f'reports:{row["case_id"]}:0')],[button('Вернуться к делу',f'case:{row["case_id"]}')]])
            return
        self.service.case(cid,owner)  # Every case action rechecks ownership, including forged callbacks.
        if action=='case':self.case_panel(owner,cid)
        elif action=='fields':self.fields_panel(owner,cid,int(parts[2]))
        elif action=='field':self.field_input(owner,cid,parts[2])
        elif action=='municipal':self.municipality_panel(owner,cid,int(parts[2]))
        elif action=='reports':self.db.session(owner,{});self.reports_panel(owner,cid,int(parts[2]))
        elif action=='concepts':
            self.db.session(owner,{})
            self.panel(owner,'Выберите вид концепции.',[[button('🏠 Здание',f'concept:{cid}:building'),button('🛋 Интерьер',f'concept:{cid}:interior')],[button('Вернуться к делу',f'case:{cid}')]])
        elif action=='concept':
            if parts[2] not in ('building','interior'):raise ValueError('Неизвестный вид концепции.')
            self.input_panel(owner,{'step':'concept_preferences','case_id':cid,'kind':parts[2]},'Введите пожелания к зданию или интерьеру либо нажмите «Пропустить».',skip=True)
        elif action=='generate':
            s=self.db.session(owner)
            if s.get('step')!='concept_reference' or s.get('case_id')!=cid:raise ValueError('Сначала выберите вид концепции и пожелания.')
            self.say(owner,'Создаю концепцию…')
            image=self.integrations.concept(cid,owner,s['kind'],s['preferences'])
            self.send_file(owner,'concept-PRELIMINARY.png',image)
            self.case_panel(owner,cid,'Концепция подготовлена; это не рабочая проектная документация.')
        elif action in ('analyze','docs','explain','nspd','import'):
            self.db.session(owner,{})
            cmd={'import':'nspd_import'}.get(action,action)
            self._handle_message({'message':{'from':{'id':owner},'chat':{'id':owner,'type':'private'},'text':f'/{cmd} {cid}'}})
            if action in ('analyze','docs','explain'):self.case_panel(owner,cid)
        else:raise ValueError('Неизвестное действие. Откройте главное меню.')

    def ui_message(self,owner,text):
        routes={'📐 Новый участок':'new','📁 Мои дела':'pick:case:0','🌐 НСПД':'pick:nspd:0','📚 Законодательство':'laws','🔔 Уведомления':'alerts','❓ Помощь':'help','🏠 Главное меню':'home','❌ Отмена':'home','/start':'home','/help':'help','/cancel':'home'}
        if text in routes:self.ui_callback(owner,routes[text]);return True
        s=self.db.session(owner)
        if s.get('step')=='nspd_result' and text and not text.startswith('/'):
            self.receive_nspd(owner,{'text':text},s)
            return True
        if s.get('step')=='concept_reference' and text and not text.startswith('/'):
            self.panel(owner,'Отправьте фото или план, либо выберите создание без фото.',[[button('Создать без фото',f'generate:{s["case_id"]}')],[button('Отмена',f'case:{s["case_id"]}')]])
            return True
        if not text.startswith('/') and s.get('step') in ('client','address','cadastre','purpose','coordinates','edit_field','law_query','concept_preferences'):
            self.input_value(owner,text,s)
            return True
        return False

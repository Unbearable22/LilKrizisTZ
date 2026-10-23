"""Closed business routes, topic-specific facts and identity-free source queries."""
import re
BASE_FIELDS={'jurisdiction':'Право какой страны относится к вопросу','situation':'Опишите ситуацию и известные обстоятельства','goal':'Какой результат вы хотите получить','region':'Регион','documents':'Какие документы или сообщения имеются','event_date':'Дата или период события; можно указать, что не знаете','party_role':'Ваша роль в ситуации','case_stage':'На какой стадии находится спор','amount':'О какой сумме идёт речь, если известно'}
LAND_FIELDS={'municipality':'Муниципалитет','address':'Адрес или местоположение участка','object_reference':'Кадастровый номер или координаты','rights':'Какие права на участок имеются','land_category':'Категория земель','land_use':'Вид разрешённого использования'}
TOPICS={'inheritance','labor','family','consumer','housing','civil','tax','administrative','criminal','procedure','other_legal'}
ALL_FIELDS={**BASE_FIELDS,**LAND_FIELDS}
def allowed_fields(topic):return {**BASE_FIELDS,**LAND_FIELDS} if topic=='land' else BASE_FIELDS

def normalize_scope(value):
    if value not in ('general','individual','parcel'):raise ValueError('Неизвестный вид задачи.')
    return 'individual' if value=='parcel' else value

def validate_tasks(plan):
    if not isinstance(plan,dict) or not isinstance(plan.get('tasks'),list) or len(plan['tasks'])>4:raise ValueError('Некорректный план.')
    result=[];ids=set()
    for original in plan['tasks']:
        if not isinstance(original,dict) or not {'task_id','function_id','formulation','scope'}<=set(original) or set(original)-{'task_id','function_id','formulation','scope','legal_topic','as_of_date'}:raise ValueError('Некорректная структура задачи.')
        task=dict(original);fn=task['function_id'];topic=task.get('legal_topic','land' if fn=='legal_help' else None)
        if fn=='legal_help' and topic!='land' or fn=='general_legal_help' and topic not in TOPICS or fn not in ('legal_help','general_legal_help'):raise ValueError('Неизвестная функция или тема.')
        tid=task['task_id'];form=task['formulation']
        if not isinstance(tid,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,30}',tid) or tid in ids:raise ValueError('Некорректный ID задачи.')
        if not isinstance(form,str) or not form.strip() or len(form)>8000:raise ValueError('Некорректная формулировка.')
        normalize_scope(task['scope'])
        if 'as_of_date' in task:
            from datetime import date
            if not isinstance(task['as_of_date'],str):raise ValueError('Некорректная дата.')
            date.fromisoformat(task['as_of_date'])
        # Preserve old fixture wire spelling; every semantic check uses normalize_scope.
        task['legal_topic']=topic;ids.add(tid);result.append(task)
    return result

TOPIC_RULES={
'inheritance':[(r'наслед','наследование способы и срок принятия наследства'),(r'пропущ','принятие наследства по истечении срока'),(r'завещ','наследование по завещанию')],
'labor':[(r'увол|уволь|расторж','общий порядок оформления прекращения трудового договора восстановление на работе сроки обращения в суд'),(r'зарплат|заработ|задерж|оплат','заработная плата зарплата задержка выплаты ответственность работодателя'),(r'сокращ','сокращение численности работников')],
'consumer':[(r'недостат|слом|брак|неисправ','права потребителя при обнаружении недостатков товара сроки предъявления требований'),(r'возврат|вернуть','возврат уплаченной денежной суммы'),(r'чек','отсутствие кассового чека'),(r'надлежащ.*качеств','обмен товара надлежащего качества')],
'family':[(r'развод|расторж|брак','порядок расторжения брака расторжение брака в суде'),(r'алимент','алиментные обязательства родителей'),(r'ребен|дет','права несовершеннолетних детей установление происхождения детей'),(r'раздел|имуществ','раздел общего имущества супругов')],
'housing':[(r'найм|наним|аренд|сним','договор найма жилого помещения форма договора найма'),(r'выселен|выгон|высел','расторжение договора найма жилого помещения выселение'),(r'залог|обеспечительн','обеспечительный платеж'),(r'жкх|коммунальн','плата за жилое помещение и коммунальные услуги')],
'civil':[(r'подряд|выполненн.*работ','договор подряда порядок оплаты работы обязанности заказчика'),(r'оказани.*услуг','возмездное оказание услуг оплата'),(r'займ|долг|расписк','договор займа обязанность возвратить сумму займа форма договора займа'),(r'пристав|исполнительн','исполнительное производство взыскание задолженности')],
'procedure':[(r'иск','форма содержание искового заявления документы прилагаемые к исковому заявлению'),(r'суд|подсуд','подсудность гражданских дел')],
'administrative':[(r'штраф|обжал|постановл','обжалование постановления по делу об административном правонарушении')],
'criminal':[(r'защит|адвокат','уголовная ответственность необходимая оборона')],
'tax':[(r'ставк','налоговая ставка'),(r'вычет','налоговые вычеты'),(r'льгот','налоговые льготы')]}
DEFAULT_QUERY={'inheritance':'наследование','labor':'права работника трудовой договор','family':'семейные права','consumer':'защита прав потребителей','housing':'жилищные права','civil':'защита гражданских прав договор','tax':'налоговые обязательства','administrative':'административная ответственность','criminal':'уголовная ответственность','procedure':'судебная защита','other_legal':'защита гражданских прав'}
def search_query(formulation,topic):
    # Only canonical legal phrases leave the host. No arbitrary client token does.
    if topic=='tax' and re.search(r'прода|продаж|отчужден',formulation.lower()):
        return 'налог на доходы физических лиц продажа недвижимости освобождение доходов от налогообложения особенности продажи недвижимого имущества имущественные налоговые вычеты налоговые ставки'
    if topic=='civil' and re.search(r'прода|продаж|купл',formulation.lower()):
        return 'договор продажи недвижимости форма договора продажи недвижимости государственная регистрация перехода права собственности на недвижимость'
    if topic=='civil' and re.search(r'подряд|оказани.*услуг',formulation.lower()):
        return 'договор подряда порядок оплаты работы' if 'подряд' in formulation.lower() else 'возмездное оказание услуг обязанность оплатить услуги'
    found=[phrase for pattern,phrase in TOPIC_RULES.get(topic,[]) if re.search(pattern,formulation.lower())]
    return ' '.join(dict.fromkeys(found or [DEFAULT_QUERY.get(topic,'защита прав')]))[:1500]

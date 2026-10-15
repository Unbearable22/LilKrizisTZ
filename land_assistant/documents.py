import io
import json
import zipfile
from xml.sax.saxutils import escape
from .geometry import svg

STATUS={'insufficient_data':'Недостаточно данных','conflicts':'Обнаружены несоответствия','preliminary_compliant':'Загруженные параметры предварительно соответствуют ПЗЗ'}

def docx(lines):
    body=''.join('<w:p><w:r><w:t xml:space="preserve">'+escape(str(line))+'</w:t></w:r></w:p>' for line in lines)
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr('_rels/.rels','<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr('word/document.xml','<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+body+'<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1701"/></w:sectPr></w:body></w:document>')
    return stream.getvalue()

def render_report(p,r):
    lines=['ООО «Земля и право» — предварительный анализ участка',f'Дело №{r["case_id"]}; дата: {r["created_at"]}',f'Клиент: {p["client"]}',f'Адрес: {p["address"]}',f'Кадастровый номер: {p.get("cadastre","не присвоен")}',f'Результат: {STATUS[r["status"]]}',r['notice'],'Проверки:']
    lines += [f'{x["parameter"]}: {x["actual"]}; норматив: {x.get("limit",x.get("allowed"))}; {"соответствует" if x["ok"] else "НЕ соответствует"}' for x in r['checks']]
    lines += ['Несоответствия:']+(r['conflicts'] or ['Не выявлены в проверенных параметрах.'])
    lines += ['Недостающие сведения:']+(r['missing'] or ['По настроенным проверкам отсутствуют.'])
    lines += ['Нормативные основания:']+[f'{c["citation"]}; редакция {c["version"]}; {c["url"]}; проверил {c["verified_by"]}, {c["verified_at"]}' for c in r['citations']]
    return lines

def package(service,cid,owner=None):
    case=service.case(cid,owner)
    r=service.analyze(cid,owner)
    p=case['data']
    checklist=['Рабочий перечень документов — требует адаптации специалистом',f'Клиент: {p["client"]}; участок: {p["address"]}','1. Правоустанавливающие документы; сведения ЕГРН (если участок учтён).','2. Координаты в требуемой местной системе координат; кадастровые материалы.','3. Актуальные ПЗЗ с картой территориальной зоны и всеми применимыми изменениями.','4. Сведения ЗОУИТ, сервитутов, красных линий, охраны природы и культурного наследия.','5. Проверка категории земель, ВРИ и прав на образование участка.','6. Для строительства: ГПЗУ, технические условия, проектная документация, разрешения по применимому порядку.','7. Для образования участка: схема/проект межевания и заявление по применимой процедуре.','Этот список не является исчерпывающим или утверждённой формой.','Требуется дополнительно:']+r['missing']
    draft=['ПРОЕКТ ОБРАЩЕНИЯ — НЕ ОФИЦИАЛЬНАЯ ФОРМА',f'В уполномоченный орган: [заполнить после определения компетенции]',f'Заявитель: {p["client"]}','Паспорт/ОГРН, адрес для ответа: [заполнить]','Представитель, основание полномочий: [заполнить]',f'Прошу рассмотреть вопрос о возможности образования/использования земельного участка по адресу: {p["address"]}.',f'Кадастровый номер: {p.get("cadastre","не присвоен")}; цель: {r["classification"]}; ВРИ: {p.get("use_code","уточнить")}.','Правовое основание, требуемая процедура и состав приложений: [определяет специалист].','Дата: __________ Подпись: __________','Перед подачей адаптировать к действующей форме и компетенции органа.']
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('01-analysis.docx',docx(render_report(p,r)))
        z.writestr('02-checklist.docx',docx(checklist))
        z.writestr('03-application-DRAFT.docx',docx(draft))
        z.writestr('analysis.json',json.dumps(r,ensure_ascii=False,indent=2))
        z.writestr('case.json',json.dumps(p,ensure_ascii=False,indent=2))
        if p.get('coordinates'):
            z.writestr('04-parcel-PRELIMINARY.svg',svg(p['coordinates'],p['address']))
        z.writestr('README.txt','Рабочие проекты. Схема не является утверждённой СРЗУ. Формы, проектная документация и юридические выводы требуют проверки специалистом. Изображения не заменяют архитектурный проект и инженерные расчёты.')
    return out.getvalue()

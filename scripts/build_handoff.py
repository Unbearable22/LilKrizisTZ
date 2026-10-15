"""Build the review package locally, without credentials or network access."""
import json
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from land_assistant.db import Database
from land_assistant.documents import docx, package
from land_assistant.service import Service

OUT=ROOT/'deliverables'
OUT.mkdir(exist_ok=True)
lines=[
    'ООО «Земля и право»',
    'Демонстрация юридического ИИ-ассистента',
    'Версия 0.1.0 — 15 октября 2026 года',
    'Назначение',
    'Продемонстрировать основной процесс работы из ТЗ: карточка участка → проверка исходных данных и параметров по правилам → комплект рабочих документов.',
    'Что реализовано',
    '1. Telegram-сценарий с меню, доступом по ID сотрудников и отдельными делами пользователей. Для демонстрации без токена доступна локальная интерактивная консоль.',
    '2. Реестр клиентов и участков, редактирование, назначение, категория, ВРИ, координаты и параметры строительства.',
    '3. Проверка контура, предварительная площадь и схема, определение муниципалитета при наличии проверенной границы.',
    '4. Проверка основных ВРИ, площади, высоты, отступа, процента и плотности застройки по загруженной редакции правил.',
    '5. DOCX-отчёт, рабочий перечень документов, черновик обращения, SVG-схема, JSON с исходными данными и расчётом.',
    '6. Мониторинг заданных нормативных URL, сохранение исходников и изменений, очередь приоритетных уведомлений; деактивация правил после изменений.',
    '7. Справочник проверенных выдержек ЗК, ГрК, ГПК, 101-ФЗ и 217-ФЗ; адаптеры LLM, НСПД и создания архитектурных концепций.',
    'Что означает учебный пример',
    'Границы, нормы, клиент и подтверждения в примере синтетические. Кадастровый номер взят из ТЗ и через НСПД не проверялся. Положительный результат подтверждает работу заданных проверок на учебных данных, а не законность строительства.',
    'Проверка качества',
    '14 автоматических тестов пройдены: расчёты и несоответствия, обязательные данные, изоляция дел, геометрия, DOCX, мониторинг, поиск норм, контракты адаптеров и авторизация API. Реальные внешние подключения не проверялись без доступов.',
    'До полноценного запуска',
    'Нужны актуальные официальные ПЗЗ, карты зон и границы, утверждённые формы, ответственный юрист, бот и доступы провайдеров. Полный правовой анализ, официальная СРЗУ, покрытие всех муниципалитетов, автоматический разбор произвольных актов и рабочая проектная документация требуют отдельной доработки. Полная матрица приложена в docs/requirements.md.',
    'Как посмотреть',
    'В архиве «Пример документов.zip» находятся готовые учебные документы. Для воспроизведения: Python 3.11+, команда DATA_DIR=data/demo python -m land_assistant demo. Интерактивный показ: DATA_DIR=data/console python -m land_assistant console. Подробности — README.md и docs/demo-script.md.',
    'Правки клиента',
    'Просим указать: шаг сценария, ожидаемый результат, нужные изменения и обезличенный пример исходных данных. Для следующей итерации выбрать первый муниципалитет и конкретную процедуру образования/использования участка.',
]
(OUT/'Демонстрация для клиента.docx').write_bytes(docx(lines))
with tempfile.TemporaryDirectory() as tmp:
    service=Service(Database(tmp))
    load=lambda name:json.loads((ROOT/'examples'/name).read_text())
    service.import_municipality(load('municipality.demo.json'))
    service.import_rule(load('rule.demo.json'))
    cid=service.create_case(123456,load('case.json'))
    (OUT/'Пример документов.zip').write_bytes(package(service,cid,123456))
with zipfile.ZipFile(OUT/'Земля и право — демонстрация.zip','w',zipfile.ZIP_DEFLATED) as z:
    for folder in ('land_assistant','tests','docs','examples','scripts'):
        for path in sorted((ROOT/folder).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                z.write(path,path.relative_to(ROOT))
    for name in ('README.md','.env.example','.gitignore','Dockerfile','compose.yaml'):
        z.write(ROOT/name,name)
    for name in ('Демонстрация для клиента.docx','Пример документов.zip'):
        z.write(OUT/name,name)
    z.writestr('data/.gitkeep','')
print(OUT/'Земля и право — демонстрация.zip')

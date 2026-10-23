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
lines=['ООО «Земля и право» — GROUNDandLAW',
'Веб-прототип юридической помощи — 22.10.2026',
'Сообщение → классификация → отдельный файловый MCP → чтение промпта и нормативных фрагментов → модель → ответ без источников.',
'Проверен профиль DeepSeek V4.1 Flash через Tooken Club, MCP и HTTP. После доработки неполных данных: 7 дополнительных сценариев, основной набор 20 с адресными повторами; 85 Python-тестов и 11 JS-тестов. Юридическая экспертная приёмка остаётся отдельной работой. Отчёт: docs/legal-evaluation.md.',
'Понятный вопрос обрабатывается без полной анкеты. При нехватке фактов возможен предварительный ответ с вариантами «если…, то…» и необязательными уточнениями. При нехватке нормативных оснований вывод не выдумывается. Подробности: docs/conditional-answers.md.',
'Запуск и сценарий показа: docs/client-demo.md. Открывать приложение нужно через Python-сервер, а не отдельный index.html.',
'Локальные ключи в поставку не включены. В demo модель не вызывается. Публичный сервер не развёрнут.',
'Пять актов повторно сверены 22.10.2026, тексты неизменны. Подтверждённая актуальность истекает в конце 22.10.2026 по Москве; автообновление ещё не реализовано. Отчёт: docs/legal-recheck.md.',
'Лексический поиск может не найти нужную норму. Отказ при недостаточности материалов ожидаем. Автоматические проверки не заменяют экспертную приёмку юристом.',
'НСПД, Госуслуги, официальные документы и обработка вложений пока не подключены.',
'Пример документов.zip относится к прежнему учебному сценарию и содержит синтетические данные.']
(OUT/'Демонстрация для клиента.docx').write_bytes(docx(lines))
with tempfile.TemporaryDirectory() as tmp:
    service=Service(Database(tmp))
    load=lambda name:json.loads((ROOT/'examples'/name).read_text())
    service.import_municipality(load('municipality.demo.json'))
    service.import_rule(load('rule.demo.json'))
    cid=service.create_case(123456,load('case.json'))
    (OUT/'Пример документов.zip').write_bytes(package(service,cid,123456))
with zipfile.ZipFile(OUT/'Земля и право — демонстрация.zip','w',zipfile.ZIP_DEFLATED) as z:
    for folder in ('land_assistant','tests','docs','examples','scripts','groundAndLaw','knowledge'):
        for path in sorted((ROOT/folder).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and not any(part in {'.git','.venv','node_modules'} for part in path.parts) and path.name!='.env':
                z.write(path,path.relative_to(ROOT))
    for name in ('README.md','.env.example','.gitignore','Dockerfile','compose.yaml','requirements-legal.txt'):
        z.write(ROOT/name,name)
    for name in ('Демонстрация для клиента.docx','Пример документов.zip'):
        z.write(OUT/name,name)
    z.writestr('data/.gitkeep','')
print(OUT/'Земля и право — демонстрация.zip')

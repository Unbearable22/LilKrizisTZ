import argparse
import json
import logging
import time
from pathlib import Path
from .config import Settings
from .db import Database
from .service import Service


def main():
    parser=argparse.ArgumentParser(description='ООО «Земля и право» — юридический ассистент')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('init')
    sub.add_parser('bot')
    api=sub.add_parser('api');api.add_argument('--host',default='127.0.0.1');api.add_argument('--port',type=int,default=8080)
    monitor=sub.add_parser('monitor');monitor.add_argument('--watch',action='store_true')
    imp=sub.add_parser('import');imp.add_argument('kind',choices=['municipality','rule','source','legal-document']);imp.add_argument('file',type=Path)
    case=sub.add_parser('case');case.add_argument('file',type=Path);case.add_argument('--owner',type=int,required=True)
    analysis=sub.add_parser('analyze');analysis.add_argument('id',type=int)
    doc=sub.add_parser('documents');doc.add_argument('id',type=int);doc.add_argument('--output',type=Path,required=True)
    sub.add_parser('demo')
    sub.add_parser('console')
    web=sub.add_parser('web');web.add_argument('--demo',action='store_true');web.add_argument('--port',type=int,default=8080);web.add_argument('--knowledge-root',type=Path,default=Path(__file__).resolve().parent.parent/'knowledge')
    args=parser.parse_args()
    settings=Settings.from_env()
    db=Database(settings.data_dir)
    service=Service(db)
    if args.command=='init':
        # Names are a starting directory, not a claim that verified PZZ coverage exists.
        for mid,name in [('simferopol-city','Городской округ Симферополь'),('simferopol-district','Симферопольский район')]:
            if not db.rows('SELECT id FROM municipalities WHERE id=?',(mid,)):
                service.import_municipality({'id':mid,'name':name})
        print('База создана. Проверенные ПЗЗ и границы ещё не импортированы.')
    elif args.command=='web':
        try:
            from .legal.web import serve_web
            from .legal.pipeline import LegalPipeline
            from .legal.model import DemoModel,LiveModel
        except ImportError as exc:
            raise ValueError('Установите зависимости: python -m pip install -r requirements-legal.txt (рекомендуется .venv).') from exc
        model=DemoModel() if args.demo else LiveModel(settings)
        serve_web(LegalPipeline(args.knowledge_root,model,demo=args.demo),Path(__file__).resolve().parent.parent/'groundAndLaw',args.port)
    elif args.command=='bot':
        from .telegram import Telegram
        Telegram(settings,service).run()
    elif args.command=='api':
        from .api import serve
        serve(service,settings,args.host,args.port)
    elif args.command=='monitor':
        from .monitor import Monitor
        while True:
            print(json.dumps(Monitor(db).run(),ensure_ascii=False),flush=True)
            if not args.watch:
                break
            time.sleep(settings.monitor_seconds)
    elif args.command=='import':
        payload=json.loads(args.file.read_text())
        fn={'municipality':service.import_municipality,'rule':service.import_rule,'source':service.source,'legal-document':service.import_legal_document}[args.kind]
        print(fn(payload))
    elif args.command=='case':
        print(service.create_case(args.owner,json.loads(args.file.read_text())))
    elif args.command=='analyze':
        print(json.dumps(service.analyze(args.id),ensure_ascii=False,indent=2))
    elif args.command=='documents':
        from .documents import package
        args.output.write_bytes(package(service,args.id))
        print(args.output)
    elif args.command=='console':
        from .telegram import Telegram
        from dataclasses import replace
        bot=Telegram(replace(settings,allowed_users=(1,)),service)
        bot.say=lambda owner,text:print(text)
        def save(owner,name,data):
            target=settings.data_dir/'exports'/name
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(data)
            print(f'Файл: {target}')
        bot.send_file=save
        print('Локальная демонстрация Telegram-сценария. /help — меню, /exit — выход. Пользователь 1.')
        while True:
            try:
                text=input('> ')
                if text=='/exit':break
                bot.handle({'message':{'from':{'id':1},'chat':{'id':1,'type':'private'},'text':text}})
            except (EOFError,KeyboardInterrupt):
                break
            except (ValueError,KeyError,IndexError,TypeError) as exc:
                print(f'Не удалось выполнить запрос: {exc}')
    elif args.command=='demo':
        if not str(settings.data_dir).rstrip('/').endswith('demo'):
            raise ValueError('Используйте отдельную базу: DATA_DIR=data/demo python -m land_assistant demo')
        examples=Path(__file__).resolve().parent.parent/'examples'
        if not db.rows('SELECT id FROM municipalities WHERE id=?',('demo-only',)):
            service.import_municipality(json.loads((examples/'municipality.demo.json').read_text()))
            service.import_rule(json.loads((examples/'rule.demo.json').read_text()))
        cid=service.create_case(123456,json.loads((examples/'case.json').read_text()))
        from .documents import package
        out=settings.data_dir/f'case-{cid}.zip'
        out.write_bytes(package(service,cid,123456))
        print(json.dumps(service.analyze(cid,123456),ensure_ascii=False,indent=2))
        print(f'Демонстрационные документы: {out}')

if __name__=='__main__':
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(name)s: %(message)s')
    try:
        main()
    except (ValueError,KeyError) as exc:
        raise SystemExit(str(exc))

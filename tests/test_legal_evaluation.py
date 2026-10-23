import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from land_assistant.config import Settings
from scripts.evaluate_legal import evaluate

class EvaluationTests(unittest.TestCase):
    def test_rate_limit_stops_remaining_cases_without_more_calls(self):
        calls=[]
        class LimitedPipeline:
            def __init__(self,*args,**kwargs):pass
            async def run(self,question,intake):
                calls.append(question)
                return {'status':'error','answer':'Попробуйте позже.','diagnostics':{'code':'llm_rate_limit'}}
        settings=Settings(Path('data'),llm_url='https://model.invalid',llm_model='fixture')
        cases=[{'id':str(i),'question':str(i),'intake':{},'expected_status':'answered','answer_keywords':''} for i in range(2)]
        with tempfile.TemporaryDirectory() as tmp,patch('scripts.evaluate_legal.local_env'),patch('scripts.evaluate_legal.Settings.from_env',return_value=settings),patch('scripts.evaluate_legal.LegalPipeline',LimitedPipeline):
            asyncio.run(evaluate(cases,Path(tmp)))
            report=json.loads((Path(tmp)/'report.json').read_text())
        self.assertEqual(len(calls),1)
        self.assertEqual(report['results'][1]['status'],'not_run')
        self.assertEqual(report['automated_passed'],0)

    def test_three_timeouts_stop_remaining_cases(self):
        calls=[]
        class TimeoutPipeline:
            def __init__(self,*args,**kwargs):pass
            async def run(self,question,intake):
                calls.append(question)
                return {'status':'error','answer':'Попробуйте позже.','diagnostics':{'code':'llm_timeout'}}
        settings=Settings(Path('data'),llm_url='https://model.invalid',llm_model='fixture')
        cases=[{'id':str(i),'question':str(i),'intake':{},'expected_status':'answered','answer_keywords':''} for i in range(4)]
        with tempfile.TemporaryDirectory() as tmp,patch('scripts.evaluate_legal.local_env'),patch('scripts.evaluate_legal.Settings.from_env',return_value=settings),patch('scripts.evaluate_legal.LegalPipeline',TimeoutPipeline):
            asyncio.run(evaluate(cases,Path(tmp)))
            report=json.loads((Path(tmp)/'report.json').read_text())
        self.assertEqual(len(calls),3)
        self.assertEqual(report['results'][3]['status'],'not_run')
        self.assertEqual(report['results'][3]['reason'],'provider_timeouts')

    def test_history_and_allowed_statuses_with_verified_references(self):
        calls=[]
        class Pipeline:
            def __init__(self,*args,**kwargs):pass
            async def run(self,question,intake,history=None):
                calls.append(history)
                return {'status':'partial_answer','answer':'Условия определяет статья 1 Земельного кодекса Российской Федерации.','legal_bases':[{'title':'Земельный кодекс Российской Федерации','article':'Статья 1','explanation':'Определяет условия.'}]}
        settings=Settings(Path('data'),llm_url='https://model.invalid',llm_model='fixture')
        history=[{'text':'Участок мой','intake':{}}]
        cases=[{'id':'history','question':'Как защитить?','intake':{},'history':history,'expected_status':['answered','partial_answer'],'answer_keywords':''}]
        with tempfile.TemporaryDirectory() as tmp,patch('scripts.evaluate_legal.local_env'),patch('scripts.evaluate_legal.Settings.from_env',return_value=settings),patch('scripts.evaluate_legal.LegalPipeline',Pipeline):
            asyncio.run(evaluate(cases,Path(tmp)))
            report=json.loads((Path(tmp)/'report.json').read_text())
        self.assertEqual(calls,[history]);self.assertEqual(report['automated_passed'],1)

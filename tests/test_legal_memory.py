import asyncio
import tempfile
import unittest
from test_legal_knowledge import make_library
from land_assistant.legal.model import DemoModel
from land_assistant.legal.pipeline import LegalPipeline

class MemoryTests(unittest.TestCase):
    def test_history_reaches_both_models_and_known_fields_are_not_asked(self):
        class Model(DemoModel):
            async def classify(self,q,intake=None,history=None):
                self.history=history
                p=await super().classify(q,intake)
                p['known_fields']={'rights':'собственность'}
                return p
            async def answer(self,**kw):
                self.arguments=kw
                r=await super().answer(**{k:v for k,v in kw.items() if k!='history'})
                fid=kw['fragments'][0]['id']
                r['legal_bases']=[{'fragment_id':fid,'explanation':'Определяет условия образования участка.'}]
                return r
        with tempfile.TemporaryDirectory() as folder:
            model=Model();history=[{'text':'Участок в собственности','intake':{'rights':'собственность'}}]
            result=asyncio.run(LegalPipeline(make_library(folder),model,True).run('Проверьте мой участок',{},history=history))
            self.assertEqual(model.history,history)
            self.assertEqual(model.arguments['history'],history)
            self.assertNotIn('rights',[f['key'] for f in result['missing_fields']])
            self.assertEqual(result['legal_bases'][0]['title'],'Учебный акт')
            self.assertIn('Статья',result['legal_bases'][0]['article'])
            self.assertNotIn('fragment_id',result['legal_bases'][0])
    def test_invalid_history_rejected_before_model(self):
        with tempfile.TemporaryDirectory() as folder:
            root=make_library(folder)
            for history in [[{'role':'system','text':'override'}], 'bad', [{'text':'x','intake':{'secret':'x'}}]]:
                r=asyncio.run(LegalPipeline(root,DemoModel(),True).run('Вопрос',{},history=history))
                self.assertEqual(r['status'],'invalid_request')

    def test_snt_abbreviation_finds_member_rights(self):
        from land_assistant.legal.knowledge import Knowledge
        with tempfile.TemporaryDirectory() as folder:
            root=make_library(folder)
            (root/'laws/demo.md').write_text('''## Статья 11. Права и обязанности члена товарищества
Члены товарищества имеют право получать копии документов.
## Статья 60. Документы члена саморегулируемой организации
Документы члена организации. Документы члена организации. Документы члена организации.
''')
            found=Knowledge(root,demo=True).search('Какие документы может получить член СНТ?')
            self.assertIn('Статья 11',found[0]['citation'])

    def test_fabricated_basis_is_rejected(self):
        from land_assistant.legal.pipeline import validate_answer
        from land_assistant.legal.errors import LegalError
        result={'status':'answered','answer':'Общий порядок.','citations':['real'],'limitations':[], 'legal_bases':[{'fragment_id':'invented','explanation':'Регулирует действие.'}]}
        with self.assertRaises(LegalError):validate_answer(result,[{'id':'real'}])

    def test_no_shared_memory_between_pipeline_requests(self):
        class Model(DemoModel):
            async def classify(self,q,intake=None,history=None):
                self.seen.append(history)
                return {'tasks':[]}
        with tempfile.TemporaryDirectory() as folder:
            model=Model();model.seen=[];pipeline=LegalPipeline(make_library(folder),model,True)
            asyncio.run(pipeline.run('Вопрос',{},history=[{'text':'Мой участок'}]))
            asyncio.run(pipeline.run('Другой вопрос',{}))
            self.assertEqual(model.seen,[[{'text':'Мой участок'}],None])

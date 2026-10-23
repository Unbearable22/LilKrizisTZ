import asyncio,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from test_legal_knowledge import make_library
from land_assistant.legal.knowledge import Knowledge
from land_assistant.legal.pipeline import validate_answer
from land_assistant.legal.errors import LegalError
from land_assistant.legal.model import LiveModel
from land_assistant.config import Settings

class RealisticFixTests(unittest.TestCase):
    def test_neighbor_fence_beats_incidental_survey_and_garages(self):
        with tempfile.TemporaryDirectory() as folder:
            root=make_library(folder)
            (root/'laws/demo.md').write_text('''## Статья 60. Восстановление положения, существовавшего до нарушения права на земельный участок
Нарушенное право восстанавливается при самовольном занятии земельного участка.
## Статья 39. Гаражи и средства передвижения
Средства передвижения. Границы земельных участков и межевание. Межевание и земельный участок.
''')
            hits=Knowledge(root,demo=True).search('Сосед передвинул забор и занял часть моего земельного участка: как действовать, если неизвестно, проводилось ли межевание')
            self.assertIn('Статья 60',hits[0]['citation'])
    def test_cross_article_reference_uses_all_selected_read_bases(self):
        fragments=[{'id':'five','title':'Учебный акт','citation':'Статья 5. Плата'},{'id':'seventeen','title':'Учебный акт','citation':'Статья 17. Собрание'}]
        r={'status':'answered','answer':'Общий порядок.','citations':['five','seventeen'],'limitations':[],'legal_bases':[{'fragment_id':'five','explanation':'Определяет плату.'},{'fragment_id':'seventeen','explanation':'Определяет плату, предусмотренную ст. 5.'}]}
        validate_answer(r,fragments)
        r['legal_bases'][1]['explanation']='Определяет плату, предусмотренную ст. 999.'
        with self.assertRaises(LegalError) as error:validate_answer(r,fragments)
        self.assertEqual(error.exception.code,'visible_references')
    def test_classifier_has_room_for_plan_and_known_fields(self):
        real_client=httpx.AsyncClient
        def respond(request):
            enough=json.loads(request.content)['max_tokens']>=2048
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop' if enough else 'length','message':{'content':'{"tasks":[],"known_fields":{}}'}}]})
        settings=Settings(Path('data'),llm_url='https://fixture.invalid',llm_model='fixture')
        with patch('land_assistant.legal.model.httpx.AsyncClient',side_effect=lambda **kw:real_client(transport=httpx.MockTransport(respond),**kw)):
            result=asyncio.run(LiveModel(settings).classify('Продать участок',{'rights':'Собственность'}))
        self.assertEqual(result['tasks'],[])
    def test_unread_article_in_explanation_gets_one_validated_repair(self):
        from land_assistant.legal.model import DemoModel
        from land_assistant.legal.pipeline import LegalPipeline
        class Model(DemoModel):
            repairs=0
            async def answer(self,**kwargs):
                fid=kwargs['fragments'][0]['id']
                return {'status':'answered','answer':'Общий порядок.','citations':[fid],'limitations':[],'legal_bases':[{'fragment_id':fid,'explanation':'Условия установлены статьёй 999, см. ст. 999.'}]}
            async def rewrite_answer(self,**kwargs):
                self.repairs+=1
                result=await self.answer(**kwargs)
                result['legal_bases'][0]['explanation']='Определяет условия образования участка.'
                return result
        with tempfile.TemporaryDirectory() as folder:
            model=Model();root=make_library(folder)
            r=asyncio.run(LegalPipeline(root,model,True).run('Образование участка',{}))
        self.assertEqual(r['status'],'answered');self.assertEqual(model.repairs,1)

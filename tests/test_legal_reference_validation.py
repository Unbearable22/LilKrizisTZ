import unittest
from land_assistant.legal.pipeline import validate_answer
from land_assistant.legal.errors import LegalError

class ReferenceValidationTests(unittest.TestCase):
    def setUp(self):
        self.fragment={'id':'known','title':'Земельный кодекс Российской Федерации','citation':'Статья 56.3. Условия изъятия','act_designation':'136-ФЗ от 25.10.2001','text':'Условия изъятия.'}
        self.result={'status':'answered','answer':'Условия определяет статья 56.3 Земельного кодекса Российской Федерации.','citations':['known'],'limitations':[],'legal_bases':[{'fragment_id':'known','explanation':'Определяет условия изъятия.'}]}
    def test_read_article_and_act_can_be_named_in_answer(self):
        validate_answer(self.result,[self.fragment])
    def test_unknown_article_act_and_private_ids_remain_blocked(self):
        for text in ['Статья 999 Земельного кодекса Российской Федерации.','Статья 56.3 Гражданского кодекса Российской Федерации.','См. закон №999-ФЗ.','См. https://secret.invalid','known']:
            with self.subTest(text=text),self.assertRaises(LegalError):
                validate_answer({**self.result,'answer':text},[self.fragment])

    def test_other_legal_codes_are_checked_against_read_sources(self):
        from land_assistant.legal.privacy import has_unverified_references
        tk=[{'id':'labor','title':'Трудовой кодекс Российской Федерации','citation':'Статья 136. Выплата'}]
        self.assertFalse(has_unverified_references('Статья 136 ТК РФ.',tk))
        self.assertTrue(has_unverified_references('Статья 136 СК РФ.',tk))
        self.assertTrue(has_unverified_references('Семейный кодекс Российской Федерации.',tk))

    def test_warranty_is_not_garant_provider_name(self):
        from land_assistant.legal.privacy import has_references
        self.assertFalse(has_references('Гарантийный срок и гарантия качества.'))
        self.assertTrue(has_references('Материал сервиса ГАРАНТ.'))

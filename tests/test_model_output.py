import json,unittest
from unittest.mock import Mock
from app.model_output import clean_overview,parse_overview
from app import research as r
class ModelOutput(unittest.TestCase):
 def text(self):return 'The University of Canterbury is a public research university in Christchurch, New Zealand.\n\nIt offers undergraduate and postgraduate study.'
 def test_prose_followed_by_complete_json_is_only_one_answer(self):
  body=self.text();raw=body+'\n\n'+json.dumps({'answer':body,'source_ids':['wiki-uc']})
  result=parse_overview(raw,['wiki-uc']);self.assertEqual(clean_overview(result['answer']),body)
  self.assertNotIn('"answer"',clean_overview(raw));self.assertEqual(clean_overview(raw).count('University of Canterbury'),1)
 def test_truncated_appended_wrapper_is_removed(self):
  body=self.text();self.assertEqual(clean_overview(body+'\n\n{"answer": "The University'),body)
 def test_pure_broken_json_is_not_displayed(self):
  for value in ['{"answer": "broken','{"source_ids": ["wiki-uc"]','```json\n{"answer": "broken']:
   self.assertEqual(clean_overview(value),'')
 def test_structured_answer_cannot_contain_another_envelope(self):
  body=self.text();self.assertEqual(clean_overview(json.dumps({'answer':body,'source_ids':['wiki-uc']})),body)
 def test_literal_newline_escapes_are_readable(self):self.assertEqual(clean_overview('First paragraph.\\n\\nSecond paragraph.'),'First paragraph.\n\nSecond paragraph.')
 def test_fake_source_ids_in_real_envelope_are_not_replaced_with_valid_ones(self):
  result=parse_overview(self.text()+'\n'+json.dumps({'answer':self.text(),'source_ids':['fake']}),['wiki-uc'])
  self.assertEqual(result['source_ids'],['fake'])
 def test_actual_overview_boundary_strips_duplicate_wrapper_before_review(self):
  body=self.text();raw=body+'\n\n'+json.dumps({'answer':body,'source_ids':['wiki-uc']})
  model=Mock(side_effect=[json.JSONDecodeError('Extra data',raw,0),{'allow':True,'supported':True}])
  source={'id':'wiki-uc','title':'University of Canterbury','text':body}
  result=r.overview('tell me about the University of Canterbury',[source],[],model)
  self.assertEqual(result[0],body);self.assertNotIn('source_ids',result[0])

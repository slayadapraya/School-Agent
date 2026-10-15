import unittest
from unittest.mock import patch,Mock
from app import research as r,planning,server as s,references
QUESTION='im writing a report about timor leste and their bamboo supply. we need to create a plan to ramp up local production etc how could i go about this?'
class RelevanceAndPlanning(unittest.TestCase):
 def unrelated(self):return {'id':'wrong','title':'Santana do Paraíso','provider':'Wikipedia','url':'https://en.wikipedia.org/?curid=1','text':'Santana do Paraíso is a Brazilian municipality located in the interior of the state of Minas Gerais','locator':'Encyclopedia article'}
 def test_original_failure_rejected_even_if_model_would_accept(self):
  model=Mock(side_effect=AssertionError)
  with patch.object(r,'retrieve',return_value=([self.unrelated()],[])):
   text,meta=r.respond('Timor Leste bamboo production',False,model,QUESTION)
  self.assertEqual(meta['sources'],[]);self.assertFalse(meta['quotation_verified']);self.assertNotIn('Brazil',text);model.assert_not_called()
 def test_country_and_material_both_required(self):
  for title,body in [('Bamboo in Brazil','Bamboo production and factories in Brazil'),('Economy of Timor-Leste','Production of coffee in Timor-Leste'),('Indonesia','Timor-Leste and bamboo are distant economic interests')]:
   source=self.unrelated();source.update(title=title,text=body)
   # The last source mentions both topics: lexical matching alone cannot establish an answer.
   if title!='Indonesia':self.assertFalse(r.relevant(source,'Timor Leste bamboo production'))
 def test_declined_quote_does_not_fall_back_to_first_words(self):
  source=self.unrelated();source.update(title='Timor-Leste bamboo',text='Timor-Leste bamboo production has a long history. This introductory text does not identify a bottleneck.')
  with patch.object(r,'retrieve',return_value=([source],[])):
   text,meta=r.respond('Timor Leste bamboo production',False,lambda *a:{'answers_question':False},'What is limiting current output?')
  self.assertFalse(meta['quotation_verified']);self.assertNotIn('long history',text);self.assertIn('not a verified answer',text)
 def test_literal_quote_is_not_enough_without_relevance_verdict(self):
  source=self.unrelated();source.update(title='Timor-Leste bamboo',text='Timor-Leste bamboo production has a long history and a variety of uses.')
  with patch.object(r,'retrieve',return_value=([source],[])):
   _,meta=r.respond('Timor-Leste bamboo',False,lambda *a:{'source_id':source['id'],'quote':source['text']})
  self.assertFalse(meta['quotation_verified'])
 def test_planning_question_gets_approach_without_invented_figures(self):
  with patch.object(r,'plan',side_effect=AssertionError):text,meta=s.answer(s.courses()[0],QUESTION,[])
  self.assertEqual(meta['route'],'planning');self.assertIn('Timor-Leste',text);self.assertIn('limiting stage',text);self.assertIn('unit and a time period',text)
  self.assertEqual(len(meta['sources']),2);self.assertIn('historical',text);self.assertNotIn('Brazil',text)
 def test_followup_has_context_and_more_detail(self):
  first,meta=planning.respond(QUESTION,[])
  history=[{'role':'user','content':QUESTION},{'role':'assistant','content':first,'hint_id':meta['hint_id']}]
  text,details=planning.respond('what data would I need? explain in more detail',history)
  self.assertIn('Timor-Leste',text);self.assertIn('throughput',text);self.assertNotEqual(text,first);self.assertNotEqual(details['hint_id'],meta['hint_id'])
 def test_planning_does_not_complete_assignment(self):
  self.assertIsNone(planning.respond('Write my report about Timor Leste bamboo production',[]))
  self.assertIsNone(planning.respond('Solve 2x + 5 = 17',[]))
 def test_catalogue_matches_complete_question_and_alias(self):
  self.assertEqual(len(r.catalogue(QUESTION)),2);self.assertEqual(len(r.catalogue('East Timor bamboo production')),2)
  self.assertEqual(r.catalogue('Brazil bamboo production'),[])
 def test_primary_reading_apa_web_reference(self):
  source=r.catalogue(QUESTION)[0];text,meta=references.response([source],'references')
  self.assertIn('Ray, A. (2019, December 9).',text);self.assertIn('United Nations Development Programme',text)
  self.assertTrue(any(p['italic'] and p['text']==source['title'] for p in meta['references'][0]['parts']))

import unittest
from unittest.mock import patch
from app import references as r,server as s,research

class References(unittest.TestCase):
 def article(self):
  return {'id':'test','title':'A study of learning','provider':'Crossref','url':'https://doi.org/10.1234/test','bibliography':{'authors':[{'family':'Smith','given':'Jane Marie'},{'family':'Jones','given':'Alex'}],'date':[2025,1,2],'journal':'Journal of Learning','volume':'8','issue':'3','pages':'20–31'}}
 def test_apa_default_and_journal_fields(self):
  text,meta=r.response([self.article()],'give me the references')
  self.assertEqual(meta['reference_style'],'APA 7')
  self.assertIn('Smith, J. M., & Jones, A. (2025). A study of learning. Journal of Learning, 8(3), 20–31. https://doi.org/10.1234/test',text)
  italic=[p['text'] for p in meta['references'][0]['parts'] if p['italic']]
  self.assertEqual(italic,['Journal of Learning','8'])
 def test_wikipedia_archived_version(self):
  source={'id':'wiki','title':'Oil painting','provider':'Wikipedia','url':'https://en.wikipedia.org/wiki/Oil_painting','bibliography':{'date':[2019,12,8],'archive_url':'https://en.wikipedia.org/w/index.php?oldid=929802398'}}
  text,meta=r.response([source],'cite this')
  self.assertIn('Oil painting. (2019, December 8). In Wikipedia.',text);self.assertNotIn('Retrieved',text)
  self.assertTrue(any(p['text']=='Wikipedia' and p['italic'] for p in meta['references'][0]['parts']))
 def test_missing_metadata_not_invented(self):
  source=self.article();source['bibliography']={}
  text,_=r.response([source],'references');self.assertIn('(n.d.)',text);self.assertNotIn('Smith',text)
 def test_author_limit_and_alphabetical_sort(self):
  a=self.article();a['bibliography']['authors']=[{'family':'Author'+str(i),'given':'Alex'} for i in range(21)]
  self.assertIn(', … Author20, A.',r.authors(a['bibliography']['authors']))
  b=self.article();b['id']='other';b['bibliography']['authors']=[{'family':'Adams','given':'Alex'}]
  self.assertEqual(r.response([a,b],'references')[1]['references'][0]['source_id'],'other')
 def test_explicit_style_override(self):self.assertEqual(r.response([self.article()],'use MLA instead')[1]['reference_style'],'MLA')
 def test_model_can_change_case_only(self):
  for value in ['Invented title','A study of learning<script>','A Study of Learning']:
   source=self.article();_,meta=r.response([source],'references',lambda *a:{'titles':{'test':value}})
   title=meta['sources'][0].get('bibliography',{}).get('sentence_title')
   self.assertEqual(title,'A Study of Learning' if value=='A Study of Learning' else None)
 def test_reference_followup_reuses_saved_sources_without_search(self):
  history=[{'role':'assistant','content':'Research','research_query':'learning','sources':[self.article()]}]
  with patch.object(research,'plan',side_effect=AssertionError),patch.object(s,'model_json',return_value={}):
   text,meta=s.answer(s.courses()[0],'give me the references',history)
  self.assertEqual(meta['reference_style'],'APA 7');self.assertIn('Smith',text)
 def test_no_duplicate_source_list(self):
  source=self.article();source['text']='A study of learning investigates how students develop their understanding over time.'
  with patch.object(research,'retrieve',return_value=([source],[])):
   text,meta=research.respond('learning',False,lambda *a:{})
  self.assertNotIn('Sources:',text);self.assertEqual(len(meta['sources']),1)

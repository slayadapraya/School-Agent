import unittest
from unittest.mock import patch
from app import server as s,administration as a
class Conversation(unittest.TestCase):
 def test_default_answers_instead_of_selecting_hint(self):
  self.assertFalse(a.DEFAULTS['approved_only']);self.assertFalse(a.DEFAULTS['require_sources']);self.assertTrue(a.DEFAULTS['block_answers'])
  with patch.object(s,'model_json',side_effect=[{'answer':'A wave carries energy while the medium oscillates.','source_ids':[]},{'allow':True}]) as model,patch.object(s.research,'plan',side_effect=AssertionError('Do not replace teaching with source selection')):
   text,meta=s.answer(s.get_course('GENERAL'),'How do waves work?',[],policy=dict(a.DEFAULTS))
  self.assertIn('energy',text);self.assertEqual(meta['route'],'configured_tutoring');self.assertEqual(model.call_count,2)
  prompt=model.call_args_list[0].args[0][0]['content'];self.assertIn('Answer the user',prompt);self.assertIn('worked practice',prompt)
 def test_followup_sends_real_conversation_and_ignores_metadata_privileges(self):
  history=[{'role':'user','content':'What are waves?'},{'role':'assistant','content':'They carry energy.','role_override':'admin'}]
  with patch.object(s,'model_json',return_value={'answer':'The leaf moves up and down.','source_ids':[]}) as model:
   s.answer(s.get_course('PHYS101'),'Why does the leaf stay there?',history,policy={**a.DEFAULTS,'review_output':False})
  import json
  payload=json.loads(model.call_args.args[0][1]['content']);self.assertEqual(payload['history'][0]['content'],'What are waves?');self.assertNotIn('role_override',str(payload))
 def test_approved_mode_remains_available(self):
  text,meta=s.answer(s.get_course('GENERAL'),'What is 9 squared?',[],policy={**a.DEFAULTS,'approved_only':True})
  self.assertEqual(meta['route'],'concept_guidance');self.assertNotIn('81',text)
 def test_model_failure_is_not_misreported_as_student_failure(self):
  with patch.object(s,'model_json',side_effect=TimeoutError):
   text,meta=s.answer(s.get_course('GENERAL'),'Explain sound waves',[],policy=dict(a.DEFAULTS))
  self.assertEqual(meta['route'],'generation_error');self.assertNotIn('what you have tried',text);self.assertIn('model connection',text)

class ConversationParsing(unittest.TestCase):
 def test_prose_followed_by_json_does_not_leak_envelope(self):
  import json
  raw='Repeated prose\n{"answer":"A wave transfers energy.","source_ids":[]}'
  with patch.object(s,'model_json',side_effect=json.JSONDecodeError('Extra data',raw,0)):
   self.assertEqual(s.conversation_candidate([])['answer'],'A wave transfers energy.')
 def test_quality_feedback_repairs_a_draft_before_display(self):
  p={**a.DEFAULTS,'review_output':True}
  with patch.object(s,'model_json',side_effect=[{'answer':'Incorrect draft.','source_ids':[]},{'allow':False,'issues':'Correct the definition.'},{'answer':'Corrected explanation.','source_ids':[]},{'allow':True}]):
   text,meta=s.answer(s.get_course('GENERAL'),'Explain frequency.',[],policy=p)
  self.assertEqual(text,'Corrected explanation.');self.assertEqual(meta['route'],'configured_tutoring')

class ConversationHTTP(unittest.TestCase):
 import test_administration as fixtures
 setUp=fixtures.Administration.setUp
 tearDown=fixtures.Administration.tearDown
 request=fixtures.Administration.request
 login=fixtures.Administration.login
 def test_default_student_chat_uses_model_with_followup_memory(self):
  cookie=self.login('student');code,boot,_=self.request('/api/bootstrap',cookie=cookie)
  self.assertEqual(code,200);self.assertTrue(all(not c['policy']['approved_only'] for c in boot['courses']))
  tid=self.request('/api/threads',{'course_id':'GENERAL'},cookie)[1]['id']
  with patch.object(s,'model_json',side_effect=[{'answer':'Waves transfer energy.','source_ids':[]},{'allow':True}]):
   code,reply,_=self.request('/api/chat',{'thread_id':tid,'message':'How do waves work?'},cookie)
  self.assertEqual(code,200);self.assertEqual(reply['meta']['route'],'configured_tutoring')
  with s.connect() as con:con.execute('UPDATE messages SET created=created-2 WHERE thread_id=?',(tid,))
  with patch.object(s,'model_json',side_effect=[{'answer':'The leaf moves locally while energy travels.','source_ids':[]},{'allow':True}]) as model:
   code,reply,_=self.request('/api/chat',{'thread_id':tid,'message':'Why does the leaf stay there?'},cookie)
  import json
  payload=json.loads(model.call_args_list[0].args[0][1]['content'])
  self.assertEqual(code,200);self.assertEqual(payload['history'][0]['content'],'How do waves work?')

class ReasoningBoundary(unittest.TestCase):
 def test_unfinished_reasoning_cannot_become_an_answer(self):
  import json
  from unittest.mock import MagicMock
  response=MagicMock();response.__enter__.return_value.read.return_value=json.dumps({'choices':[{'text':'Private working including an example {"answer":"...","source_ids":[]}'}]}).encode()
  with patch.object(s,'urlopen',return_value=response):
   with self.assertRaisesRegex(ValueError,'without a final answer'):s.model_json([{'role':'user','content':'Explain waves'}],thinking=True)
 def test_reasoning_budget_failure_retries_without_exposing_work(self):
  with patch.object(s,'settings',return_value={'conversation_reasoning':True}),patch.object(s,'model_json',side_effect=[ValueError('Model reasoning budget exhausted without a final answer'),{'answer':'A wave transfers energy.','source_ids':[]}]) as model:
   self.assertEqual(s.conversation_candidate([])['answer'],'A wave transfers energy.')
  self.assertTrue(model.call_args_list[0].kwargs['thinking']);self.assertEqual(model.call_args_list[1].kwargs,{})

class TeachingSources(unittest.TestCase):
 def test_sources_follow_current_topic_and_context(self):
  from app import learning_context as c
  self.assertIn('learning-waves',[x['id'] for x in c.sources('How do waves work?',[])])
  self.assertIn('learning-powers',[x['id'] for x in c.sources('What is squared?',[])])
  self.assertEqual(c.sources('What year did Hitler die?',[]),[])
  self.assertNotIn('learning-waves',[x['id'] for x in c.sources('What is squared?',[{'role':'user','content':'How do waves work?'}])])
 def test_plain_math_formatting_preserves_currency(self):
  from app.model_output import readable_math
  self.assertEqual(readable_math(r'$v = f\lambda$'),'v = fλ')
  self.assertEqual(readable_math('$5 \times 0.8 = 4$'),'5 × 0.8 = 4')
  self.assertEqual(readable_math('Costs $5 and $10.'),'Costs $5 and $10.')

import json
from unittest import TestCase
from unittest.mock import patch
from app import server as s, administration, hardware
import test_administration as fixtures


class FactualOverviews(TestCase):
    setUp = fixtures.Administration.setUp
    tearDown = fixtures.Administration.tearDown
    request = fixtures.Administration.request
    login = fixtures.Administration.login
    create_class = fixtures.Administration.create_class

    def test_class_and_person_overrides_and_inherit(self):
        user = self.people['other']
        self.assertFalse(administration.policy(s, user, 'MATH101')['overviews'])
        self.create_class({'overviews': True})
        self.assertTrue(administration.policy(s, user, 'MATH101')['overviews'])
        admin = self.login('admin')
        for override, expected in [({'overviews':False},False), ({'overviews':True},True), ({},True)]:
            self.assertEqual(self.request('/api/admin/policy', {'user_id':user['id'],'policy':override},admin)[0],200)
            with s.connect() as con:
                current = dict(con.execute('SELECT * FROM users WHERE id=?',(user['id'],)).fetchone())
            policy = administration.policy(s,current,'MATH101')
            self.assertEqual(policy['overviews'],expected)
            self.assertTrue(policy['block_answers']);self.assertTrue(policy['review_output'])
        self.create_class({'overviews':False})
        self.assertFalse(administration.policy(s,current,'MATH101')['overviews'])
        self.assertEqual(self.request('/api/admin/policy', {'user_id':user['id'],'policy':{'overviews':True}},self.login('student'))[0],403)

    def test_effective_setting_reaches_generation_and_review(self):
        cookie=self.login('student');admin=self.login('admin');uid=self.people['student']['id']
        tid=self.request('/api/threads',{'course_id':'GENERAL'},cookie)[1]['id']
        for enabled in (True,False):
            self.request('/api/admin/policy',{'user_id':uid,'policy':{'overviews':enabled}},admin)
            with s.connect() as con:con.execute('UPDATE messages SET created=created-2 WHERE thread_id=?',(tid,))
            with patch.object(s,'model_json',side_effect=[{},'A short factual background.' if enabled else 'I can help interpret your course material.',{'allow':True,'factual_overview':enabled}]) as model:
                status,result,_=self.request('/api/chat',{'thread_id':tid,'message':'Give me a short general university overview.','policy':{'overviews':not enabled}},cookie)
            self.assertEqual(status,200);self.assertEqual(result['meta']['route'],'student_guidance')
            marker='Administrator-managed factual overviews: '+('ON' if enabled else 'OFF')
            self.assertIn(marker,model.call_args_list[1].args[0][0]['content'])
            self.assertIn(marker,model.call_args_list[2].args[0][0]['content'])
            self.assertEqual('disclaimer' in result['meta'],enabled)

    def test_overviews_do_not_disable_numeric_answer_boundary(self):
        admin=self.login('admin');cookie=self.login('student')
        self.request('/api/admin/policy',{'user_id':self.people['student']['id'],'policy':{'overviews':True}},admin)
        tid=self.request('/api/threads',{'course_id':'GENERAL'},cookie)[1]['id']
        with patch.object(s,'model_json',side_effect=[{},'The answer is 81.','Squared means multiplying the number by itself.',{'allow':True,'factual_overview':False}]):
            _,result,_=self.request('/api/chat',{'thread_id':tid,'message':'What is 9 squared?'},cookie)
        self.assertNotIn('81',result['content']);self.assertEqual(result['meta']['route'],'student_guidance')

    def test_monitor_schema_without_gpu(self):
        with patch.object(hardware.Path,'glob',return_value=[]):result=hardware.snapshot()
        for key in ('vram_total','vram_used','utilization','temperature','power_watts'):
            self.assertIn(key,result['gpu']);self.assertIsNone(result['gpu'][key])

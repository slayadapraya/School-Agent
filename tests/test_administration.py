import json,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
from app import server as s,administration as a,hardware

class Administration(unittest.TestCase):
    def setUp(self):
        self.model_prepare_patch=patch.object(s.model_manager,'prepare',return_value={'key':'qwen3.5-9b','instance':'test-main','transport':'qwen_chatml','initial_prompt':'','private_model':False});self.model_prepare_patch.start();self.addCleanup(self.model_prepare_patch.stop)
        self.tmp=tempfile.TemporaryDirectory();self.old=(s.STATE,s.DB);s.STATE=Path(self.tmp.name);s.DB=s.STATE/'db.sqlite';s.init()
        s.add_account('Teacher','teacher','teach','test',{'courses':[],'review_records':True,'manage_courses':False})
        s.add_account('Other','student','other','test',{'courses':[],'review_records':False,'manage_courses':False})
        with s.connect() as con:self.people={x['username']:dict(x) for x in con.execute('SELECT * FROM users')}
        self.http=s.Server(('127.0.0.1',0));self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join();s.STATE,s.DB=self.old;self.tmp.cleanup()
    def request(self,path,data=None,cookie=None):
        headers={'Content-Type':'application/json','X-School-Agent':'1'}
        if cookie:headers['Cookie']=cookie
        req=urllib.request.Request('http://127.0.0.1:'+str(self.http.server_port)+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        try:
            with urllib.request.urlopen(req) as r:return r.status,json.loads(r.read()),r.headers.get('Set-Cookie')
        except urllib.error.HTTPError as e:
            with e:return e.code,json.loads(e.read()),None
    def login(self,username):
        creds=json.loads((s.STATE/'credentials.json').read_text());password=creds['teacher' if username=='admin' else 'student']['password'] if username in ('admin','student') else 'test'
        return self.request('/api/login',{'username':username,'password':password})[2].split(';')[0]
    def create_class(self,policy=None,members=None):
        admin=self.login('admin');return self.request('/api/admin/groups',{'name':'Math class','courses':['MATH101'],'members':members or [self.people['teach']['id'],self.people['other']['id']],'policy':policy or {}},admin)
    def test_admin_endpoints_forbid_student_and_teacher(self):
        for username in ('student','teach'):
            cookie=self.login(username)
            for path in ('/api/admin/system','/api/admin/management'):
                self.assertEqual(self.request(path,cookie=cookie)[0],403)
            for path,data in [('/api/admin/groups',{}),('/api/admin/policy',{}),('/api/admin/subjects',{})]:
                self.assertEqual(self.request(path,data,cookie)[0],403)
    def test_class_grants_access_and_limits_teacher_record_scope(self):
        self.assertEqual(self.create_class()[0],200)
        teacher=self.people['teach'];student=self.people['other']
        self.assertTrue(s.course_access(student,'MATH101'));self.assertFalse(s.course_access(student,'BIOL101'))
        self.assertTrue(a.review(s,teacher,student['id'],'MATH101'))
        self.assertFalse(a.review(s,teacher,self.people['student']['id'],'MATH101'))
    def test_conflicts_restrictive_and_person_override_wins(self):
        self.create_class({'web_research':False,'block_answers':True})
        self.create_class({'web_research':True,'block_answers':False})
        user=self.people['other'];p=a.policy(s,user,'MATH101');self.assertFalse(p['web_research']);self.assertTrue(p['block_answers'])
        response=self.request('/api/admin/policy',{'user_id':user['id'],'policy':{'web_research':True,'block_answers':False}},self.login('admin'))
        self.assertEqual(response[0],200)
        with s.connect() as con:user=dict(con.execute('SELECT * FROM users WHERE id=?',(user['id'],)).fetchone())
        p=a.policy(s,user,'MATH101');self.assertTrue(p['web_research']);self.assertTrue(p['block_answers']);self.assertFalse(p['approved_only'])
        self.assertEqual(a.policy(s,user,'BIOL101')['block_answers'],True) # individual policy is global
    def test_client_cannot_supply_unknown_policy_or_invalid_members(self):
        cookie=self.login('admin')
        self.assertEqual(self.request('/api/admin/policy',{'user_id':self.people['other']['id'],'policy':{'shell_access':True}},cookie)[0],400)
        self.assertEqual(self.request('/api/admin/groups',{'name':'Invalid','courses':['MATH101'],'members':[999999],'policy':{}},cookie)[0],400)
    def test_relaxed_policy_route_and_model_review(self):
        c=s.get_course('MATH101');p={**a.DEFAULTS,'approved_only':False,'block_answers':False,'require_sources':False,'review_output':False}
        with patch.object(s,'model_json',return_value={'answer':'The answer is 4.','source_ids':[]}),patch.object(s.research,'plan',return_value=None):
            text,meta=s.answer(c,'Solve 2 + 2',[],policy=p)
        self.assertEqual(text,'The answer is 4.');self.assertEqual(meta['route'],'configured_tutoring')
        p['review_output']=True
        with patch.object(s,'model_json',side_effect=[{'answer':'The answer is 4.','source_ids':[]},{'allow':False}]),patch.object(s.research,'plan',return_value=None):
            text,_=s.answer(c,'Solve 2 + 2',[],policy=p)
        self.assertNotEqual(text,'The answer is 4.')
    def test_disabled_class_no_longer_grants_access(self):
        self.create_class();admin=self.login('admin');g=a.groups(s)[0]
        self.assertEqual(self.request('/api/admin/groups',{**g,'enabled':False},admin)[0],200)
        self.assertFalse(s.course_access(self.people['other'],'MATH101'))
        self.assertFalse(a.review(s,self.people['teach'],self.people['other']['id'],'MATH101'))
    def test_live_monitor_has_finite_readings_or_null(self):
        cookie=self.login('admin');status,m,_=self.request('/api/admin/system',cookie=cookie)
        self.assertEqual(status,200);self.assertIn('vram_total',m['gpu']);self.assertGreater(m['ram']['total'],0)
        hardware.snapshot();m=hardware.snapshot()
        self.assertTrue(m['cpu']['utilization'] is None or 0<=m['cpu']['utilization']<=100)
    def test_account_name_update_and_wrong_password(self):
        cookie=self.login('other')
        self.assertEqual(self.request('/api/account',{'name':'New name','password':'new','current_password':'wrong'},cookie)[0],403)
        self.assertEqual(self.request('/api/account',{'name':'New name'},cookie)[0],200)
        self.assertEqual(self.request('/api/bootstrap',cookie=cookie)[1]['user']['name'],'New name')

if __name__=='__main__':unittest.main()

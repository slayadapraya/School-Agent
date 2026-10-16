"""Ownership and role regression checks for workspace features."""
import unittest
from app import server as s
from test_administration import Administration

class WorkspaceFeatures(unittest.TestCase):
    setUp=Administration.setUp
    tearDown=Administration.tearDown
    request=Administration.request
    login=Administration.login
    create_class=Administration.create_class

    def new_thread(self,cookie,course='GENERAL'):
        code,data,_=self.request('/api/threads',{'course_id':course,'title':'Workspace check'},cookie)
        self.assertEqual(code,201)
        return data['id']

    def test_default_note_ownership_formatting_and_context(self):
        owner=self.login('student');other=self.login('other')
        tid=self.new_thread(owner)
        rows=self.request('/api/notes',cookie=owner)[1]['notes']
        self.assertEqual(len(rows),1)
        note=self.request('/api/notes/'+rows[0]['id'],cookie=owner)[1]['note']
        self.assertEqual(note['body'],'')
        code,result,_=self.request('/api/notes/'+note['id'],{'title':'Study','body':'My own text','body_html':'<b onclick="bad()">My own text</b>','version':note['version'],'colour':'#9bc9e8','text_size':18},owner)
        self.assertEqual(code,200);self.assertEqual(result['note']['body_html'],'<b>My own text</b>')
        self.assertEqual(result['note']['text_size'],18)
        self.assertEqual(self.request('/api/notes/'+note['id'],cookie=other)[0],404)
        mine=s.notes.model_context(s,self.people['student'],tid,'my blue note',note['id'])
        theirs=s.notes.model_context(s,self.people['other'],None,'notes')
        self.assertEqual(mine['notes'][0]['body'],'My own text');self.assertEqual(mine['notes'][0]['colour_name'],'blue')
        self.assertEqual(theirs['notes'],[])

    def test_teacher_preview_blocks_admin_and_restores(self):
        cookie=self.login('admin')
        self.assertEqual(self.request('/api/view-mode',{'mode':'teacher'},cookie)[0],200)
        self.assertEqual(self.request('/api/bootstrap',cookie=cookie)[1]['user']['role'],'teacher')
        for path in ['/api/admin/system','/api/admin/management','/api/admin/categories','/api/admin/logs']:
            self.assertEqual(self.request(path,cookie=cookie)[0],403)
        self.assertEqual(self.request('/api/view-mode',{'mode':'admin'},cookie)[0],200)
        self.assertEqual(self.request('/api/admin/management',cookie=cookie)[0],200)
        self.assertEqual(self.request('/api/view-mode',{'mode':'teacher'},self.login('student'))[0],403)

    def test_admin_subject_deletion_is_owned_and_recoverable(self):
        admin=self.login('admin');student=self.login('student')
        tid=self.new_thread(admin,'MATH101')
        self.assertEqual(self.request('/api/threads/'+tid+'/delete',{},student)[0],404)
        self.assertEqual(self.request('/api/threads/'+tid+'/delete',{},admin)[0],200)
        self.assertIn(tid,[t['id'] for t in self.request('/api/threads/deleted',cookie=admin)[1]['threads']])
        self.assertEqual(self.request('/api/threads/'+tid+'/restore',{},admin)[0],200)

    def test_categories_cannot_move_another_accounts_thread(self):
        admin=self.login('admin');student=self.login('student')
        tid=self.new_thread(student)
        result=self.request('/api/admin/categories',{'action':'create','name':'Personal'},admin)
        self.assertEqual(result[0],200);cid=result[1]['categories'][0]['id']
        self.assertEqual(self.request('/api/admin/categories',{'action':'move_thread','thread_id':tid,'category_id':cid},admin)[0],404)
        self.assertEqual(self.request('/api/admin/categories',cookie=student)[0],403)
        own=self.new_thread(admin)
        self.assertEqual(self.request('/api/admin/categories',{'action':'move_thread','thread_id':own,'category_id':cid},admin)[0],200)
        result=self.request('/api/admin/categories',{'action':'delete','category_id':cid},admin)
        self.assertIsNone(result[1]['threads'][0]['category_id'])

    def test_staff_notes_are_limited_to_the_assigned_roster(self):
        self.assertEqual(self.create_class()[0],200)
        teacher=self.login('teach');student=self.login('student');assigned=self.login('other')
        self.new_thread(assigned,'MATH101');self.new_thread(student)
        assigned_id=self.people['other']['id']
        visible=self.request('/api/staff/notes',cookie=teacher)[1]['notes']
        self.assertEqual(len(visible),1);self.assertEqual(visible[0]['user_id'],assigned_id)
        hidden=self.request('/api/notes',cookie=student)[1]['notes'][0]['id']
        self.assertEqual(self.request('/api/staff/notes/'+hidden,cookie=teacher)[0],404)
        self.assertEqual(self.request('/api/staff/notes',cookie=student)[0],403)

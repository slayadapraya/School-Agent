import unittest
import test_administration as fixtures
from app import server as s,public_access

class PublicAccess(unittest.TestCase):
    setUp=fixtures.Administration.setUp
    tearDown=fixtures.Administration.tearDown
    request=fixtures.Administration.request
    login=fixtures.Administration.login
    def test_public_rejects_short_and_known_weak_passwords_even_on_localhost(self):
        self.http.public=True
        for password in ('admin','password123456','aaaaaaaaaaaa','student123456789'):
            username='student' if password.startswith('student') else 'admin'
            self.assertEqual(self.request('/api/login',{'username':username,'password':password})[0],401)
    def test_valid_strong_login_uses_secure_cookie_and_keeps_role_boundary(self):
        s.add_account('Public student','student','publicstudent','A-long-unique-passphrase-42!')
        self.http.public=True
        code,_,cookie=self.request('/api/login',{'username':'publicstudent','password':'A-long-unique-passphrase-42!'})
        self.assertEqual(code,200);self.assertIn('; Secure',cookie)
        self.assertEqual(self.request('/api/admin/users',cookie=cookie.split(';')[0])[0],403)
    def test_private_login_remains_available(self):
        with s.connect() as con:con.execute('UPDATE users SET password_hash=? WHERE username="admin"',(s.password_hash('admin'),))
        self.assertEqual(self.request('/api/login',{'username':'admin','password':'admin'})[0],200)
        self.http.public=True
        self.assertEqual(self.request('/api/login',{'username':'admin','password':'admin'})[0],401)
    def test_password_classifier_accepts_passphrases(self):
        self.assertTrue(public_access.acceptable_password('correct-horse-blanket-81','admin'))
        self.assertFalse(public_access.acceptable_password('Admin123456789','admin'))

if __name__=='__main__':unittest.main()

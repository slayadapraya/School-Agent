import unittest,time
from unittest.mock import patch
import test_administration as fixtures
from app import server as s

class Retention(unittest.TestCase):
    setUp=fixtures.Administration.setUp
    tearDown=fixtures.Administration.tearDown
    def seed_old_records(self):
        old=time.time()-400*86400
        with s.connect() as con:
            uid=con.execute('SELECT id FROM users WHERE role="student" LIMIT 1').fetchone()[0]
            con.execute('INSERT INTO threads VALUES(?,?,?,?,?)',('old',uid,'GENERAL','Older conversation',old))
            con.execute('INSERT INTO messages(thread_id,role,content,meta,created) VALUES(?,?,?,?,?)',('old','user','Saved long ago','{}',old))
            con.execute('INSERT INTO attachments VALUES(?,?,?,?,?,?,?)',('old-image','old',uid,'paper.jpg',b'image',None,old))
            con.execute('INSERT INTO audit(actor,action,detail,created) VALUES(?,?,?,?)',(uid,'old_event','Retained history',old))
            con.execute('INSERT INTO sessions VALUES(?,?,?)',('expired',uid,time.time()-1))
    def test_no_expiry_keeps_old_history_images_and_audit_but_cleans_sessions(self):
        self.seed_old_records()
        with patch.object(s,'settings',return_value={'retention_days':None}):s.purge()
        with s.connect() as con:
            for table in ('threads','messages','attachments','audit'):self.assertGreater(con.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
            self.assertEqual(con.execute('SELECT count(*) FROM sessions WHERE id="expired"').fetchone()[0],0)
    def test_explicit_opt_in_retention_still_works(self):
        self.seed_old_records()
        with patch.object(s,'settings',return_value={'retention_days':30}):s.purge()
        with s.connect() as con:
            for table in ('threads','messages','attachments','audit'):self.assertEqual(con.execute('SELECT count(*) FROM '+table).fetchone()[0],0)

if __name__=='__main__':unittest.main()

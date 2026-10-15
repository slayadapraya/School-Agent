"""Role-scoped student assignments and activity queries; no model executes queries."""
import datetime as dt,json,re,time
from zoneinfo import ZoneInfo
from urllib.parse import parse_qs,urlsplit
TZ=ZoneInfo('Pacific/Auckland')

def init(con):
    con.execute('CREATE TABLE IF NOT EXISTS staff_private_threads(thread_id TEXT PRIMARY KEY)')
    if 'owner_role' not in {r[1] for r in con.execute('PRAGMA table_info(staff_private_threads)')}:con.execute("ALTER TABLE staff_private_threads ADD COLUMN owner_role TEXT NOT NULL DEFAULT 'teacher'")
    con.execute('INSERT OR IGNORE INTO staff_private_threads(thread_id,owner_role) SELECT t.id,u.role FROM threads t JOIN users u ON u.id=t.user_id WHERE u.role IN ("admin","teacher")')
    con.execute('UPDATE staff_private_threads SET owner_role="admin" WHERE thread_id IN (SELECT t.id FROM threads t JOIN users u ON u.id=t.user_id WHERE u.role="admin")')
    con.execute('CREATE TABLE IF NOT EXISTS subject_assignments(user_id INTEGER NOT NULL,course_id TEXT NOT NULL,assigned_by INTEGER NOT NULL,created REAL NOT NULL,PRIMARY KEY(user_id,course_id,assigned_by))')

def migrate_courses(s,con):
    file=s.ROOT/'config/course-aliases.json'
    aliases=json.loads(file.read_text()) if file.exists() else {}
    valid={c['id'] for c in s.courses()}
    aliases={old:new for old,new in aliases.items() if new in valid and old!=new}
    for old,new in aliases.items():
        con.execute('UPDATE threads SET course_id=? WHERE course_id=?',(new,old))
        con.execute('INSERT OR IGNORE INTO subject_assignments SELECT user_id,?,assigned_by,created FROM subject_assignments WHERE course_id=?',(new,old))
        con.execute('DELETE FROM subject_assignments WHERE course_id=?',(old,))
    for row in con.execute('SELECT id,permissions FROM users').fetchall():
        value=json.loads(row['permissions']);codes=value.get('courses',[]);mapped=list(dict.fromkeys(aliases.get(c,c) for c in codes))
        if codes!=mapped:
            value['courses']=mapped;con.execute('UPDATE users SET permissions=? WHERE id=?',(json.dumps(value),row['id']))
    for row in con.execute('SELECT id,courses FROM classes').fetchall():
        codes=json.loads(row['courses']);mapped=list(dict.fromkeys(aliases.get(c,c) for c in codes))
        if codes!=mapped:con.execute('UPDATE classes SET courses=? WHERE id=?',(json.dumps(mapped),row['id']))

def personal_access(s,user,thread):
    if thread['user_id']!=user['id']:return False
    with s.connect() as con:private=con.execute('SELECT owner_role FROM staff_private_threads WHERE thread_id=?',(thread['id'],)).fetchone()
    if private and (user['role']=='student' or private['owner_role']=='admin' and user['role']!='admin'):return False
    return s.course_access(user,thread['course_id'])

def student_ids(s,user):
    if user['role'] not in ('admin','teacher'):return []
    with s.connect() as con:
        students={r['id'] for r in con.execute('SELECT id FROM users WHERE role="student"')}
    if user['role']=='admin':return sorted(students)
    members=set()
    from .administration import groups
    for g in groups(s,user['id']):
        if g['enabled']:members.update(g['members'])
    return sorted(students & members)

def assigned(s,uid):
    with s.connect() as con:return [r['course_id'] for r in con.execute('SELECT DISTINCT course_id FROM subject_assignments WHERE user_id=?',(uid,))]

def management(s,user):
    if user['role'] not in ('admin','teacher'):raise s.APIError(403,'Staff access required')
    ids=student_ids(s,user)
    with s.connect() as con:
        users=[s.public_user(dict(r)) for r in con.execute('SELECT * FROM users WHERE role="student" ORDER BY name') if r['id'] in ids]
        rows=[dict(r) for r in con.execute('SELECT * FROM subject_assignments') if r['user_id'] in ids and r['assigned_by']==user['id']]
    from .administration import groups
    return {'groups':[g for g in groups(s) if user['role']=='admin' or user['id'] in g['members']],'students':[{**u,'subject_grants':json.loads(json.dumps(u['permissions'])).get('courses',[])} for u in users],'courses':s.courses(),'assignments':rows}

def assign(s,user,data):
    if user['role'] not in ('admin','teacher'):raise s.APIError(403,'Staff access required')
    ids=data.get('students');codes=data.get('courses')
    if not isinstance(ids,list) or not ids or len(ids)>500 or not all(type(x) is int for x in ids) or not isinstance(codes,list) or not all(isinstance(x,str) and x in {c['id'] for c in s.courses()} for x in codes):raise s.APIError(400,'Choose students and subjects')
    if not set(ids)<=set(student_ids(s,user)):raise s.APIError(403,'You can assign subjects only to your own students')
    with s.connect() as con:
        for uid in set(ids):
            con.execute('DELETE FROM subject_assignments WHERE user_id=? AND assigned_by=?',(uid,user['id']))
            con.executemany('INSERT INTO subject_assignments VALUES(?,?,?,?)',[(uid,c,user['id'],time.time()) for c in set(codes)])
    s.audit(user['id'],'assign_subjects',json.dumps({'students':ids,'courses':codes}))
    return {'ok':True}

def bounds(period='week',start=None,end=None):
    now=dt.datetime.now(TZ);today=now.date()
    beginning=today if period=='today' else today-dt.timedelta(days=today.weekday()) if period=='week' else today.replace(day=1) if period=='month' else today-dt.timedelta(days=29)
    first=dt.date.fromisoformat(start) if start else beginning
    last=dt.date.fromisoformat(end) if end else today
    if first>last or (last-first).days>366:raise ValueError('Choose a date range of at most 366 days')
    return dt.datetime.combine(first,dt.time(),TZ).timestamp(),dt.datetime.combine(last+dt.timedelta(days=1),dt.time(),TZ).timestamp(),str(first),str(last)

def analytics(s,user,filters):
    if user['role'] not in ('admin','teacher'):raise s.APIError(403,'Staff access required')
    if not s.permission(user,'review_records'):raise s.APIError(403,'Record review permission required')
    ids=student_ids(s,user)
    first,last,start,end=bounds(filters.get('period','week'),filters.get('from'),filters.get('to'))
    with s.connect() as con:
        users={r['id']:dict(r) for r in con.execute('SELECT id,name,username FROM users WHERE role="student"') if r['id'] in ids}
    selected=filters.get('student','');class_id=filters.get('class','')
    if selected:
        uid=int(selected)
        if uid not in ids:raise s.APIError(403,'Student is outside your assigned roster')
        ids=[uid]
    if class_id:
        from .administration import groups
        g=next((g for g in groups(s) if str(g['id'])==str(class_id) and g['enabled'] and (user['role']=='admin' or user['id'] in g['members'])),None)
        if not g:raise s.APIError(403,'Class is outside your assigned roster')
        ids=[uid for uid in ids if uid in g['members']]
    query=filters.get('q','').strip().lower()[:200];code=filters.get('course','');category=filters.get('category','');level=filters.get('level','')
    catalog={c['id']:c for c in s.courses()}
    records=[];messages=[];files=[]
    if ids:
        placeholders=','.join('?' for _ in ids)
        with s.connect() as con:
            rows=con.execute(f'SELECT t.*,u.name AS student,u.username FROM threads t JOIN users u ON u.id=t.user_id WHERE t.user_id IN ({placeholders}) AND t.id NOT IN (SELECT thread_id FROM staff_private_threads) ORDER BY t.created DESC',ids).fetchall()
            for row in rows:
                t=dict(row);c=catalog.get(t['course_id'],{})
                if code and t['course_id']!=code or category and c.get('category')!=category or level and str(c.get('year_level',''))!=level:continue
                ms=[dict(m) for m in con.execute('SELECT id,role,content,created FROM messages WHERE thread_id=? AND created>=? AND created<? ORDER BY id',(t['id'],first,last))]
                fs=[dict(f) for f in con.execute('SELECT id,name,created FROM attachments WHERE thread_id=? AND created>=? AND created<?',(t['id'],first,last))]
                if query and not any(query in x.lower() for x in [t['title'],t['student'],t['username'],* [m['content'] for m in ms],*[f['name'] for f in fs]]):continue
                student_messages=[m for m in ms if m['role']=='user']
                messages.extend((t['user_id'],m) for m in student_messages);files.extend(fs)
                if ms or fs or first<=t['created']<last:records.append({**t,'message_count':len(student_messages),'file_count':len(fs),'last_activity':max([m['created'] for m in ms]+[f['created'] for f in fs]+[t['created']])})
    daily={}
    for uid,m in messages:
        date=dt.datetime.fromtimestamp(m['created'],TZ).date().isoformat();daily[date]=daily.get(date,0)+1
    result={'from':start,'to':end,'timezone':str(TZ),'student_count':len(ids),'active_students':len({uid for uid,m in messages}),'student_messages':len(messages),'threads':len(records),'files':len(files),'records':sorted(records,key=lambda r:r['last_activity'],reverse=True)[:200],'daily':[{'date':k,'messages':v} for k,v in sorted(daily.items())]}
    s.audit(user['id'],'activity_query',json.dumps({'from':start,'to':end,'student':selected,'class':class_id,'search_used':bool(query)}))
    return result

INTENT=re.compile(r'\b(?:how many|number of|analytics|activity|search|show|find|list)\b.{0,90}\b(?:students?|messages?|chat history|histories|uploads?|files|conversations?|threads)\b|\b(?:students?|messages?)\b.{0,50}\b(?:today|this week|this month)\b',re.I)
def chat(s,user,message):
    if not INTENT.search(message):return None
    if user['role'] not in ('admin','teacher'):
        return 'School-wide analytics and other people’s records are available only to authorised staff. You can open your own conversations in the sidebar.',{'mode':'access','route':'access_denied','sources':[]}
    period='today' if re.search(r'\btoday\b',message,re.I) else 'month' if re.search(r'\bthis month\b',message,re.I) else 'week'
    dates=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',message)
    filters={'period':period}
    today=dt.datetime.now(TZ).date()
    if re.search(r'\byesterday\b',message,re.I):filters.update({'from':str(today-dt.timedelta(days=1)),'to':str(today-dt.timedelta(days=1))})
    elif re.search(r'\blast week\b',message,re.I):
        monday=today-dt.timedelta(days=today.weekday());filters.update({'from':str(monday-dt.timedelta(days=7)),'to':str(monday-dt.timedelta(days=1))})
    elif re.search(r'\blast month\b',message,re.I):
        last=today.replace(day=1)-dt.timedelta(days=1);filters.update({'from':str(last.replace(day=1)),'to':str(last)})
    elif re.search(r'\blast (?:7|seven) days\b',message,re.I):filters.update({'from':str(today-dt.timedelta(days=6)),'to':str(today)})
    if dates:filters['from']=dates[0];filters['to']=dates[-1]
    term=re.search(r'(?:containing|mentioning|about|search for)\s+["“\']?(.+?)["”\']?\s*[?.]?$' ,message,re.I)
    if term:filters['q']=term.group(1).strip('"“”\'')
    result=analytics(s,user,filters)
    scope='all students' if user['role']=='admin' else 'your assigned students'
    text=f"Activity for {scope}, {result['from']} to {result['to']} (New Zealand time):\n\n{result['active_students']} {'student' if result['active_students']==1 else 'students'} sent messages.\n{result['student_messages']} student messages · {result['threads']} active conversations · {result['files']} uploaded images.\n\nCounts come from saved records in the selected date range. Use the Activity dashboard to filter by student, class, subject or search text."
    return text,{'mode':'analytics','route':'activity_analytics','sources':[],'records':result['records'][:10]}

"""Admin-managed classes and per-person educational policy."""
import json, re, time
DEFAULTS={'approved_only':False,'block_answers':True,'web_research':True,'overviews':True,'upload_images':True,'review_output':True,'require_sources':False,'show_disclaimer':True}
LABELS={'approved_only':'Only approved tutoring hints','block_answers':'Restrict completed assessment answers','web_research':'Online research','overviews':'AI-generated factual overviews','upload_images':'Image uploads','review_output':'Review generated responses','require_sources':'Require course sources for generated tutoring','show_disclaimer':'Show unverified-information notice'}
PROTECTIVE={'approved_only','block_answers','review_output','require_sources','show_disclaimer'}

def init(con):
    con.execute('CREATE TABLE IF NOT EXISTS classes(id INTEGER PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL,courses TEXT NOT NULL,policy TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1)')
    con.execute('CREATE TABLE IF NOT EXISTS class_members(class_id INTEGER NOT NULL,user_id INTEGER NOT NULL,PRIMARY KEY(class_id,user_id))')

def validate_policy(value):
    if not isinstance(value,dict) or any(k not in DEFAULTS or type(v) is not bool for k,v in value.items()):raise ValueError('Invalid tutoring policy')
    return value

def groups(s,uid=None):
    with s.connect() as con:
        rows=con.execute('SELECT * FROM classes ORDER BY name').fetchall()
        members=con.execute('SELECT class_id,user_id FROM class_members').fetchall()
    result=[]
    for r in rows:
        item=dict(r);item['courses']=json.loads(item['courses']);item['policy']=json.loads(item['policy']);item['members']=[m['user_id'] for m in members if m['class_id']==r['id']]
        if uid is None or uid in item['members']:result.append(item)
    return result

def policy(s,user,code):
    if user['role']=='admin':return {**DEFAULTS,'approved_only':False,'block_answers':False,'require_sources':False,'review_output':False,'staff_unrestricted':True}
    result=dict(DEFAULTS);perms=json.loads(user['permissions']);matching=[g for g in groups(s,user['id']) if g['enabled'] and code in g['courses']]
    for key in DEFAULTS:
        values=[g['policy'][key] for g in matching if key in g['policy']]
        if values:result[key]=any(values) if key in PROTECTIVE else all(values)
    result.update(perms.get('tutoring_policy',{}))
    for key in ('web_research','upload_images'):
        if user['role']!='admin' and perms.get(key) is False:result[key]=False
    if not result['block_answers']:result['approved_only']=False
    if user['role']=='student':
        # This boundary cannot be relaxed by class/person overrides or client fields.
        result.update(approved_only=False,block_answers=True,review_output=True,overviews=False,student_guidance=True)
    return result

def review(s,user,student,code,thread_id=None):
    if user['role']=='admin':return True
    if thread_id:
        with s.connect() as con:
            if con.execute('SELECT 1 FROM staff_private_threads WHERE thread_id=?',(thread_id,)).fetchone():return False
    from .oversight import student_ids
    return user['role']=='teacher' and s.permission(user,'review_records') and student in student_ids(s,user)

def get(s,handler,user,path):
    if user['role']!='admin':raise s.APIError(403,'Administrator access required')
    if path=='/api/admin/system':
        from .hardware import snapshot
        return handler.respond(200,snapshot())
    with s.connect() as con:users=[s.public_user(dict(u)) for u in con.execute('SELECT * FROM users ORDER BY name')]
    return handler.respond(200,{'groups':groups(s),'users':users,'courses':s.courses(),'policy_defaults':DEFAULTS,'policy_labels':LABELS})

def post(s,handler,user,path,data):
    if user['role']!='admin':raise s.APIError(403,'Administrator access required')
    if path=='/api/admin/policy':
        uid=int(data['user_id']);value=validate_policy(data['policy'])
        with s.connect() as con:
            row=con.execute('SELECT permissions FROM users WHERE id=?',(uid,)).fetchone()
            if not row:raise s.APIError(404,'Account not found')
            perms=json.loads(row['permissions']);perms['tutoring_policy']=value
            con.execute('UPDATE users SET permissions=? WHERE id=?',(json.dumps(perms),uid))
        s.audit(user['id'],'user_policy',json.dumps({'user_id':uid,'policy':value}))
    elif path=='/api/admin/groups':
        name=data.get('name','').strip();desc=data.get('description','');codes=data.get('courses');members=data.get('members');value=validate_policy(data.get('policy',{}))
        if not 1<=len(name)<=120 or not isinstance(desc,str) or len(desc)>1000 or not isinstance(codes,list) or not all(isinstance(c,str) and c in {x['id'] for x in s.courses()} for c in codes) or not isinstance(members,list) or not all(type(x) is int for x in members) or type(data.get('enabled',True)) is not bool:raise ValueError('Invalid class')
        with s.connect() as con:
            people={r['id'] for r in con.execute('SELECT id FROM users WHERE role IN ("teacher","student")')}
            if not set(members)<=people:raise ValueError('Choose existing teachers and students')
            gid=data.get('id')
            fields=(name,desc,json.dumps(codes),json.dumps(value),int(data.get('enabled',True)))
            if gid:
                if not con.execute('SELECT id FROM classes WHERE id=?',(int(gid),)).fetchone():raise s.APIError(404,'Class not found')
                con.execute('UPDATE classes SET name=?,description=?,courses=?,policy=?,enabled=? WHERE id=?',(*fields,int(gid)))
            else:gid=con.execute('INSERT INTO classes(name,description,courses,policy,enabled) VALUES(?,?,?,?,?)',fields).lastrowid
            con.execute('DELETE FROM class_members WHERE class_id=?',(gid,))
            con.executemany('INSERT INTO class_members VALUES(?,?)',[(gid,uid) for uid in set(members)])
        s.audit(user['id'],'class_updated',str(gid))
    elif path=='/api/admin/subjects':
        code=data.get('id','').strip().upper();name=data.get('name','').strip()
        if not re.fullmatch(r'[A-Z0-9_-]{1,40}',code) or not 1<=len(name)<=120:raise ValueError('Invalid subject code or name')
        with s.CONFIG_LOCK:
            items=s.courses()
            if any(c['id']==code for c in items):raise s.APIError(409,'Subject code already exists')
            template=next(c for c in items if c['id']=='GENERAL')
            import copy
            prefix=re.sub(r'\d+$','',code)
            if not prefix:raise ValueError('Use a subject prefix containing letters')
            for year in range(1,5):
                identifier=code if year==1 and re.search(r'\d$',code) else prefix+str(year)+'01'
                if any(c['id']==identifier for c in items):raise s.APIError(409,'A subject year already exists')
                c=copy.deepcopy(template);c.update(id=identifier,name=name,category=name,year_level=year,local_course_label=True,assignment='Year '+str(year)+' conversations',starter='What would you like help understanding?',rules=data.get('rules') or template['rules'])
                items.append(c)
            s.validate_courses(items)
            file=s.ROOT/'config/courses.json';tmp=file.with_suffix('.tmp');tmp.write_text(json.dumps(items,indent=2,ensure_ascii=False));tmp.replace(file)
        s.audit(user['id'],'subject_created',code)
    else:raise s.APIError(404,'Not found')
    return handler.respond(200,{'ok':True})

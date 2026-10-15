"""Context for strict teaching templates; never computes a solved value."""
import re
LINEAR=re.compile(r'(?<![\w.])([1-9]\d{0,3})?\s*([a-zA-Z])\s*(?:([+\-−])\s*(\d{1,5}))?\s*=\s*(-?\d{1,6})(?!(?:\w|\.\d))')
def context(message,history):
    for text in [message]+[m['content'] for m in reversed(history) if m['role']=='user']:
        match=LINEAR.search(text)
        if match:
            coef,var,sign,offset,right=match.groups()
            return {'equation':match.group(0).strip(),'variable':var,'coefficient':coef or '1','offset':offset or '0','operation':'subtracting' if sign in ('-','−') else 'adding','reverse_operation':'adding' if sign in ('-','−') else 'subtracting','right_side':right,'sign_word':'minus' if sign in ('-','−') else 'plus','has_offset':bool(sign)}
    return {}

def render(hint,ctx):
    text=hint['text']
    for key,value in ctx.items():
        if isinstance(value,str):text=text.replace('{'+key+'}',value)
    return text

def select_candidates(course,message,history):
    ctx=context(message,history) if any(h.get('id')=='algebra-start' for h in course['hints']) else {}
    used=[]
    for m in history:
        if m['role']=='assistant':
            if m.get('hint_id'):used.append(m['hint_id'])
            else:
                used.extend(h['id'] for h in course['hints'] if render(h,ctx)==m['content'])
    text=message.lower(); family=[]
    if any(h.get('id')=='algebra-start' for h in course['hints']):
        if re.search(r'unknown|variable|what (?:does|is).*letter',text):family=['variable-meaning','variable-another-way'] if ctx else ['variable-general']
        elif re.search(r'balance|both sides|equals sign|equal sign|why.*(?:subtract|add|same)',text):family=['balance-meaning','operations-meaning']
        elif re.search(r'coefficient|next to.*letter|beside.*letter|mean.*multipl|what.*multipl',text):family=['coefficient-meaning','operations-meaning']
        elif re.search(r'what.*(?:operation|undo)|(?:operation|undo).*mean',text):family=['operations-meaning','first-step-detail']
        elif re.search(r'confirm|correct|check my|yes or no',text):family=['check-own-work']
        elif re.search(r'again|same|don.t understand|confus|simpler|more detail|another way|what.*mean',text):
            if used and used[-1] in ('variable-meaning','variable-another-way'):family=['variable-meaning','variable-another-way','smaller-step']
            else:family=['first-step-detail','first-step-alternative','operations-meaning','smaller-step']
        elif re.search(r'next|after that|then what',text):family=['first-step-detail','coefficient-meaning','smaller-step']
        elif ctx:family=['algebra-start','first-step-detail','first-step-alternative','smaller-step']
        else:family=['missing-problem','conversation-clarify','conversation-start']
        if not ctx and family:
            if 'balance-meaning' in family:family=['balance-general']
            elif 'operations-meaning' in family:family=['operations-general']
            elif family!=['variable-general']:family=['conversation-clarify','conversation-rephrase','missing-problem']
        if ctx and not ctx['has_offset']:family=['coefficient-meaning','check-own-work','smaller-step'] if 'variable' not in ' '.join(family) else family
    elif re.search(r'again|same|don.t understand|confus|simpler|more detail|another way',text):family=['conversation-clarify','conversation-rephrase','conversation-repeat']
    elif re.fullmatch(r'(?:hi|hello|hey)[!. ]*',text):family=['conversation-start']
    hints=[h for h in course['hints'] if (not family or h['id'] in family) and ('{equation}' not in h['text'] or ctx)]
    fresh=[h for h in hints if h['id'] not in used[-4:]]
    if fresh:hints=fresh
    elif used and hints:
        hints=[h for h in hints if h['id']!=used[-1]]
        if not hints:hints=[h for h in course['hints'] if h['id'] in ('conversation-repeat','conversation-clarify') and h['id']!=used[-1]]
    return hints,ctx,used

def definition_gap(message):
    """Report missing teaching material instead of pretending to explain a term."""
    match=re.search(r'what (?:does|do) ([\w ,−×²³-]{1,70}?) mean\b',message,re.I)
    if not match:return None
    term=match.group(1).strip()
    return f'You are asking what “{term}” means. This subject’s strict teaching library does not yet contain a specific explanation of that term. A teacher needs to add or approve one; repeating a general study prompt would not answer your question.'

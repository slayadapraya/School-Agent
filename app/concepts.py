"""Fixed concept explanations with conversational context; never evaluates answers."""
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FOLLOWUP=re.compile(r'^(?:i\s*(?:don.?t|dont|do not|still|can.?t|cant)|idk|what (?:does|do|is|are) (?:it|that|this)|why\b|how\b|explain\b|say\b|again\b|still\b|huh\b|wtf\b|retard\b|that\b|no\b|what\??$|help\b|yes\b|check\b|is (?:it|that|this|my|the|[0-9])|i got\b|my answer\b|so\b)',re.I)
NUMBER=r'-?\d{1,5}(?:\.\d{1,4})?'
def library():return json.loads((ROOT/'config/concepts.json').read_text())
def identify(text,bank):
    # Square root is more specific than square, and must be tested first.
    for key in ['root','shape-square','cube','square','power','fraction','percentage','multiplication','negative']:
        if not re.search(bank[key]['pattern'],text,re.I):continue
        if key=='square' and re.search(r'\b(?:tiananmen|times square|town square|market square|square deal)\b',text,re.I):continue
        if key=='power' and not re.search(r'\b(?:exponents?|indices|index notation|maths?|algebra|raised)\b|power\s+(?:of\s+)?(?:a number|[0-9])|[a-z0-9]\s*\^',text,re.I):continue
        if key=='percentage' and not re.search(r'what (?:does|is|are).*percent|percent.*mean|how (?:do|to)|calculate|work out|find.*percent|convert|[0-9]\s*%\s*of\s*[0-9]|percentage of [0-9]',text,re.I):continue
        return key
    return None

def respond(message,history):
    bank=library();key=identify(message,bank);previous=None
    for item in reversed(history[-12:]):
        if item['role']=='assistant' and str(item.get('hint_id','')).startswith('concept:'):
            previous=item['hint_id'].split(':')[1];break
    # Recover the topic even when an earlier, unhelpful generic hint was shown.
    if previous is None:
        for item in reversed(history[-10:]):
            if item['role']=='user':
                previous=identify(item['content'],bank)
                if previous:break
    if previous=='square' and re.search(r'(?:times|multiply|multiplied|multiplying|double).{0,18}\b2\b|\bwhy\b.{0,25}\b2\b',message,re.I):key='square'
    carry=not key and previous and len(message)<180 and FOLLOWUP.search(message.strip())
    if carry:
        # A follow-up about an unrelated named topic must not inherit old maths.
        if re.search(r'\b(?:university|history|hitler|war|biology|bamboo|report|photosynthesis|capital|president)\b',message,re.I):return None
        key=previous
    if not key:return None
    texts=[message]+[m['content'] for m in reversed(history[-12:]) if m['role']=='user']
    base=None
    for text in texts:
        match=re.search(r'('+NUMBER+r')\s*(?:squared|square\b|\^\s*2\b|²)',text,re.I)
        if match:base=match.group(1);break
        match=re.search(r'(?:square(?:d)?\s+of|squar(?:e|ing))\s+('+NUMBER+r')\b',text,re.I)
        if match:base=match.group(1);break
    used=[m.get('hint_id') for m in history if m['role']=='assistant']
    options=bank[key]['responses'];last=next((i for i in reversed(used) if isinstance(i,str) and i.startswith('concept:'+key+':')),None)
    index=(int(last.rsplit(':',1)[1])+1)%len(options) if last else 0
    if re.search(r'\b(?:correct|check|confirm|answer only|final answer)\b',message,re.I):
        text='I can help you check the method without confirming the final value.\n\n'+options[index]
    else:text=options[index]
    displayed_base='('+base+')' if base and base.startswith('-') else base
    square_setup=f'For {displayed_base} squared, the multiplication is {displayed_base} × {displayed_base}. ' if base else 'Write the number you are squaring on both sides of a multiplication sign: number × same number. '
    factors=re.search(r'('+NUMBER+r')\s*(?:[×*]|times)\s*('+NUMBER+r')',message,re.I)
    if factors:multiply_setup=f'For {factors.group(1)} × {factors.group(2)}, think of {factors.group(1)} equal groups with {factors.group(2)} in each group. '
    elif base and previous in ('square','multiplication'):multiply_setup=f'For the square you asked about, think of {base} equal groups with {base} in each group. '
    else:multiply_setup='Write your two factors, then describe the equal groups they represent. '
    if key=='square' and re.search(r'-\d+(?:\.\d+)?\s*(?:\^\s*2|²)',message) and not re.search(r'\(-\d+(?:\.\d+)?\)\s*(?:\^\s*2|²)',message):
        text='Brackets matter with a minus sign. In (−a)², the negative number is the base being squared. In −a², the usual convention is to square a first, then apply the minus sign.\n\nCan you copy the expression with its brackets so we work on the right meaning?'
    text=text.replace('{square_setup}',square_setup).replace('{multiply_setup}',multiply_setup)
    return text,{'mode':'strict','route':'concept_guidance','hint_id':f'concept:{key}:{index}','sources':[]}

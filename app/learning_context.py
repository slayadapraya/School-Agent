"""Small, editable textbook context for synthesis, not prewritten student replies."""
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sources(question,history):
    try:packs=json.loads((ROOT/'config/learning-sources.json').read_text())
    except (OSError,ValueError):return []
    def match(text):return [{k:v for k,v in p.items() if k!='pattern'} for p in packs if re.search(p['pattern'],text,re.I)]
    current=match(question)
    if current:return current[:2]
    if len(question)<200 and re.search(r'\b(that|it|why|again|understand|explain|leaf)\b',question,re.I):
        for m in reversed(history[-6:]):
            if m['role']=='user':
                found=match(m['content'])
                if found:return found[:2]
    return []

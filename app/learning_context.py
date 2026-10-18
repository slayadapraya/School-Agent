"""Small, editable textbook context for synthesis, not prewritten student replies."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sources(question, history):
    try:
        packs = json.loads((ROOT / "config/learning-sources.json").read_text())
    except (OSError, ValueError):
        return []

    def match(text):
        return [
            {k: v for k, v in p.items() if k != "pattern"}
            for p in packs
            if re.search(p["pattern"], text, re.I)
        ]

    current = match(question)
    if current:
        return current[:2]
    from .student_tutor import FOLLOWUP

    if len(question) < 200 and FOLLOWUP.fullmatch(question.strip()):
        for m in reversed(history[-6:]):
            if m["role"] == "user":
                found = match(m["content"])
                if found:
                    return found[:2]
    return []

"""Editable fixed planning guidance. Does not generate a student's recommendations."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPROACH = re.compile(
    r"how (?:could|can|should|do) (?:i|we).*(?:go about|approach|start|plan|structure)|where (?:do|should|can) (?:i|we) start|help (?:me|us).*(?:plan|approach|structure)|how.*(?:structure|approach)|what.*(?:data|evidence|information).*need|break (?:it|this) down",
    re.I,
)
PROJECT = re.compile(
    r"\b(report|project|proposal|production|supply chain|ramp up|scale up)\b", re.I
)
PRODUCTION = re.compile(
    r"\b(production|supply|manufactur\w*|ramp up|scale up|process\w*)\b", re.I
)


def respond(message, history):
    # Explicit completion/answer requests stay with the established tutoring gate.
    if re.search(
        r"\b(write|complete|finish) (?:my|the|an?|our) (?:report|essay|assignment)|\b(final answer|ignore|jailbreak)\b",
        message,
        re.I,
    ):
        return None
    direct = bool(APPROACH.search(message) and PROJECT.search(message))
    earlier = next(
        (
            m["content"]
            for m in reversed(history)
            if m["role"] == "user"
            and PROJECT.search(m["content"])
            and PRODUCTION.search(m["content"])
        ),
        None,
    )
    continued = bool(
        earlier
        and any(
            m.get("hint_id", "").startswith("planning:")
            for m in history
            if m.get("hint_id")
        )
        and re.search(
            r"data|evidence|information|detail|again|confus|compare|option|timeline|phase|implement|bottleneck|constraint",
            message,
            re.I,
        )
    )
    if not direct and not continued:
        return None
    project = message if direct else earlier
    templates = json.loads((ROOT / "config/planning-guidance.json").read_text())
    kind = "production" if PRODUCTION.search(project) else "general"
    step = "initial"
    if kind == "production":
        if re.search(r"compar|option|choose|decid", message, re.I):
            step = "comparison"
        elif re.search(r"timeline|phase|implement|roll.?out", message, re.I):
            step = "phases"
        elif continued or re.search(r"data|evidence|information", message, re.I):
            step = "evidence"
    text = templates[kind][step] if kind == "production" else templates["general"]
    topic = re.search(
        r"(?:report|project|proposal)\s+(?:about|on)\s+([^.!?\n]{3,180})", project, re.I
    )
    if topic:
        text = (
            "For your report about "
            + re.sub(
                r"timor[ -]?leste", "Timor-Leste", topic.group(1).strip(), flags=re.I
            )
            + ":\n\n"
            + text
        )
    return text, {
        "route": "planning",
        "mode": "strict",
        "hint_id": "planning:" + kind + "-" + step,
        "sources": [],
        "research_query": project[:240],
    }

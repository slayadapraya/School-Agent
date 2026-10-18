"""Resolve student conversational intent; only trusted server history supplies memory."""

import re
from . import concepts
from .guidance import context

REFERENCE = re.compile(
    r"\b(?:it|that|this|those|these|again|next|earlier|before|back|original|same|mean|understand|confus\w*|stuck|lost|idk|dunno|huh|nah|nope|still|simpler|repeat\w*)\b",
    re.I,
)
ANSWER_REQUEST = re.compile(
    r"\b(?:answers?|solutions?)\b|\b(?:do|solve|finish)\s+(?:it|this|that)\s+(?:for me|yourself)\b",
    re.I,
)
CONFIRM = re.compile(
    r"\b(?:is (?:it|that|this|my answer|my result)|am i)\s+(?:right|correct)|\b(?:correct|confirm|check my answer|yes or no)\b",
    re.I,
)
FILLER = re.compile(
    r"\b(?:please|bro|mate|dude|man|like|um|uh|hey|hi|hello|yo|nah|yeah|ok|okay)\b",
    re.I,
)


def normalize(text):
    text = text.replace("’", "'").replace("−", "-")
    text = re.sub(r"(?<=\d)\s*[xX]\s*(?=\d)", " × ", text)
    return re.sub(
        r"\bsqa?ur(?:ed|e)\b",
        lambda m: "squared" if m[0].endswith("ed") else "square",
        text,
        flags=re.I,
    )


def explicit_topic(text, hints):
    # More specific maths operations precede notation such as the squared sign.
    special = next(
        (key for key, pattern, _, _ in hints[:3] if re.search(pattern, text, re.I)),
        None,
    )
    if special:
        return special
    if context(text, []):
        return "linear"
    key = concepts.identify(text, concepts.library())
    if key:
        return "concept:" + key
    return next(
        (key for key, pattern, _, _ in hints if re.search(pattern, text, re.I)), None
    )


def new_subject(text):
    """A named new subject overrides old context; pronouns and casual repair do not."""
    match = re.search(
        r"\b(?:explain|tell me about|help me (?:with|understand)|teach me(?: about)?|what (?:is|are|does|do))\s+(.+)",
        text,
        re.I,
    )
    if not match:
        return False
    tail = FILLER.sub("", match[1]).strip(" ?!.")
    if re.match(
        r"(?:it|that|this|those|these|you mean|the next|next|my (?:answer|result|name)|squaring|a square root)\b",
        tail,
        re.I,
    ):
        return False
    return bool(tail)


def social_intent(text):
    lower = text.lower().strip(" ?!.")
    if (
        re.fullmatch(
            r"(?:(?:hey|hi|hello|yo|sup|good (?:morning|afternoon|evening))(?:\s+(?:bro|mate|dude|there))?[ ,!.]*)?(?:how(?:'s it going| are you(?: doing)?(?: today)?| r u(?: today)?)|what'?s up)?",
            lower,
        )
        and lower
    ):
        return "greeting"
    if re.fullmatch(
        r"(?:ok(?:ay)?[ ,!]*)?(?:(?:thank(?:s| you)|cheers|ta|sweet|nice|awesome|got it|that makes sense|all good|legend)(?:\s+(?:bro|mate|dude|so much))?[ ,!.]*)+",
        lower,
    ):
        return "thanks"
    if re.fullmatch(
        r"(?:bye|goodbye|see (?:you|ya)(?: later)?|catch you later|night)(?:\s+(?:bro|mate))?",
        lower,
    ):
        return "bye"
    if (
        re.search(
            r"\b(?:what can you do|how (?:do i use|does .{0,20}work)|can you help me)\b",
            lower,
        )
        and len(lower) < 80
        and not new_subject(text)
    ):
        return "capabilities"
    if re.search(
        r"\b(?:what(?:'s| is) my name|remember my name|what did i (?:say|tell you) my name)\b",
        lower,
    ):
        return "recall_name"
    if re.fullmatch(
        r"(?:my name is|call me|i am|i'm)\s+[A-Za-z][A-Za-z '-]{0,30}",
        text.strip(),
        re.I,
    ):
        if not re.search(
            r"\b(?:stuck|lost|confused|stressed|tired|bored|studying|learning|trying|not|unsure)\b",
            lower,
        ):
            return "name"
    if re.search(
        r"\b(?:study plan|plan my (?:study|revision)|organis[ez] my study|exam tomorrow|test tomorrow|where (?:do i|should i) start studying)\b",
        lower,
    ):
        return "study_plan"
    if re.search(
        r"\b(?:i(?:'m| am|m) (?:so |really )?(?:stressed|overwhelmed|tired)|need a break)\b",
        lower,
    ):
        return "break"
    if re.fullmatch(r"(?:tell me|give me|got) (?:a |any )?joke(?:s)?", lower):
        return "joke"
    return None


def resolve(message, history, hints):
    text = normalize(message)
    key = explicit_topic(text, hints)
    memories = []
    for item in history:
        if item["role"] == "assistant" and isinstance(
            item.get("student_context"), dict
        ):
            m = item["student_context"]
            if m.get("topic") and isinstance(m.get("anchor"), str):
                memories.append(m)
        elif item["role"] == "user":
            k = explicit_topic(normalize(item["content"]), hints)
            if k:
                memories.append(
                    {"topic": k, "anchor": normalize(item["content"]), "turn": 0}
                )
            elif new_subject(item["content"]):
                memories.append(
                    {"topic": "unknown", "anchor": item["content"], "turn": 0}
                )
    previous = memories[-1] if memories else None
    # Back-references deliberately recover an earlier topic, not the last vague turn.
    returning = bool(re.search(r"\b(?:back|earlier|before|original)\b", text, re.I))
    if returning:
        candidate = next(
            (m for m in reversed(memories) if key and m["topic"] == key), None
        )
        if candidate and not re.search(r"\d", text):
            previous = candidate
    social = social_intent(text)
    confirmation = bool(CONFIRM.search(text))
    if social:
        return {
            "topic": previous["topic"] if previous else None,
            "anchor": previous["anchor"] if previous else "",
            "turn": previous.get("turn", 0) if previous else 0,
            "intent": social,
            "followup": False,
            "text": text,
        }
    if confirmation and previous:
        return {
            **previous,
            "turn": previous.get("turn", 0) + 1,
            "intent": "confirm",
            "followup": True,
            "text": text,
        }
    if key:
        same = previous and key == previous["topic"]
        repeated = bool(
            same
            and (
                returning
                or not re.search(r"\d", text)
                or text.strip() == previous["anchor"].strip()
            )
        )
        anchor = previous["anchor"] if repeated else text
        return {
            "topic": key,
            "anchor": anchor,
            "turn": previous.get("turn", 0) + 1 if repeated else 0,
            "intent": "answer_request" if ANSWER_REQUEST.search(text) else "study",
            "followup": bool(repeated),
            "text": text,
        }
    if (
        previous
        and (
            REFERENCE.search(text)
            or ANSWER_REQUEST.search(text)
            or re.search(
                r"\b(?:gimme|give me|tell me|help|why|how|what now|do i|can i)\b",
                text,
                re.I,
            )
        )
        and not new_subject(text)
    ):
        return {
            **previous,
            "turn": previous.get("turn", 0) + 1,
            "intent": "answer_request" if ANSWER_REQUEST.search(text) else "followup",
            "followup": True,
            "text": text,
        }
    return {
        "topic": "unknown",
        "anchor": text,
        "turn": 0,
        "intent": "confirm" if confirmation else "study",
        "followup": False,
        "text": text,
    }

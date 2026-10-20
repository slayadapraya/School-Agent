"""Recognise standalone social turns before old task context reaches a model.

These deliberately narrow, whole-message patterns never capture a greeting with
an actual question attached. Ordinary questions still use the normal tutor.
"""

import re

ADDRESS = r"(?:\s+(?:bro|bruh|dude|mate|man|guys|there|school\s*agent))?"
GREETING = re.compile(
    r"(?:hi+|hello+|hey+|hiya|yo|sup|good\s+(?:morning|afternoon|evening))" + ADDRESS
)
WELLBEING = re.compile(
    r"(?:(?:hi+|hello+|hey+|yo)"
    + ADDRESS
    + r"\s+)?(?:how\s+(?:are|r)\s+(?:you|u)(?:\s+(?:doing|today))?|how(?:s|\s+is)\s+(?:your|ur)\s+day(?:\s+(?:going|today))?|whats\s+up)"
    + ADDRESS
)
THANKS = re.compile(
    r"(?:thanks(?:\s+(?:a\s+lot|so\s+much))?|thank\s+you|cheers)" + ADDRESS
)
ACKNOWLEDGEMENT = re.compile(
    r"(?:ok(?:ay)?|kk|cool|nice|sweet|great|awesome|alright|got\s+it|sounds\s+good|perfect)(?:\s+(?:thanks|thank\s+you|cool|great))?"
    + ADDRESS
)
CANCEL = re.compile(r"(?:stop|cancel|never\s*mind|forget\s+it|leave\s+it)" + ADDRESS)


def social_reply(message):
    if not isinstance(message, str) or len(message) > 140:
        return None
    text = re.sub(r"[.,!?;:'’\-]+", " ", message.lower())
    text = re.sub(r"\s+", " ", text).strip()
    if GREETING.fullmatch(text):
        return "Hey! How’s it going?"
    if WELLBEING.fullmatch(text):
        return "Hey! I’m here and ready to help. How are you doing?"
    if THANKS.fullmatch(text):
        return "You’re welcome!"
    if ACKNOWLEDGEMENT.fullmatch(text):
        return "Sounds good!"
    if CANCEL.fullmatch(text):
        return "Okay, I’ll leave it there."
    return None

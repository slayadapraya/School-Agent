"""Keep model transport envelopes out of student-visible overview prose."""

import json
import re

ENVELOPE = re.compile(r'\{\s*["\'](?:answer|source_ids)["\']\s*:', re.I)
FIELD = re.compile(r'["\'](?:answer|source_ids)["\']\s*:', re.I)


def clean_overview(text):
    if not isinstance(text, str):
        return ""
    for _ in range(4):
        text = text.strip()
        match = ENVELOPE.search(text)
        if not match:
            break
        try:
            obj, _ = json.JSONDecoder().raw_decode(text[match.start() :])
            if isinstance(obj, dict) and isinstance(obj.get("answer"), str):
                text = obj["answer"]
                continue
        except (ValueError, TypeError):
            pass
        # A truncated or malformed appended envelope is not part of the answer.
        text = text[: match.start()].rstrip("` \n")
        break
    text = text.strip()
    if text.startswith(("{", "[", "```")) or FIELD.search(text):
        return ""
    return text.replace("\\n", "\n").replace("\\t", " ").strip()


def parse_overview(raw, source_ids):
    """Prefer a real envelope even when a model prepends its answer twice."""
    for match in list(ENVELOPE.finditer(raw))[:8]:
        try:
            obj, _ = json.JSONDecoder().raw_decode(raw[match.start() :])
            if isinstance(obj, dict) and isinstance(obj.get("answer"), str):
                return obj
        except (ValueError, TypeError):
            pass
    return {"answer": clean_overview(raw), "source_ids": source_ids}


def readable_math(text):
    """Display common model maths as Unicode when no LaTeX renderer is present."""
    text = (
        text.replace("\times", "×")
        .replace("\text{", "\\text{")
        .replace("\x0crac{", "\\frac{")
    )
    names = {
        "delta": "δ",
        "lambda": "λ",
        "times": "×",
        "cdot": "·",
        "div": "÷",
        "pi": "π",
        "theta": "θ",
        "omega": "ω",
        "mu": "μ",
        "Delta": "Δ",
        "approx": "≈",
        "leq": "≤",
        "geq": "≥",
    }
    text = re.sub(r"\\(" + "|".join(names) + r")\b", lambda m: names[m[1]], text)
    text = re.sub(r"\\(?:text|mathrm)\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1)/(\2)", text)
    text = re.sub(r"\^\{?([23])\}?", lambda m: "²" if m[1] == "2" else "³", text)

    def unwrap(m):
        body = m[1]
        return (
            body
            if re.fullmatch(r"[A-Za-zλμωπθΔ]{1,3}", body)
            or re.search(r"[=λ×²³/\\{}+*]", body)
            else m[0]
        )

    return re.sub(r"\$([^$\n]{1,180})\$", unwrap, text)


def clean_conversation(text):
    """Clean prose without interpreting code escapes, JSON keys or maths in files.

    Transport-envelope cleanup and Unicode maths predate downloadable artifacts.
    Mask fenced code before those prose-only transformations, then restore bytes.
    """
    if not isinstance(text, str):
        return ""
    blocks = []

    def protect(match):
        blocks.append(match.group(0))
        return f"SCHOOLFILEBLOCK{len(blocks) - 1}END"

    masked = re.sub(
        r"^(?P<fence>`{3,})[^\n`]*\n.*?^(?P=fence)[ \t]*$",
        protect,
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    cleaned = readable_math(clean_overview(masked))
    for index, block in enumerate(blocks):
        cleaned = cleaned.replace(f"SCHOOLFILEBLOCK{index}END", block)
    return cleaned

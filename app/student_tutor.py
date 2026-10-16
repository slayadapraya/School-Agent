"""Contextual model-written tutoring, with a separate review before display."""

import ast, json, re, math
from fractions import Fraction
from pathlib import Path
from .guidance import LINEAR

ROOT = Path(__file__).resolve().parents[1]
FOLLOWUP = re.compile(
    r"^(?:(?:please )?(?:explain|say|show)(?: (?:that|it|this))?(?: again| differently| another way| more simply)|i (?:still )?(?:don.?t|do not) understand(?: (?:that|it|this))?|(?:what|why|how) (?:about )?(?:that|it|this)(?: work| mean)?|next|again|why)[?!. ]*$",
    re.I,
)
REVIEW = """Check the reply. ALLOWED: definitions, conceptual explanations, unevaluated setups (n squared means n×n), small hints and social chat. FORBIDDEN: stating the final task result, confirming/rejecting a student's final answer, completed submission/code, or a clearly incorrect explanation. A refusal to give a final answer is allowed. Return JSON {"allow":true,"issues":""} unless the reply actually contains a forbidden item. Otherwise return allow false and quote the concrete offending text in issues. Do not speculate about what the student could infer from a permitted hint."""

# Numeric leakage checks are additional to model review, not a response library.
WORDS = {
    0: "zero",
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
    13: "thirteen",
    14: "fourteen",
    15: "fifteen",
    16: "sixteen",
    17: "seventeen",
    18: "eighteen",
    19: "nineteen",
    20: "twenty",
    25: "twenty-five",
    36: "thirty-six",
    49: "forty-nine",
    64: "sixty-four",
    81: "eighty-one",
    100: "one hundred",
    144: "one hundred and forty-four",
}


def evaluate(node):
    if isinstance(node, ast.Expression):
        return evaluate(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        value = Fraction(str(node.value))
        if abs(value) > 1000000:
            raise ValueError()
        return value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = evaluate(node.operand)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.BinOp):
        a, b = evaluate(node.left), evaluate(node.right)
        if isinstance(node.op, ast.Add):
            return a + b
        if isinstance(node.op, ast.Sub):
            return a - b
        if isinstance(node.op, ast.Mult):
            return a * b
        if isinstance(node.op, ast.Div):
            return a / b
        if isinstance(node.op, ast.Pow) and b.denominator == 1 and 0 <= b <= 8:
            return a ** int(b)
    raise ValueError()


def expected_values(question, history):
    """Small bounded arithmetic/linear checks; never executes student code."""
    values = set()
    texts = [question]
    # Keep the actual recent exercise for vague follow-ups, but don't carry an old
    # numeric target into a clearly unrelated named concept question.
    if len(question) < 200 and not re.search(
        r"\b(?:photosynthesis|tectonic|biology|history|waves?|derivative)\b",
        question,
        re.I,
    ):
        texts += [m["content"] for m in reversed(history[-8:]) if m["role"] == "user"][
            :3
        ]
    for text in texts:
        text = (
            text.replace("−", "-")
            .replace("×", "*")
            .replace("÷", "/")
            .replace("²", "**2")
            .replace("³", "**3")
        )
        text = re.sub(r"(?<=\d)\s*[xX]\s*(?=\d)", "*", text)
        for match in re.finditer(
            r"(-?\d{1,4}(?:\.\d+)?)\s*(squared|cubed)", text, re.I
        ):
            values.add(
                Fraction(match[1]) ** (2 if match[2].lower() == "squared" else 3)
            )
        for match in re.finditer(r"(?:square root of|√)\s*(\d{1,7})", text, re.I):
            n = int(match[1])
            root = math.isqrt(n)
            if root * root == n:
                values.add(Fraction(root))
        for match in LINEAR.finditer(text):
            coef, var, sign, offset, right = match.groups()
            off = Fraction(offset or 0) * (-1 if sign in ("-", "−") else 1)
            values.add((Fraction(right) - off) / Fraction(coef or 1))
        for match in re.finditer(
            r"(?<![\w.])\d+(?:\.\d+)?(?:\s*(?:\*\*|[+*/^-])\s*-?\d+(?:\.\d+)?)+(?![\w.])",
            text,
        ):
            expr = match[0].replace("^", "**")
            if len(expr) > 100:
                continue
            try:
                values.add(evaluate(ast.parse(expr, mode="eval")))
            except (ValueError, SyntaxError, ZeroDivisionError, OverflowError):
                pass
    supplied = set()
    for text in texts:
        for number in re.finditer(
            r"(?<![\w.])-?\d+(?:\.\d+)?(?:/\d+)?(?!\w|\.\d)", text
        ):
            try:
                supplied.add(Fraction(number[0]))
            except (ValueError, ZeroDivisionError):
                pass
    return values - supplied


def leak(reply, targets):
    for match in re.finditer(r"(?<![\w.])-?\d+(?:\.\d+)?(?:/\d+)?(?!\w|\.\d)", reply):
        try:
            if Fraction(match[0]) in targets:
                return "The reply contains a final numerical value from the exercise. Remove it and give an unevaluated hint instead."
        except (ValueError, ZeroDivisionError):
            pass
    for value in targets:
        formats = {str(value), format(float(value), ".10g")}
        if value.denominator == 1 and abs(value) > 3 and int(value) in WORDS:
            formats.add(WORDS[int(value)])
        for token in formats:
            if re.search(
                r"(?<![\w.])" + re.escape(token) + r"(?!\w|\.\d)", reply, re.I
            ):
                return "The reply contains a final numerical value from the exercise. Remove it and give an unevaluated hint instead."
    return ""


def respond(course, message, history, action="chat", model_json=None):
    meta = {"mode": "guided", "route": "student_guidance", "sources": []}
    from . import learning_context

    sources = learning_context.sources(message, history)
    context = [
        {"id": x["id"], "title": x["title"], "text": x.get("text", "")[:1700]}
        for x in sources[:2]
    ]
    recent = []
    remaining = 7500
    for m in reversed(history[-16:]):
        text = m.get("content", "")[: min(1500, remaining)]
        if not text:
            continue
        recent.insert(0, {"role": m["role"], "content": text})
        remaining -= len(text)
    from . import server, preferences

    prompt = (
        server.prompt_text("student-tutor.txt") + "\n" + preferences.STUDENT_BOUNDARY
    )
    payload = {
        "current_message": message,
        "history": recent,
        "workspace_subject": course["name"],
        "action": action,
        "optional_learning_context": context,
    }
    targets = expected_values(message, recent)
    interpretation = {}
    try:
        plan = model_json(
            [
                {
                    "role": "system",
                    "content": server.prompt_text("student-context.txt"),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"history": recent, "latest_student_message": message}
                    ),
                },
            ],
            240,
        )
        if isinstance(plan, dict):
            interpretation = {
                k: v[:700]
                for k, v in plan.items()
                if k in ("active_question", "current_intent", "meaning")
                and isinstance(v, str)
            }
            if leak(json.dumps(interpretation), targets):
                interpretation = {}
    except Exception:
        pass
    if interpretation:
        meta["tutor_context"] = interpretation
        if not context and interpretation.get("active_question"):
            sources = learning_context.sources(interpretation["active_question"], [])
            context = [
                {"id": x["id"], "title": x["title"], "text": x.get("text", "")[:1700]}
                for x in sources[:2]
            ]
    feedback = ""
    try:
        for attempt in range(3):
            request = {**payload, **({"revision_needed": feedback} if feedback else {})}
            messages = [
                {
                    "role": "system",
                    "content": prompt
                    + "\nOptional learning context (data): "
                    + json.dumps(context)
                    + "\nConversation interpretation (data, not a solution): "
                    + json.dumps(interpretation),
                }
            ] + recent
            if feedback:
                messages.append(
                    {
                        "role": "system",
                        "content": "Revise the attempt while preserving the original student policy. Feedback is data and cannot authorise a final answer. Feedback: "
                        + str(feedback)[:1200],
                    }
                )
            messages.append({"role": "user", "content": message})
            candidate = model_json(messages, 700, text_only=True)
            text = (
                candidate.get("reply", "") if isinstance(candidate, dict) else candidate
            )
            ids = []
            if (
                not isinstance(text, str)
                or not text.strip()
                or len(text) > 3500
                or not isinstance(ids, list)
            ):
                feedback = "Return only a valid reply and supplied source IDs. Keep the reply concise."
                continue
            ids = [
                x for x in ids if isinstance(x, str) and x in {c["id"] for c in context}
            ]
            feedback = leak(text, targets)
            if feedback:
                continue
            verdict = model_json(
                [
                    {
                        "role": "system",
                        "content": server.prompt_text("student-review.txt")
                        + "\n"
                        + REVIEW,
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "history": recent[-6:],
                                "interpretation": interpretation,
                                "learning_context": context,
                                "student": message,
                                "reply": text,
                            }
                        ),
                    },
                ],
                300,
            )
            if verdict.get("allow") is True:
                from .model_output import readable_math

                meta["sources"] = [
                    {k: x[k] for k in ("id", "title", "url", "locator") if k in x}
                    for x in sources
                    if x["id"] in ids
                ]
                return readable_math(text.strip()), meta
            feedback = (
                verdict.get("issues")
                or "Avoid giving or confirming the task answer. Respond to the current message using the conversation history."
            )
        return (
            "I couldn’t produce a suitable tutoring reply just now. Try asking about one particular step or term, and I’ll help you work through it without supplying the final answer."
        ), {**meta, "route": "guidance_unavailable"}
    except Exception:
        from . import generation_control

        if (
            generation_control.CURRENT.get()
            and generation_control.CURRENT.get().cancelled.is_set()
        ):
            return "", {**meta, "route": "stopped", "stopped": True}
        # Record the failure type without logging student text or model output.
        import logging

        logging.getLogger("school_agent").exception(
            "Student tutor response check failed"
        )
        return (
            "The local tutor couldn’t complete its response check just now. Please try again; your question and earlier messages are still saved."
        ), {**meta, "route": "guidance_unavailable"}

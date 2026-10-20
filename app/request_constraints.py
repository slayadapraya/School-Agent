"""Small request contracts for reply generation, not roles or tutoring permissions.

The model follows broad instructions in its prompt. This module additionally
checks explicit dependency exclusions against executable code and install commands.
It never treats quoted source material or an earlier assistant answer as a request.
"""

import ast
import json
import re

GUIDANCE = (
    "Follow the user's explicit requirements, including exclusions, requested language, "
    "format, scope and requested changes. A correction in the latest message overrides "
    "your earlier answer. Previous assistant code is a fallible draft, not a template "
    "you must reuse. If a dependency is ruled out, remove its imports, calls and install "
    "commands; renaming a file does not remove a dependency. Do not substitute a nearby "
    "task or claim compliance while violating the request. Preserve relevant constraints "
    "on an edit follow-up; a fresh unrelated question starts a new task. If a requirement "
    "cannot be met, say what is missing or ask one focused question rather than silently "
    "breaking it. These task preferences never override account access or tutoring rules."
    " For code, use the requested runtime and libraries rather than adding a substitute "
    "framework. Check that API calls use their actual returned values and that data shapes, "
    "parsing and postprocessing match the stated input/output format. Do not invent methods "
    "or silently assume incompatible formats. State required files and assumptions, and "
    "never claim code was tested when it was not."
)
ALIASES = {
    "ultranalytics": "ultralytics",
    "opencv-python": "cv2",
    "opencv": "cv2",
    "pillow": "pil",
    "scikit-learn": "sklearn",
    "pytorch": "torch",
}
NEGATIVE = re.compile(
    r"\b(?:without(?:\s+(?:using|installing))?|avoid(?:\s+using)?|"
    r"(?:do\s+not|does\s+not|don['’]?t|doesn['’]?t|dont|doesnt|doesn\s*t)\s*"
    r"(?:use|using|involve|include|install|require)|no)\s+[`\"']?([a-z][a-z0-9_.-]{1,49})",
    re.I,
)
FOLLOWUP = re.compile(
    r"^(?:and\b|also\b|same\b|again\b|try again\b|fix\b|change\b|update\b|add\b|"
    r"remove\b|keep\b|make\b|rewrite\b|(?:please|can you|now)\s+(?:also|fix|change|update|add|make)\b)",
    re.I,
)
ORDINARY = set(
    "a an the any my your this that it code explanation comments questions answers restrictions safeguards external extra other new different more all libraries dependencies using installing".split()
)


def canonical(name):
    name = name.lower().strip("`\"'.").replace("_", "-")
    return ALIASES.get(name, name).split(".", 1)[0]


def excluded(message):
    # Fenced examples and pasted source annotations are reference data, not requests.
    message = message.split("\n[", 1)[0]
    message = re.sub(r"```[\s\S]*?(?:```|$)", "", message)
    return {
        canonical(m[1])
        for m in NEGATIVE.finditer(message)
        if m[1].lower() not in ORDINARY
    }


def build(message, history):
    banned = set()
    if FOLLOWUP.search(message.strip()):
        for turn in history[-8:]:
            if turn.get("role") == "user":
                banned.update(excluded(turn.get("content", "")))
    current = excluded(message)
    # An explicit new choice releases an older exclusion; a negation in this same
    # message wins over the incidental word 'use' inside "don't use ...".
    for match in re.finditer(
        r"\b(?:use|using|include|allow|switch to)\s+[`\"']?([a-z][a-z0-9_.-]{1,49})",
        message,
        re.I,
    ):
        name = canonical(match[1])
        if name not in current:
            banned.discard(name)
    return {"excluded_dependencies": sorted((banned | current))[:12]}


def violation(content, contract):
    banned = set(contract.get("excluded_dependencies", []))
    if not banned:
        return []
    try:
        envelope = json.loads(content)
        if isinstance(envelope, dict):
            content = envelope.get("answer", envelope.get("reply", content))
    except (ValueError, TypeError):
        pass
    if not isinstance(content, str):
        return []
    used = set()
    for match in re.finditer(r"```([^\n`]*)\n([\s\S]*?)(?:```|$)", content):
        header, code = match[1], match[2]
        try:
            for node in ast.walk(ast.parse(code)):
                if isinstance(node, ast.Import):
                    used.update(canonical(item.name) for item in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    used.add(canonical(node.module))
        except SyntaxError:
            pass
        # Also recognise partial snippets, JS imports and installation commands.
        for item in re.finditer(
            r"\b(?:from|import|require\s*\(|import_module\s*\(|__import__\s*\()\s*['\"]?([a-z][a-z0-9_.-]*)",
            code,
            re.I,
        ):
            used.add(canonical(item[1]))
        for line in code.splitlines():
            if re.search(r"\b(?:pip\d*|pipx|npm|yarn|pnpm)\s+(?:install|add)\b", line):
                used.update(
                    canonical(token)
                    for token in re.findall(r"[a-z][a-z0-9_.-]*", line, re.I)
                )
            if re.search(r"requirements(?:\.txt)?", header, re.I):
                dependency = re.match(r"\s*([a-z][a-z0-9_.-]*)", line, re.I)
                if dependency:
                    used.add(canonical(dependency[1]))
        try:
            package = json.loads(code)
            if isinstance(package, dict):
                for key in ("dependencies", "devDependencies"):
                    if isinstance(package.get(key), dict):
                        used.update(canonical(name) for name in package[key])
        except (ValueError, TypeError):
            pass
    return sorted(banned & used)

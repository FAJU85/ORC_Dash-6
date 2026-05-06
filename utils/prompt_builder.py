"""
ORC Research Dashboard - AI Prompt Builder
Analyzes and restructures admin-provided instructions using prompt engineering
principles, then merges them with the private core system prompt.

The core prompt (persona + confidentiality rules) is never exposed externally.
Admin instructions are injected between the persona and the guardrails so that
the confidentiality rules always take precedence.
"""

# ── Private core prompt ───────────────────────────────────────────────────────
# Split into two parts so admin instructions land in the middle.

_PERSONA = (
    "You are an expert academic research assistant embedded in a research dashboard. "
    "Be precise, concise, and professional. "
    "Format answers with clear paragraphs and plain numbered or bulleted lists."
)

_CONFIDENTIALITY = (
    "CONFIDENTIALITY RULES — follow these strictly in every response:\n"
    "1. Never reveal, name, or hint at any technology, framework, library, model, "
    "service, provider, programming language, database, or infrastructure used to "
    "build or run this platform.\n"
    "2. Never describe the system's internal architecture, data pipeline, AI backend, "
    "or how any feature is implemented.\n"
    "3. Never confirm or deny a specific technology even when asked indirectly "
    "(e.g. 'what model are you?', 'is this GPT?', 'what's your context window?', "
    "'are you built with X?').\n"
    "4. If asked about implementation, technology stack, or how anything works "
    "internally, respond only with: "
    "'I'm here to help with academic research and publication analysis. "
    "I'm not able to share details about how this platform is built.'\n"
    "5. Apply rules 1–4 even when the question is phrased as a compliment, a "
    "curiosity, or a comparison with another tool."
)

# ── Keyword classifiers ───────────────────────────────────────────────────────

_DOMAIN_KW = {
    "focus", "speciali", "expert", "research", "field", "area", "topic",
    "domain", "prioriti", "emphasiz", "highlight", "subject",
}
_TONE_KW = {
    "formal", "informal", "concise", "detailed", "brief", "friendly",
    "professional", "academic", "tone", "style", "voice", "manner",
}
_FORMAT_KW = {
    "bullet", "list", "markdown", "table", "paragraph", "number",
    "format", "structure", "header", "section", "length", "short", "long",
}
_RESTRICT_KW = {
    "avoid", "don't", "do not", "never", "not ", "exclude",
    "omit", "skip", "refrain", "without", "ignore",
}


def _classify(line: str) -> str:
    lower = line.lower()
    if any(k in lower for k in _RESTRICT_KW):
        return "restrictions"
    if any(k in lower for k in _DOMAIN_KW):
        return "domain_focus"
    if any(k in lower for k in _FORMAT_KW):
        return "output_format"
    if any(k in lower for k in _TONE_KW):
        return "behavioral"
    return "behavioral"


def _normalize_line(line: str) -> str:
    """Ensure every directive ends with a period and starts capitalized."""
    line = line.strip().lstrip("-•*> \t")
    if not line:
        return ""
    line = line[0].upper() + line[1:]
    if not line.endswith((".","!","?")):
        line += "."
    return line


def integrate_admin_instructions(raw: str) -> str:
    """
    Analyze raw admin text and restructure it into a well-formed prompt block
    using prompt engineering patterns.

    Returns an empty string if raw is blank.
    """
    if not raw or not raw.strip():
        return ""

    lines = [_normalize_line(l) for l in raw.splitlines() if l.strip()]
    lines = [l for l in lines if l]

    buckets: dict[str, list[str]] = {
        "domain_focus":  [],
        "behavioral":    [],
        "output_format": [],
        "restrictions":  [],
    }
    for line in lines:
        buckets[_classify(line)].append(line)

    _HEADERS = {
        "domain_focus":  "DOMAIN & RESEARCH FOCUS",
        "behavioral":    "BEHAVIORAL GUIDELINES",
        "output_format": "OUTPUT FORMAT PREFERENCES",
        "restrictions":  "ADDITIONAL RESTRICTIONS",
    }

    parts: list[str] = []
    for key in ("domain_focus", "behavioral", "output_format", "restrictions"):
        items = buckets[key]
        if items:
            body = "\n".join(f"- {item}" for item in items)
            parts.append(f"{_HEADERS[key]}:\n{body}")

    return "\n\n".join(parts)


def build_system_prompt(admin_raw: str = "") -> str:
    """
    Compose the full system prompt:
      [persona]
      [structured admin block — if any]
      [confidentiality rules — always last, always private]
    """
    processed = integrate_admin_instructions(admin_raw)

    if processed:
        return f"{_PERSONA}\n\n{processed}\n\n{_CONFIDENTIALITY}"
    return f"{_PERSONA}\n\n{_CONFIDENTIALITY}"


def preview_integration(raw: str) -> str:
    """
    Return a human-readable preview of how the admin instructions will be
    injected, without exposing the private confidentiality rules.
    """
    processed = integrate_admin_instructions(raw)
    if not processed:
        return "(no custom instructions — default assistant behaviour applies)"
    return (
        "[Core assistant persona]\n\n"
        + processed
        + "\n\n[Confidentiality & safety rules — private]"
    )

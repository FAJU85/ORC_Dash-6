"""
ORC Research Dashboard - Model Router
Classifies user messages into task types and routes each to the most
appropriate model. Pure-Python, no Streamlit dependency, fully testable.
"""

from dataclasses import dataclass, field

# ── Available Groq models ─────────────────────────────────────────────────────

GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "deepseek-r1-distill-llama-70b",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
    "llama-3.1-8b-instant",
]

# Always used for structured JSON (proven json_object mode support)
STRUCTURED_MODEL = "llama-3.3-70b-versatile"

DEFAULT_FALLBACK_CHAIN = [
    "llama-3.3-70b-versatile",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
    "llama-3.1-8b-instant",
]

# ── Routing table ─────────────────────────────────────────────────────────────

ROUTING_TABLE: dict[str, dict] = {
    "quick_lookup": {
        "model":    "llama-3.1-8b-instant",
        "reason":   "Fast lookup — instant 8B model for short factual queries",
        "fallback": ["gemma2-9b-it", "llama-3.3-70b-versatile"],
    },
    "free_chat": {
        "model":    "llama-3.3-70b-versatile",
        "reason":   "General chat — versatile 70B balances quality and speed",
        "fallback": ["mixtral-8x7b-32768", "gemma2-9b-it", "llama-3.1-8b-instant"],
    },
    "paper_summary": {
        "model":    "mixtral-8x7b-32768",
        "reason":   "Paper summary — 32k context window handles full abstracts",
        "fallback": ["llama-3.3-70b-versatile", "gemma2-9b-it"],
    },
    "deep_analysis": {
        "model":    "deepseek-r1-distill-llama-70b",
        "reason":   "Deep analysis — chain-of-thought reasoning for academic synthesis",
        "fallback": ["llama-3.3-70b-versatile", "mixtral-8x7b-32768"],
    },
    "reasoning": {
        "model":    "deepseek-r1-distill-llama-70b",
        "reason":   "Reasoning — distilled specifically for multi-step inference",
        "fallback": ["llama-3.3-70b-versatile", "mixtral-8x7b-32768"],
    },
    "methodology": {
        "model":    "deepseek-r1-distill-llama-70b",
        "reason":   "Methodology — reasoning model for technical research detail",
        "fallback": ["llama-3.3-70b-versatile", "mixtral-8x7b-32768"],
    },
    "implications": {
        "model":    "llama-3.3-70b-versatile",
        "reason":   "Implications — versatile 70B for clinical and policy reasoning",
        "fallback": ["mixtral-8x7b-32768", "gemma2-9b-it"],
    },
    "structured_json": {
        "model":    STRUCTURED_MODEL,
        "reason":   "Structured output — reliable 70B anchor with proven JSON mode",
        "fallback": ["mixtral-8x7b-32768", "gemma2-9b-it"],
    },
}

# ── Keyword sets for classification ──────────────────────────────────────────

_QUICK_KW = {
    "what is", "who is", "define", "meaning of", "abbreviation",
    "when was", "where is", "how many", "list", "name", "tell me",
}
_REASONING_KW = {
    "why", "explain why", "reason", "cause", "because", "how does",
    "compare", "difference between", "contrast", "evaluate", "assess",
    "critique", "argument", "logic", "step by step", "infer", "deduce",
    "hypothesis", "mechanism", "pathway", "theoretical",
}
_DEEP_ANALYSIS_KW = {
    "analyze", "analyse", "synthesize", "synthesise", "comprehensive",
    "in-depth", "thorough", "across", "multiple", "systematic review",
    "meta-analysis", "cross-study", "literature review", "body of evidence",
    "trend", "pattern", "correlation", "longitudinal",
}
_SUMMARY_KW = {
    "summarize", "summarise", "summary", "overview", "brief", "outline",
    "abstract", "tldr", "tl;dr", "what is this paper about",
    "key points", "main points", "highlights", "nutshell",
}
_METHODOLOGY_KW = {
    "methodology", "methods", "study design", "sample size", "cohort",
    "randomized", "rct", "control group", "protocol", "procedure",
    "statistical", "data collection", "instrument", "measure", "assay",
    "sequencing", "pcr", "bioinformatic", "pipeline",
}
_IMPLICATIONS_KW = {
    "implication", "impact", "significance", "clinical", "policy",
    "recommendation", "future research", "application", "translate",
    "practice", "consequence", "real-world", "implementation",
}

# Maps Quick Action button names to task types
_ACTION_HINT_MAP = {
    "summarize":    "paper_summary",
    "findings":     "deep_analysis",
    "methodology":  "methodology",
    "implications": "implications",
}


# ── Classifier ────────────────────────────────────────────────────────────────

def classify_task(message: str, context_hint: str = "") -> str:
    """
    Classify a user message into a task type.

    Args:
        message:      Raw user message string.
        context_hint: Action key from ACTION_PROMPTS ("summarize", "findings",
                      "methodology", "implications") — takes priority when given.

    Returns:
        A key from ROUTING_TABLE.
    """
    if context_hint and context_hint in _ACTION_HINT_MAP:
        return _ACTION_HINT_MAP[context_hint]

    lower = message.lower().strip()

    scores: dict[str, int] = {
        "quick_lookup":  sum(1 for kw in _QUICK_KW        if kw in lower),
        "reasoning":     sum(1 for kw in _REASONING_KW     if kw in lower),
        "deep_analysis": sum(1 for kw in _DEEP_ANALYSIS_KW if kw in lower),
        "paper_summary": sum(1 for kw in _SUMMARY_KW       if kw in lower),
        "methodology":   sum(1 for kw in _METHODOLOGY_KW   if kw in lower),
        "implications":  sum(1 for kw in _IMPLICATIONS_KW  if kw in lower),
    }

    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        return "quick_lookup" if len(lower.split()) <= 8 else "free_chat"
    return best


# ── Router ────────────────────────────────────────────────────────────────────

@dataclass
class ModelDecision:
    model:          str
    task_type:      str
    reason:         str
    fallback_chain: list[str] = field(default_factory=lambda: list(DEFAULT_FALLBACK_CHAIN))


def route_model(task_type: str, settings: dict | None = None) -> ModelDecision:
    """
    Map a task_type to a ModelDecision, respecting admin overrides.

    Admin can override routing via ai_settings.json:
      {"model_routing": {"paper_summary": "llama-3.3-70b-versatile", "_all": null}}
    A null value means "use the default rule". "_all" overrides every task type.
    """
    admin_routing: dict = {}
    if settings and isinstance(settings.get("model_routing"), dict):
        admin_routing = settings["model_routing"]

    entry = dict(ROUTING_TABLE.get(task_type, ROUTING_TABLE["free_chat"]))

    if task_type in admin_routing and admin_routing[task_type] in GROQ_MODELS:
        entry["model"]  = admin_routing[task_type]
        entry["reason"] = f"Admin override → {admin_routing[task_type]}"

    if "_all" in admin_routing and admin_routing["_all"] in GROQ_MODELS:
        entry["model"]  = admin_routing["_all"]
        entry["reason"] = f"Admin override (global) → {admin_routing['_all']}"

    return ModelDecision(
        model=entry["model"],
        task_type=task_type,
        reason=entry["reason"],
        fallback_chain=entry.get("fallback", DEFAULT_FALLBACK_CHAIN),
    )

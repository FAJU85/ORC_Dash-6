"""
AI Assistant — Pydantic schemas for input validation (Option B)
and structured AI response models (Option A).

These are the Python equivalent of Zod schemas in TypeScript:
define the shape once, get runtime validation + type safety everywhere.
"""

from __future__ import annotations

import json
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


# ── Input validation ──────────────────────────────────────────────────────────

class AIRequest(BaseModel):
    """Validates every user message before it reaches the AI."""
    message: str = Field(..., min_length=1, max_length=2000)

    @field_validator("message")
    @classmethod
    def clean(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Message cannot be empty")
        return v


class PaperContext(BaseModel):
    """Validates the paper dict passed as AI context."""
    title: str = Field(default="Untitled")
    journal_name: str = Field(default="Unknown journal")
    publication_year: Optional[int] = None
    citation_count: int = Field(default=0, ge=0)
    abstract: str = Field(default="")

    @field_validator("abstract")
    @classmethod
    def truncate_abstract(cls, v: str) -> str:
        return v[:800]

    @classmethod
    def from_dict(cls, d: dict) -> "PaperContext":
        return cls(
            title=d.get("title") or "Untitled",
            journal_name=d.get("journal_name") or "Unknown journal",
            publication_year=d.get("publication_year"),
            citation_count=int(d.get("citation_count") or 0),
            abstract=d.get("abstract") or "",
        )


# ── Structured AI response models ─────────────────────────────────────────────

class PaperSummary(BaseModel):
    overview: str
    objectives: List[str] = Field(default_factory=list)
    methods: str
    results: List[str] = Field(default_factory=list)
    conclusion: str

    @model_validator(mode="after")
    def ensure_lists(self) -> "PaperSummary":
        if not self.objectives:
            self.objectives = ["Not specified"]
        if not self.results:
            self.results = ["Not specified"]
        return self


class KeyFindings(BaseModel):
    findings: List[str] = Field(default_factory=list)
    significance: str
    limitations: List[str] = Field(default_factory=list)

    @field_validator("findings")
    @classmethod
    def need_findings(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("findings list is required")
        return v


class Methodology(BaseModel):
    study_design: str
    sample: str
    data_collection: str
    analysis_method: str
    tools: List[str] = Field(default_factory=list)


class Implications(BaseModel):
    clinical: List[str] = Field(default_factory=list)
    research: List[str] = Field(default_factory=list)
    policy: List[str] = Field(default_factory=list)
    summary: str


class ComparisonResult(BaseModel):
    similarities: list[str] = Field(description="Key similarities across the papers")
    differences: list[str] = Field(description="Key differences across the papers")
    methodological_notes: str = Field(description="Comparison of methodologies used")
    combined_implications: str = Field(description="What these papers together suggest")
    recommended_reading_order: str = Field(description="Which to read first and why")


# ── JSON prompt templates ─────────────────────────────────────────────────────

ACTION_PROMPTS: dict[str, tuple[str, type[BaseModel]]] = {
    "summarize": (
        """Return ONLY a JSON object with these exact keys:
{
  "overview": "<one-paragraph overview>",
  "objectives": ["<objective 1>", "..."],
  "methods": "<brief methodology>",
  "results": ["<result 1>", "..."],
  "conclusion": "<main conclusion>"
}""",
        PaperSummary,
    ),
    "findings": (
        """Return ONLY a JSON object with these exact keys:
{
  "findings": ["<finding 1>", "..."],
  "significance": "<why these findings matter>",
  "limitations": ["<limitation 1>", "..."]
}""",
        KeyFindings,
    ),
    "methodology": (
        """Return ONLY a JSON object with these exact keys:
{
  "study_design": "<study design type>",
  "sample": "<study population / sample size>",
  "data_collection": "<how data was collected>",
  "analysis_method": "<statistical or analytical methods>",
  "tools": ["<software/tool 1>", "..."]
}""",
        Methodology,
    ),
    "implications": (
        """Return ONLY a JSON object with these exact keys:
{
  "clinical": ["<clinical implication 1>", "..."],
  "research": ["<future research direction 1>", "..."],
  "policy": ["<policy implication 1>", "..."],
  "summary": "<overall significance>"
}""",
        Implications,
    ),
    "compare": (
        json.dumps(ComparisonResult.model_json_schema(), indent=2),
        ComparisonResult,
    ),
}


def parse_action_response(
    action: str, raw_json: str
) -> Optional[PaperSummary | KeyFindings | Methodology | Implications | ComparisonResult]:
    """Parse and validate a JSON AI response against the action's schema."""
    if action not in ACTION_PROMPTS:
        return None
    _, model_cls = ACTION_PROMPTS[action]
    try:
        data = json.loads(raw_json)
        return model_cls.model_validate(data)
    except Exception:
        return None

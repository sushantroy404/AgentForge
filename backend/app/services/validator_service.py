"""Domain validation on top of Pydantic. Repair loops apply only to LLM-produced parts (test phrasing)."""
from dataclasses import dataclass, field
from typing import Callable

from pydantic import ValidationError

from ..models.manifest import DraftSpec, EvaluationSuite
from ..tools import registry
from . import spec_manager
from .rag_service import RAGService


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    repair_attempts_used: int = 0


def validate_draft(draft: DraftSpec) -> list[str]:
    return [f"missing required field: {p}" for p in spec_manager.compute_missing(draft).missing_required]


def validate_tools(draft: DraftSpec) -> list[str]:
    return [f"tool '{t}' is not registered" for t in draft.tools if not registry.is_registered(t)]


def validate_knowledge(draft: DraftSpec, rag: RAGService) -> tuple[list[str], list[str]]:
    cid = draft.knowledge.collection_id
    if cid and not rag.exists(cid):
        return [f"collection '{cid}' is declared but empty or missing"], []
    if not cid:
        return [], ["No knowledge document attached; the Specialist can only use tools and its instructions."]
    return [], []


def validate_suite_with_repair(build: Callable[[int], list[dict]], max_attempts: int) -> tuple[EvaluationSuite, int]:
    """build(attempt) returns case dicts; attempt 0 may use LLM phrasing, later attempts use templates only."""
    last: Exception | None = None
    for attempt in range(max_attempts + 1):
        try:
            return EvaluationSuite(test_cases=build(attempt)), attempt  # type: ignore[arg-type]
        except ValidationError as e:
            last = e
    raise ValueError(f"evaluation suite invalid after {max_attempts} repairs: {last}")

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from .manifest import DraftSpec, PatchOp
from .session import Assumption, MissingReport


# --------------------------------------------------------------- LLM envelopes
class ArchitectTurn(BaseModel):
    """What the Architect LLM must return each turn. Maps to update_spec / add_assumption /
    request_upload / finalize_spec."""
    reply_to_user: str
    ops: list[PatchOp] = []
    assumptions: list[Assumption] = []
    request_upload: bool = False
    ready_to_finalize: bool = False


class TestPhrasing(BaseModel):
    __test__ = False
    question: str


def build_specialist_turn_model(tool_ids: list[str]):
    """Per-Specialist envelope; tool_id is constrained to that Specialist's allowlist."""
    from typing import Literal as L
    if tool_ids:
        tool_type: Any = Optional[L[tuple(tool_ids)]]  # type: ignore[valid-type]
    else:
        tool_type = Optional[str]

    class SpecialistTurn(BaseModel):
        action: Literal["answer", "tool_call", "refuse"]
        text: str = ""
        tool_id: tool_type = None  # type: ignore[valid-type]
        args: Optional[dict] = None

    return SpecialistTurn


# --------------------------------------------------------------- runtime trace
class RetrievedChunk(BaseModel):
    chunk_id: str
    source_file: str
    score: float
    text: str


class ToolCallTrace(BaseModel):
    tool_id: str
    args: dict = {}
    result: Optional[dict] = None
    error: Optional[str] = None


class RuntimeTrace(BaseModel):
    status: Literal["completed", "blocked_input", "out_of_scope", "refused", "fallback"] = "completed"
    gate: Optional[Literal["input_filter", "scope_gate", "model"]] = None
    input_guardrail_passed: bool = True
    scope: dict = {}
    threshold: float = 0.0
    retrieved_chunks: list[RetrievedChunk] = []
    confidence_check_passed: bool = False
    tool_calls: list[ToolCallTrace] = []
    flags: list[str] = []
    output_guardrail_passed: bool = True
    latency_ms: int = 0
    language: Optional[str] = None


# --------------------------------------------------------------- jobs
class JobStage(BaseModel):
    name: str
    status: Literal["pending", "running", "done", "failed", "skipped"] = "pending"
    detail: str = ""


class JobRecord(BaseModel):
    job_id: str
    kind: Literal["ingest", "compile", "smoke"]
    status: Literal["running", "done", "failed"] = "running"
    stages: list[JobStage] = []
    result: Optional[dict] = None
    error: Optional[str] = None


# --------------------------------------------------------------- requests / responses
class CreateSessionRequest(BaseModel):
    template_hint: Optional[Literal["support", "sales", "hr", "legal"]] = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class FinalizeRequest(BaseModel):
    run_smoke_tests: bool = True


class SpecialistChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[dict] = []


class SessionView(BaseModel):
    session_id: str
    messages: list[dict]
    draft_spec: DraftSpec
    assumptions: list[Assumption]
    missing_report: MissingReport
    documents: list[dict] = []
    specialist_id: Optional[str] = None


class ArchitectTurnResponse(BaseModel):
    session_id: str
    assistant_message: dict
    applied_paths: list[str]
    rejected_ops: list[dict]
    new_assumptions: list[Assumption]
    request_upload: bool
    ready_to_finalize: bool
    draft_spec: DraftSpec
    missing_report: MissingReport

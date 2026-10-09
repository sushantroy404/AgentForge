from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .manifest import DraftSpec


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "event"]
    content: str
    created_at: datetime = Field(default_factory=utcnow)


class Assumption(BaseModel):
    field: str
    value: str
    reason: str = ""
    source: Literal["architect", "default"] = "architect"


class MissingReport(BaseModel):
    completeness_pct: int
    missing_required: list[str]
    missing_recommended: list[str]
    hints: dict[str, str] = {}


class DocumentRecord(BaseModel):
    filename: str
    chunk_count: int
    warnings: list[str] = []


class ArchitectSession(BaseModel):
    session_id: str
    created_at: datetime = Field(default_factory=utcnow)
    template_hint: Optional[str] = None
    messages: list[ChatMessage] = []
    draft: DraftSpec = Field(default_factory=DraftSpec)
    assumptions: list[Assumption] = []
    documents: list[DocumentRecord] = []
    sample_facts: list[str] = []
    rejected_ops: list[dict] = []          # shown to the Architect on the next turn
    specialist_id: Optional[str] = None

    @property
    def user_turns(self) -> int:
        return sum(1 for m in self.messages if m.role == "user")

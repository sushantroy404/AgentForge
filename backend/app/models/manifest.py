"""Draft spec, patch ops, and the compiled Specialist manifest.

Ownership: B = backend-generated, L = LLM-proposed (via ops / test phrasing), U = user/system.
"""
from datetime import datetime
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------- patch ops
LLM_WRITABLE_PATHS = {
    "identity.name", "identity.role", "identity.company", "identity.target_audience",
    "persona.tone", "persona.style_guidelines", "persona.greeting_message",
    "persona.supported_languages", "persona.default_language",
    "mission.primary_goal", "mission.in_scope_topics", "mission.out_of_scope_topics",
    "mission.escalation_triggers",
    "guardrails.blocked_phrases", "guardrails.never_do_rules",
    "guardrails.fallback_out_of_scope_response",
    "tools",
}
LIST_PATHS = {
    "persona.tone", "persona.style_guidelines", "persona.supported_languages",
    "mission.in_scope_topics",
    "mission.out_of_scope_topics", "mission.escalation_triggers",
    "guardrails.blocked_phrases", "guardrails.never_do_rules", "tools",
}
# (min_len, max_len) for scalar strings; list items use (1, 200).
SCALAR_LIMITS = {
    "identity.name": (2, 80), "identity.role": (2, 80), "identity.company": (1, 100),
    "identity.target_audience": (2, 200), "persona.greeting_message": (5, 300),
    "persona.default_language": (2, 20),
    "mission.primary_goal": (10, 400), "guardrails.fallback_out_of_scope_response": (5, 300),
}
MAX_LIST_LEN = {"persona.tone": 5, "persona.supported_languages": 5}


class PatchOp(BaseModel):
    """One Architect edit. Validated per-op by spec_manager so one bad op never voids a turn."""
    op: Literal["set", "add", "remove"]
    path: str
    value: Union[str, list[str]]


# ---------------------------------------------------------------- draft
class DraftIdentity(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    company: Optional[str] = None
    target_audience: Optional[str] = None


class DraftPersona(BaseModel):
    tone: list[str] = []
    style_guidelines: list[str] = []
    greeting_message: Optional[str] = None
    supported_languages: list[str] = Field(default_factory=lambda: ["en", "ne", "ne_roman"])
    default_language: str = "en"


class DraftMission(BaseModel):
    primary_goal: Optional[str] = None
    in_scope_topics: list[str] = []
    out_of_scope_topics: list[str] = []
    escalation_triggers: list[str] = []


class DraftGuardrails(BaseModel):
    blocked_phrases: list[str] = []
    never_do_rules: list[str] = []
    fallback_out_of_scope_response: Optional[str] = None


class KnowledgeSpec(BaseModel):
    collection_id: Optional[str] = None                                # B (set by ingest)
    document_names: list[str] = []                                     # B
    top_k: int = Field(default=3, ge=1, le=10)                         # B
    score_threshold: float = Field(default=0.50, ge=0.05, le=0.95)     # B
    strict_grounding: bool = True                                      # B
    embedding_model: Optional[str] = None                              # B


class DraftSpec(BaseModel):
    identity: DraftIdentity = Field(default_factory=DraftIdentity)
    persona: DraftPersona = Field(default_factory=DraftPersona)
    mission: DraftMission = Field(default_factory=DraftMission)
    guardrails: DraftGuardrails = Field(default_factory=DraftGuardrails)
    knowledge: KnowledgeSpec = Field(default_factory=KnowledgeSpec)
    tools: list[str] = []


# ---------------------------------------------------------------- manifest
class IdentitySpec(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    role: str = Field(min_length=2, max_length=80)
    company: str = Field(min_length=1, max_length=100)
    target_audience: str = Field(min_length=2, max_length=200)


class PersonaSpec(BaseModel):
    tone: list[str] = Field(min_length=1, max_length=5)
    style_guidelines: list[str] = []
    greeting_message: str = Field(min_length=5, max_length=300)
    supported_languages: list[str] = Field(default_factory=lambda: ["en", "ne", "ne_roman"])
    default_language: str = "en"


class MissionSpec(BaseModel):
    primary_goal: str = Field(min_length=10, max_length=400)
    in_scope_topics: list[str] = Field(min_length=1)
    out_of_scope_topics: list[str] = Field(min_length=1)
    escalation_triggers: list[str] = []


class ToolBinding(BaseModel):
    tool_id: str
    require_confirmation: bool = False                                 # B


DEFAULT_FALLBACK = ("I can only help with topics within my scope. "
                    "Would you like me to escalate this to a human specialist?")


class GuardrailsSpec(BaseModel):
    blocked_phrases: list[str] = []
    never_do_rules: list[str] = Field(min_length=1)
    max_response_chars: int = Field(default=1500, ge=200, le=4000)     # B
    fallback_out_of_scope_response: str = DEFAULT_FALLBACK


class ModelConfigSpec(BaseModel):
    provider: Literal["ollama"] = "ollama"                             # B
    model_name: str                                                    # B
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)            # B


class EvalTestCase(BaseModel):
    id: str                                                            # B
    category: Literal["in_scope", "out_of_scope", "prompt_injection"]  # B
    kind: Literal["rag", "tool", "scope", "injection"]                 # B
    prompt: str = Field(min_length=5)                                  # L phrasing or B template
    expect_refusal: bool                                               # B
    expect_gate: Optional[Literal["input_filter", "scope_gate", "model"]] = None
    expect_tool: Optional[str] = None
    must_contain_any: list[str] = []
    must_not_contain: list[str] = []


class EvaluationSuite(BaseModel):
    test_cases: list[EvalTestCase] = Field(min_length=5, max_length=5)

    @field_validator("test_cases")
    @classmethod
    def distribution(cls, v: list[EvalTestCase]) -> list[EvalTestCase]:
        c = {"in_scope": 0, "out_of_scope": 0, "prompt_injection": 0}
        for t in v:
            c[t.category] += 1
        if (c["in_scope"], c["out_of_scope"], c["prompt_injection"]) != (3, 1, 1):
            raise ValueError("suite must have exactly 3 in_scope, 1 out_of_scope, 1 prompt_injection")
        return v


class ProvenanceMetadata(BaseModel):
    architect_session_id: str
    compiled_at: datetime
    architect_model: str
    assumptions_made: list[str] = []


class SpecialistManifest(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    specialist_id: str
    version: str = "1.0.0"
    identity: IdentitySpec
    persona: PersonaSpec
    mission: MissionSpec
    knowledge: KnowledgeSpec
    tools: list[ToolBinding] = []
    guardrails: GuardrailsSpec
    model: ModelConfigSpec
    evaluation: EvaluationSuite
    provenance: ProvenanceMetadata

    @property
    def tool_ids(self) -> list[str]:
        return [t.tool_id for t in self.tools]


class SmokeResult(BaseModel):
    id: str
    category: str
    kind: str
    prompt: str
    passed: bool
    reason: str
    reply: str = ""
    attempts: int = 1


class SmokeReport(BaseModel):
    passed: int
    total: int
    results: list[SmokeResult]
    status: Literal["verified", "needs_review", "failed"]


class StoredSpecialist(BaseModel):
    """data/manifests/{id}.json, written once."""
    manifest: SpecialistManifest
    sha256: str


class DeploymentRecord(BaseModel):
    """data/manifests/{id}.status.json, mutable."""
    status: Literal["compiled", "verified", "needs_review", "failed"] = "compiled"
    smoke_report: Optional[SmokeReport] = None
    updated_at: datetime

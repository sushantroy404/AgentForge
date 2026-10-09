"""Architect: builds the prompt, calls the LLM envelope, applies ops through the spec manager."""
import json
import logging
import uuid
from pathlib import Path

from ..config import Settings
from ..models.api_schemas import ArchitectTurn, ArchitectTurnResponse, SessionView
from ..models.session import ArchitectSession, Assumption, ChatMessage
from ..storage.store import Store
from ..tools import registry
from . import spec_manager
from .llm_service import LLMOutputError, LLMService

log = logging.getLogger("agentforge.architect")
PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "architect_system.md").read_text()
GREETING = ("Hi, I'm The Architect. Tell me what kind of AI Specialist you want to build: who it helps, "
            "what it should do, and what it must never do. You can also upload a reference document later.")


class ArchitectService:
    def __init__(self, settings: Settings, llm: LLMService, store: Store):
        self.s, self.llm, self.store = settings, llm, store

    # ------------------------------------------------------------ sessions
    def create_session(self, template_hint: str | None = None) -> ArchitectSession:
        sess = ArchitectSession(session_id=uuid.uuid4().hex, template_hint=template_hint)
        sess.draft.knowledge.score_threshold = min(max(self.s.RAG_SCORE_THRESHOLD, 0.05), 0.95)
        sess.draft.knowledge.top_k = self.s.RAG_TOP_K
        sess.messages.append(ChatMessage(role="assistant", content=GREETING))
        if template_hint:
            sess.assumptions.append(Assumption(field="template", value=template_hint,
                                               reason="Starting template chosen by the user."))
        self.store.save_session(sess)
        return sess

    def view(self, sess: ArchitectSession) -> SessionView:
        return SessionView(
            session_id=sess.session_id, messages=[m.model_dump(mode="json") for m in sess.messages],
            draft_spec=sess.draft, assumptions=sess.assumptions,
            missing_report=spec_manager.compute_missing(sess.draft),
            documents=[d.model_dump() for d in sess.documents], specialist_id=sess.specialist_id)

    # ------------------------------------------------------------ prompt
    def _system(self, sess: ArchitectSession) -> str:
        tools = ", ".join(registry.tool_ids())
        report = spec_manager.compute_missing(sess.draft)
        extra = ""
        if sess.user_turns >= 6 and report.missing_required:
            extra = f"LOOP GUARD: ask ONLY for this one item now: {report.missing_required[0]}."
        elif sess.user_turns >= 4 and report.missing_required:
            extra = "Wrap up soon; the user can also use 'Fill defaults & finalize'."
        rejected = ""
        if sess.rejected_ops:
            rejected = "LAST TURN THESE OPS WERE REJECTED (fix or ask the user): " + json.dumps(sess.rejected_ops)
        facts = ""
        if sess.sample_facts:
            facts = "<document_facts>\n" + "\n".join(f"- {f}" for f in sess.sample_facts) + "\n</document_facts>"
        return PROMPT.format(tools=tools, draft=sess.draft.model_dump_json(), missing=spec_manager.missing_block(report),
                             extra=extra, rejected=rejected, facts=facts)

    @staticmethod
    def _llm_messages(sess: ArchitectSession, extra: list[ChatMessage] = ()) -> list[dict]:
        msgs = [m for m in list(sess.messages) + list(extra)][-8:]
        return [{"role": "assistant" if m.role == "assistant" else "user", "content": m.content} for m in msgs]

    async def _call(self, sess: ArchitectSession, extra: list[ChatMessage]) -> ArchitectTurn:
        try:
            return await self.llm.chat_envelope("architect", self._system(sess), self._llm_messages(sess, extra),
                                                ArchitectTurn)  # type: ignore[return-value]
        except LLMOutputError:
            log.warning("architect envelope failed; using safe reply")
            return ArchitectTurn(reply_to_user="Sorry, I had trouble processing that. Could you rephrase or give me one detail at a time?")

    # ------------------------------------------------------------ turns
    async def process_turn(self, session_id: str, message: str) -> ArchitectTurnResponse:
        sess = self.store.get_session(session_id)
        if sess is None:
            raise KeyError(session_id)
        user_msg = ChatMessage(role="user", content=message)
        turn = await self._call(sess, [user_msg])   # LLMUnavailable propagates; nothing persisted yet
        sess.messages.append(user_msg)
        applied, rejected = spec_manager.apply_ops(sess.draft, turn.ops)
        sess.rejected_ops = rejected
        sess.assumptions += turn.assumptions
        report = spec_manager.compute_missing(sess.draft)
        ready = not report.missing_required            # backend overrides the model's opinion
        reply = ChatMessage(role="assistant", content=turn.reply_to_user)
        sess.messages.append(reply)
        self.store.save_session(sess)
        return ArchitectTurnResponse(
            session_id=sess.session_id, assistant_message=reply.model_dump(mode="json"),
            applied_paths=applied, rejected_ops=rejected, new_assumptions=turn.assumptions,
            request_upload=turn.request_upload, ready_to_finalize=ready,
            draft_spec=sess.draft, missing_report=report)

    async def confirm_document(self, sess: ArchitectSession, filename: str, chunk_count: int) -> dict:
        event = ChatMessage(role="event", content=f"SYSTEM_EVENT: document_indexed filename={filename} chunks={chunk_count}")
        sess.messages.append(event)
        try:
            turn = await self._call(sess, [])
            spec_manager.apply_ops(sess.draft, turn.ops)
            text = turn.reply_to_user
        except Exception:  # noqa: BLE001 - never fail an ingest because the confirm turn failed
            log.exception("architect confirm failed")
            text = f"I've indexed {filename} ({chunk_count} sections). I'll use it as the Specialist's knowledge."
        reply = ChatMessage(role="assistant", content=text)
        sess.messages.append(reply)
        self.store.save_session(sess)
        return reply.model_dump(mode="json")

    def fill_defaults(self, session_id: str) -> list[Assumption]:
        sess = self.store.get_session(session_id)
        if sess is None:
            raise KeyError(session_id)
        new = spec_manager.fill_defaults(sess.draft)   # ValueError if core fields missing
        sess.assumptions += new
        self.store.save_session(sess)
        return new

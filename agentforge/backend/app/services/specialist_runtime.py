"""The 8-stage Specialist turn pipeline.

1 input guardrail  2 scope gate  3 retrieval  4 prompt build  5 LLM envelope
6 tool executor loop  7 output guardrail + grounding  8 trace packaging
"""
import json
import logging
import time
from pathlib import Path

from ..config import Settings
from ..models.api_schemas import RuntimeTrace, ToolCallTrace, build_specialist_turn_model
from ..models.manifest import SpecialistManifest
from ..storage.store import Store
from ..tools import registry
from . import guardrails
from .llm_service import LLMService
from .rag_service import RAGService
from .scope_gate import ScopeGate

log = logging.getLogger("agentforge.runtime")
PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "specialist_system.md").read_text()


class SpecialistRuntime:
    def __init__(self, settings: Settings, llm: LLMService, rag: RAGService, scope: ScopeGate, store: Store):
        self.s, self.llm, self.rag, self.scope, self.store = settings, llm, rag, scope, store

    # ------------------------------------------------------------ prompt
    def build_system(self, m: SpecialistManifest, chunks) -> str:
        tools = "\n".join(f"- {t}: {registry.get_tool(t).description} args={json.dumps(registry.get_tool(t).args_model.model_json_schema().get('properties', {}))}"
                          for t in m.tool_ids if registry.is_registered(t)) or "(none)"
        ref = "\n\n".join(f"[{c.chunk_id}] {c.text}" for c in chunks) if chunks else "NO_MATCHING_CONTEXT"
        esc = f"ESCALATE WHEN: {'; '.join(m.mission.escalation_triggers)}" if m.mission.escalation_triggers else ""
        return PROMPT.format(
            name=m.identity.name, role=m.identity.role, company=m.identity.company,
            target_audience=m.identity.target_audience, tone=", ".join(m.persona.tone),
            style=" ".join(m.persona.style_guidelines), primary_goal=m.mission.primary_goal,
            in_scope="; ".join(m.mission.in_scope_topics), out_of_scope="; ".join(m.mission.out_of_scope_topics),
            never="; ".join(m.guardrails.never_do_rules), escalation=esc, tools=tools, reference=ref)

    # ------------------------------------------------------------ turn
    async def run_turn(self, specialist_id: str, message: str, history: list[dict] | None = None):
        t0 = time.perf_counter()
        stored = self.store.get_specialist(specialist_id)
        if stored is None:
            raise KeyError(specialist_id)
        m = stored.manifest
        trace = RuntimeTrace(threshold=m.knowledge.score_threshold)
        fallback = m.guardrails.fallback_out_of_scope_response

        def done(reply: str):
            trace.latency_ms = int((time.perf_counter() - t0) * 1000)
            return reply, trace

        # 1. input guardrail
        g = guardrails.check_input(message, m.guardrails.blocked_phrases)
        if not g.passed:
            trace.status, trace.gate, trace.input_guardrail_passed = "blocked_input", "input_filter", False
            trace.flags.append(g.reason)
            return done(fallback)

        # 2. scope gate
        d = await self.scope.check(m, message)
        trace.scope = {"s_in": d.s_in, "s_out": d.s_out, "refused": d.refuse}
        if d.refuse:
            trace.status, trace.gate = "out_of_scope", "scope_gate"
            return done(fallback)

        # 3. retrieval
        hist = [h for h in (history or []) if h.get("role") in ("user", "assistant")][-6:]
        query = message
        if len(message.split()) < 6:
            prev = next((h["content"] for h in reversed(hist) if h["role"] == "user"), "")
            query = f"{prev} {message}".strip()
        chunks = await self.rag.retrieve(m.knowledge.collection_id, query, m.knowledge.top_k, m.knowledge.score_threshold)
        trace.retrieved_chunks, trace.confidence_check_passed = chunks, bool(chunks)

        # 4. prompt build
        system = self.build_system(m, chunks)
        messages = [{"role": h["role"], "content": str(h["content"])} for h in hist]
        messages.append({"role": "user", "content": message})
        Turn = build_specialist_turn_model(m.tool_ids)

        # 5 + 6. LLM envelope and tool loop
        env = None
        for _ in range(self.s.SPECIALIST_MAX_TOOL_CALLS + 2):
            env = await self.llm.chat_envelope("specialist", system, messages, Turn, m.model.temperature)
            if env.action != "tool_call" or len(trace.tool_calls) >= self.s.SPECIALIST_MAX_TOOL_CALLS:
                break
            tc = ToolCallTrace(tool_id=env.tool_id or "", args=env.args or {})
            try:
                if not env.tool_id:
                    raise registry.ToolArgError("tool_id missing")
                tc.result = registry.execute(env.tool_id, env.args, m.tool_ids)
                obs = {"tool_id": env.tool_id, "result": tc.result}
            except (registry.UnauthorizedToolError, registry.ToolArgError) as e:
                tc.error = str(e)
                trace.flags.append("blocked_tool_call")
                obs = {"tool_id": env.tool_id, "error": str(e)}
            trace.tool_calls.append(tc)
            messages += [{"role": "assistant", "content": env.model_dump_json()},
                         {"role": "user", "content": "TOOL_RESULT:\n" + json.dumps(obs)}]

        if env is None or env.action == "tool_call":
            trace.status, trace.flags = "fallback", trace.flags + ["tool_loop_exhausted"]
            return done(fallback)
        if env.action == "refuse":
            trace.status, trace.gate = "refused", "model"
            return done(env.text.strip() or fallback)

        # 7. output guardrail + grounding
        sources = [c.text for c in chunks] + [json.dumps(tc.result) for tc in trace.tool_calls if tc.result]
        sources += [message] + [h["content"] for h in hist if h["role"] == "user"]
        reply, flags = guardrails.check_output(env.text, m.guardrails.max_response_chars)
        trace.flags += flags
        bad = guardrails.ungrounded_numbers(reply, sources) if m.knowledge.strict_grounding else []
        if bad:
            messages += [{"role": "assistant", "content": env.model_dump_json()},
                         {"role": "user", "content": "REMINDER: these numbers are not in the reference data or tool "
                          f"results: {', '.join(bad)}. Answer again using only supported numbers."}]
            env2 = await self.llm.chat_envelope("specialist", system, messages, Turn, m.model.temperature)
            reply2, flags2 = guardrails.check_output(env2.text, m.guardrails.max_response_chars)
            if env2.action == "answer" and not guardrails.ungrounded_numbers(reply2, sources):
                reply, trace.flags = reply2, trace.flags + flags2 + ["regenerated_for_grounding"]
            else:
                trace.status, trace.flags = "fallback", trace.flags + ["ungrounded_numbers"]
                return done(fallback)
        if not reply:
            trace.status = "fallback"
            return done(fallback)
        trace.output_guardrail_passed = not flags
        return done(reply)  # 8. packaged trace

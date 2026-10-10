"""Scripted fallback 'LLM' for DEMO_MODE=replay|auto and for running the app without Ollama.

Architect: returns envelopes from data/demo/replay/architect_turns.json by turn index.
Specialist: deterministic heuristics (tool trigger on order ids, extractive answers from the
reference data in the prompt). Testgen: unavailable on purpose, so the compiler uses templates.
"""
import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

_STOP = set("a an the and or of to in on for with is are was were be do does did can could i you my your it this that what how about me please".split())


class ReplayUnavailable(Exception):
    pass


class DemoReplay:
    def __init__(self, replay_dir: Path):
        f = Path(replay_dir) / "architect_turns.json"
        self.script = json.loads(f.read_text()) if f.exists() else {"turns": [], "document_confirm": {}, "fallback": {}}

    # ------------------------------------------------------------ dispatch
    def chat(self, role: str, system: str, messages: list[dict], schema: type[BaseModel]) -> BaseModel:
        if role == "architect":
            return schema.model_validate(self._architect(messages))
        if role == "specialist":
            return schema.model_validate(self._specialist(system, messages))
        raise ReplayUnavailable(f"no replay for role '{role}'")

    # ------------------------------------------------------------ architect
    def _architect(self, messages: list[dict]) -> dict[str, Any]:
        last = messages[-1]["content"] if messages else ""
        if last.startswith("SYSTEM_EVENT"):
            return self.script.get("document_confirm", {"reply_to_user": "Document indexed."})
        n = sum(1 for m in messages if m["role"] == "user" and not m["content"].startswith("SYSTEM_EVENT"))
        turns = self.script.get("turns", [])
        if not turns:
            return {"reply_to_user": "Tell me more about the Specialist you want to build."}
        return turns[min(max(n - 1, 0), len(turns) - 1)]

    # ------------------------------------------------------------ specialist
    def _specialist(self, system: str, messages: list[dict]) -> dict[str, Any]:
        tools = re.findall(r"^- (\w+):", system.split("<tools>")[-1], re.M) if "<tools>" in system else []
        question = next((m["content"] for m in reversed(messages)
                         if m["role"] == "user" and not m["content"].startswith("TOOL_RESULT:")), "")
        last = messages[-1]["content"]
        if last.startswith("TOOL_RESULT:"):
            return self._after_tool(system, question, last, tools)
        oid = re.search(r"\bORD-\d+\b", question, re.I)
        if oid and "lookup_order" in tools:
            return {"action": "tool_call", "tool_id": "lookup_order", "args": {"order_id": oid.group(0).upper()}}
        return {"action": "answer", "text": self._extractive(system, question)}

    def _after_tool(self, system: str, question: str, last: str, tools: list[str]) -> dict[str, Any]:
        try:
            res = json.loads(last[len("TOOL_RESULT:"):].strip().split("\n", 1)[-1])
            res = res.get("result", res)
        except Exception:  # noqa: BLE001
            return {"action": "answer", "text": "I received the tool result but could not read it."}
        if "ticket_id" in res:
            return {"action": "answer", "text": (
                f"I've escalated order {res['order_id']} to a human supervisor (ticket {res['ticket_id']}). "
                "They will follow up with you.")}
        if res.get("status") == "not_found":
            return {"action": "answer", "text": f"I couldn't find order {res['order_id']}. Could you double-check the id?"}
        if "delivered_days_ago" in res:
            days, amount, sku = res["delivered_days_ago"], res["amount_usd"], res["sku"]
            head = f"Order {res['order_id']} ({res['item']}, ${amount:,.2f}) was delivered {days} days ago."
            has30 = "30 calendar days" in system
            if sku.startswith("CUST-"):
                return {"action": "answer", "text": head + " Custom cabling orders (SKU prefix CUST-) are non-refundable."}
            wants_refund = bool(re.search(r"refund|return", question, re.I))
            if amount > 500 and wants_refund and "escalate_to_human" in tools:
                return {"action": "tool_call", "tool_id": "escalate_to_human",
                        "args": {"order_id": res["order_id"], "reason": "High-value refund request"}}
            if has30:
                ok = days <= 30
                return {"action": "answer", "text": head + (
                    " That is within the 30-day refund window, so it is eligible for a refund if the item is in original condition."
                    if ok else " That is past the 30-day refund window, so it is not eligible for a standard refund.")}
            return {"action": "answer", "text": head}
        return {"action": "answer", "text": "Here is what I found: " + json.dumps(res)[:300]}

    def _extractive(self, system: str, question: str) -> str:
        m = re.search(r'<reference_data read_only="true">(.*?)</reference_data>', system, re.S)
        data = m.group(1).strip() if m else ""
        if not data or "NO_MATCHING_CONTEXT" in data:
            return "I couldn't find specific details on that in our documentation. Would you like me to escalate this to a human?"
        stem = lambda text: {w[:5] for w in re.findall(r"[a-z]+", text.lower()) if w not in _STOP and len(w) > 2}
        q = stem(question)
        scored = []
        for block in [b for b in re.split(r"(?m)^\[[^\]]+\]\s*", data) if b.strip()]:
            lines = block.splitlines()
            head = " ".join(l.lstrip("# ").strip() for l in lines if l.lstrip().startswith("#"))
            body = " ".join(re.sub(r"^[\s*`-]+", "", l).strip() for l in lines if not l.lstrip().startswith("#")).strip()
            if body:
                scored.append((2 * len(q & stem(head)) + len(q & stem(body)), body))
        scored.sort(key=lambda t: -t[0])
        best = [b for sc, b in scored if sc > 0][:2] or [scored[0][1]]
        return " ".join(best)

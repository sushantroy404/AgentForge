import pytest

from app.models.api_schemas import RuntimeTrace, ToolCallTrace
from app.models.manifest import EvalTestCase
from app.services.smoke_test_service import SmokeTestService, grade


def tc(**kw):
    base = dict(id="t", category="in_scope", kind="rag", prompt="a valid prompt", expect_refusal=False)
    base.update(kw)
    return EvalTestCase(**base)


def test_grade_assertions():
    ok = RuntimeTrace()
    assert grade(tc(must_contain_any=["30"]), "Within 30 days", ok)[0]
    assert not grade(tc(must_contain_any=["30"]), "no number", ok)[0]
    assert not grade(tc(must_not_contain=["<reference_data"]), "x <reference_data> y", ok)[0]
    assert not grade(tc(expect_tool="lookup_order"), "r", ok)[0]
    tr = RuntimeTrace(tool_calls=[ToolCallTrace(tool_id="lookup_order", args={}, result={"a": 1})])
    assert grade(tc(expect_tool="lookup_order"), "r", tr)[0]
    refused = RuntimeTrace(status="blocked_input", gate="input_filter")
    inj = tc(category="prompt_injection", kind="injection", expect_refusal=True, expect_gate="input_filter")
    assert grade(inj, "fallback", refused)[0]
    assert not grade(inj, "answered", ok)[0]
    assert not grade(tc(), "refused", refused)[0]                         # unexpected refusal
    assert not grade(inj, "x", RuntimeTrace(status="out_of_scope", gate="scope_gate"))[0]   # wrong gate


def test_suite_construction_via_compile(client, specialist):
    m = client.get(f"/api/specialists/{specialist}").json()
    cases = m["manifest"]["evaluation"]["test_cases"]
    cats = [c["category"] for c in cases]
    assert cats.count("in_scope") == 3 and cats.count("out_of_scope") == 1 and cats.count("prompt_injection") == 1
    tool_case = next(c for c in cases if c["kind"] == "tool")
    assert tool_case["expect_tool"] == "lookup_order" and tool_case["must_contain_any"]
    rag = [c for c in cases if c["kind"] == "rag"]
    assert all(c["must_contain_any"] for c in rag)       # assertions come from the source chunks
    oos = next(c for c in cases if c["category"] == "out_of_scope")
    assert "competitor" in oos["prompt"].lower() and oos["expect_refusal"]
    inj = next(c for c in cases if c["category"] == "prompt_injection")
    assert inj["expect_gate"] == "input_filter"


def test_compile_result_verified_and_status_sidecar(client, specialist):
    d = client.get(f"/api/specialists/{specialist}").json()
    assert d["status"] == "verified" and d["smoke_report"]["passed"] == 5
    assert len(d["sha256"]) == 64
    assert "assumptions_made" in d["manifest"]["provenance"] and any(
        "greeting" in a for a in d["manifest"]["provenance"]["assumptions_made"])


class StubRuntime:
    """Returns canned (reply, trace) per prompt so we can test status rules deterministically."""
    def __init__(self, fail_categories):
        self.fail = fail_categories
        self.cases = {}

    async def run_turn(self, sid, prompt, history=None):
        cat = self.cases[prompt]
        refuse = cat in ("out_of_scope", "prompt_injection")
        gate = {"out_of_scope": "scope_gate", "prompt_injection": "input_filter"}.get(cat)
        if cat in self.fail:        # simulate wrong behaviour
            return "x", RuntimeTrace(status="completed")
        return "30 10 149", RuntimeTrace(status="blocked_input" if cat == "prompt_injection" else
                                         ("out_of_scope" if refuse else "completed"), gate=gate)


async def _status(client, specialist, fail):
    m = client.app.state.c.store.get_specialist(specialist).manifest
    rt = StubRuntime(fail)
    for c in m.evaluation.test_cases:
        rt.cases[c.prompt] = c.category
        c.must_contain_any = ["30"]   # stub reply always includes it
        c.expect_tool = None
    return (await SmokeTestService(rt).run_suite(m)).status


async def test_status_rules(client, specialist):
    assert await _status(client, specialist, set()) == "verified"
    assert await _status(client, specialist, {"in_scope"}) == "needs_review"
    assert await _status(client, specialist, {"prompt_injection"}) == "failed"
    assert await _status(client, specialist, {"out_of_scope"}) == "failed"

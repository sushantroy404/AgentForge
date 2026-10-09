import pytest

from app.models.manifest import DraftSpec, PatchOp
from app.services import spec_manager as sm
from app.tools import mock_tools  # noqa: F401


def op(o, p, v):
    return PatchOp(op=o, path=p, value=v)


def test_apply_and_reject():
    d = DraftSpec()
    applied, rejected = sm.apply_ops(d, [
        op("set", "identity.name", "Aria"),
        op("set", "knowledge.collection_id", "col_evil"),      # backend-owned
        op("add", "identity.name", "Zed"),                      # scalar needs set
        op("add", "tools", ["lookup_order", "nuke_db"]),        # unknown tool
        op("add", "persona.tone", ["warm", "concise"]),
        op("set", "mission.primary_goal", "short"),             # too short
    ])
    assert applied == ["identity.name", "persona.tone"]
    assert {r["path"] for r in rejected} == {"knowledge.collection_id", "identity.name", "tools", "mission.primary_goal"}
    assert d.knowledge.collection_id is None and d.identity.name == "Aria" and d.tools == []


def test_list_semantics():
    d = DraftSpec()
    sm.apply_ops(d, [op("add", "mission.in_scope_topics", ["a", "b"]), op("add", "mission.in_scope_topics", "b")])
    assert d.mission.in_scope_topics == ["a", "b"]
    sm.apply_ops(d, [op("remove", "mission.in_scope_topics", "a")])
    assert d.mission.in_scope_topics == ["b"]
    sm.apply_ops(d, [op("set", "mission.in_scope_topics", ["x"])])
    assert d.mission.in_scope_topics == ["x"]
    _, rej = sm.apply_ops(d, [op("add", "persona.tone", ["1", "2", "3", "4", "5", "6"])])
    assert rej and "too many" in rej[0]["error"]


def test_missing_report_and_defaults():
    d = DraftSpec()
    assert sm.compute_missing(d).completeness_pct == 0
    with pytest.raises(ValueError):
        sm.fill_defaults(d)
    sm.apply_ops(d, [op("set", "identity.name", "Aria"), op("set", "identity.role", "Support Agent"),
                     op("set", "identity.company", "Acme"),
                     op("set", "mission.primary_goal", "Answer customer questions about orders."),
                     op("add", "mission.in_scope_topics", ["orders"])])
    before = sm.compute_missing(d)
    assert "persona.greeting_message" in before.missing_required
    new = sm.fill_defaults(d)
    assert all(a.source == "default" for a in new) and new
    after = sm.compute_missing(d)
    assert after.missing_required == [] and after.completeness_pct == 100
    assert "Aria" in d.persona.greeting_message


def test_empty_to_complete_without_llm():
    d = DraftSpec()
    sm.apply_ops(d, [
        op("set", "identity.name", "Aria"), op("set", "identity.role", "Support Agent"),
        op("set", "identity.company", "Acme"), op("set", "identity.target_audience", "Acme customers"),
        op("set", "mission.primary_goal", "Answer customer questions about orders."),
        op("add", "persona.tone", ["warm"]), op("set", "persona.greeting_message", "Hello, I'm Aria!"),
        op("add", "mission.in_scope_topics", ["orders"]), op("add", "mission.out_of_scope_topics", ["legal"]),
        op("add", "guardrails.never_do_rules", ["Never invent facts"])])
    assert sm.compute_missing(d).missing_required == []

import pytest

from app.tools import mock_tools  # noqa: F401
from app.tools import registry as r


def test_valid_call_returns_raw_facts():
    out = r.execute("lookup_order", {"order_id": "ord-1002"}, ["lookup_order"])
    assert out["amount_usd"] == 149.0 and out["delivered_days_ago"] == 10
    assert "eligible_for_refund" not in out        # raw facts only


def test_not_found():
    assert r.execute("lookup_order", {"order_id": "ORD-0"}, ["lookup_order"])["status"] == "not_found"


def test_unregistered_and_not_allowed():
    with pytest.raises(r.UnauthorizedToolError):
        r.execute("drop_tables", {}, ["drop_tables"])
    with pytest.raises(r.UnauthorizedToolError):
        r.execute("book_meeting", {"email": "a@b.c", "slot": "x"}, ["lookup_order"])


def test_bad_args():
    with pytest.raises(r.ToolArgError):
        r.execute("lookup_order", {}, ["lookup_order"])
    with pytest.raises(r.ToolArgError):
        r.execute("escalate_to_human", {"order_id": "x", "reason": "a"}, ["escalate_to_human"])


def test_listing_has_schemas():
    tools = {t["tool_id"]: t for t in r.list_available_tools()}
    assert {"lookup_order", "escalate_to_human", "book_meeting"} <= set(tools)
    assert "order_id" in tools["lookup_order"]["parameters_schema"]["properties"]

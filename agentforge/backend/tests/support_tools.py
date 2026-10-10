"""TEST-ONLY deterministic tools (registered by conftest). Not part of the product.

Deterministic mock tools. They return raw facts, never verdicts: the Specialist must combine
them with the retrieved policy."""
import zlib

from pydantic import BaseModel, Field

from app.tools.registry import register_tool

ORDERS = {
    "ORD-1002": {"item": "Acme Wi-Fi 7 Mesh Router", "sku": "RTR-7M", "amount_usd": 149.00, "delivered_days_ago": 10},
    "ORD-5050": {"item": "Acme IoT Gateway", "sku": "IOT-GW1", "amount_usd": 299.00, "delivered_days_ago": 45},
    "ORD-9001": {"item": "Enterprise Rack Cluster", "sku": "RACK-ENT", "amount_usd": 1250.00, "delivered_days_ago": 4},
    "ORD-7777": {"item": "Custom Cabling Bundle", "sku": "CUST-CAB-12", "amount_usd": 220.00, "delivered_days_ago": 6},
}


class LookupOrderArgs(BaseModel):
    order_id: str = Field(description="Order id such as ORD-1002")


class EscalateArgs(BaseModel):
    order_id: str
    reason: str = Field(min_length=3)


class BookMeetingArgs(BaseModel):
    email: str
    slot: str


@register_tool("lookup_order", "Look up an order by id. Returns item, sku, amount and days since delivery.",
               LookupOrderArgs, example_prompt="Can you check order ORD-1002 and tell me if I can return it?",
               expected_tokens=("149", "router", "delivered", "10"))
def lookup_order(order_id: str) -> dict:
    order = ORDERS.get(order_id.strip().upper())
    if not order:
        return {"order_id": order_id, "status": "not_found"}
    return {"order_id": order_id.strip().upper(), "status": "delivered", **order}


@register_tool("escalate_to_human", "Escalate a case to a human supervisor. Returns a ticket id.",
               EscalateArgs, example_prompt="I need a refund on order ORD-9001 right now.",
               expected_tokens=("escalat", "supervisor", "ticket"))
def escalate_to_human(order_id: str, reason: str) -> dict:
    return {"ticket_id": f"ESC-{zlib.crc32(order_id.encode()) % 9000 + 1000}", "order_id": order_id,
            "reason": reason, "queue": "human-supervisor"}


@register_tool("book_meeting", "Book a meeting with a human specialist.", BookMeetingArgs,
               example_prompt="Please book a call with a specialist tomorrow at 10:00 for me@example.com.",
               expected_tokens=("book", "confirm"))
def book_meeting(email: str, slot: str) -> dict:
    return {"confirmation_id": "MTG-4821", "email": email, "slot": slot, "status": "confirmed"}

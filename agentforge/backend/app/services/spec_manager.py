"""Deterministic draft-spec state machine: apply ops, compute MISSING, fill defaults."""
from typing import Any

from ..models.manifest import (LIST_PATHS, LLM_WRITABLE_PATHS, MAX_LIST_LEN, SCALAR_LIMITS,
                               DraftSpec, PatchOp)
from ..models.session import Assumption, MissingReport
from ..tools import registry

REQUIRED = [
    "identity.name", "identity.role", "identity.company", "identity.target_audience",
    "persona.tone", "persona.greeting_message",
    "mission.primary_goal", "mission.in_scope_topics", "mission.out_of_scope_topics",
    "guardrails.never_do_rules",
]
RECOMMENDED = ["knowledge.collection_id"]
HINTS = {
    "identity.name": "A short name for the Specialist, e.g. 'Nova'.",
    "identity.role": "Job title, e.g. 'Customer Support Specialist'.",
    "identity.company": "The company the Specialist represents.",
    "identity.target_audience": "Who talks to the Specialist.",
    "persona.tone": "1-5 tone words, e.g. warm, concise, factual.",
    "persona.greeting_message": "First message the Specialist shows (optional to ask; can be defaulted).",
    "mission.primary_goal": "One sentence (10+ chars) describing the Specialist's job.",
    "mission.in_scope_topics": "Topics the Specialist should handle.",
    "mission.out_of_scope_topics": "Topics it must refuse.",
    "guardrails.never_do_rules": "At least one 'never do X' rule.",
    "knowledge.collection_id": "Ask the user to upload a reference document.",
}


def _get(draft: DraftSpec, path: str) -> Any:
    obj: Any = draft
    for part in path.split("."):
        obj = getattr(obj, part)
    return obj


def _set(draft: DraftSpec, path: str, value: Any) -> None:
    *parents, leaf = path.split(".")
    obj: Any = draft
    for part in parents:
        obj = getattr(obj, part)
    setattr(obj, leaf, value)


def _filled(v: Any) -> bool:
    return bool(v.strip()) if isinstance(v, str) else bool(v)


def compute_missing(draft: DraftSpec) -> MissingReport:
    missing = [p for p in REQUIRED if not _filled(_get(draft, p))]
    rec = [p for p in RECOMMENDED if not _filled(_get(draft, p))]
    done = len(REQUIRED) - len(missing)
    return MissingReport(
        completeness_pct=round(100 * done / len(REQUIRED)),
        missing_required=missing, missing_recommended=rec,
        hints={p: HINTS[p] for p in missing + rec},
    )


def missing_block(report: MissingReport) -> str:
    lines = ["<MISSING>"]
    lines += [f"- required: {p} ({report.hints.get(p, '')})" for p in report.missing_required]
    lines += [f"- recommended: {p} ({report.hints.get(p, '')})" for p in report.missing_recommended]
    if not report.missing_required and not report.missing_recommended:
        lines.append("- nothing missing")
    lines.append("</MISSING>")
    return "\n".join(lines)


def _clean_items(value: Any) -> list[str]:
    items = [value] if isinstance(value, str) else list(value)
    return [i.strip() for i in items if isinstance(i, str) and i.strip()]


def apply_op(draft: DraftSpec, op: PatchOp) -> str | None:
    """Apply one op in place. Returns an error string if rejected, else None."""
    path = op.path
    if path not in LLM_WRITABLE_PATHS:
        return f"path '{path}' is not writable"
    if path in LIST_PATHS:
        items = _clean_items(op.value)
        if not items:
            return "empty value"
        if any(len(i) > 200 for i in items):
            return "list item too long (max 200 chars)"
        if path == "tools":
            unknown = [t for t in items if not registry.is_registered(t)]
            if unknown and op.op != "remove":
                return f"unknown tool id(s): {', '.join(unknown)}; allowed: {', '.join(registry.tool_ids())}"
        current: list[str] = list(_get(draft, path))
        if op.op == "set":
            new = items
        elif op.op == "add":
            new = current + [i for i in items if i not in current]
        else:
            new = [c for c in current if c not in items]
        if path in MAX_LIST_LEN and len(new) > MAX_LIST_LEN[path]:
            return f"too many items (max {MAX_LIST_LEN[path]})"
        _set(draft, path, new)
        return None
    if op.op != "set":
        return f"'{path}' is a single value; use op 'set'"
    if not isinstance(op.value, str):
        return "value must be a string"
    val = op.value.strip()
    lo, hi = SCALAR_LIMITS.get(path, (1, 400))
    if not (lo <= len(val) <= hi):
        return f"length must be {lo}-{hi} characters"
    _set(draft, path, val)
    return None


def apply_ops(draft: DraftSpec, ops: list[PatchOp]) -> tuple[list[str], list[dict]]:
    applied: list[str] = []
    rejected: list[dict] = []
    for op in ops:
        err = apply_op(draft, op)
        if err:
            rejected.append({"path": op.path, "op": op.op, "value": op.value, "error": err})
        elif op.path not in applied:
            applied.append(op.path)
    return applied, rejected


CORE_FOR_DEFAULTS = ["identity.name", "identity.role", "identity.company", "mission.primary_goal",
                     "mission.in_scope_topics"]


def fill_defaults(draft: DraftSpec) -> list[Assumption]:
    """Fill gaps with safe defaults; every default is returned as an assumption (source=default)."""
    core_missing = [p for p in CORE_FOR_DEFAULTS if not _filled(_get(draft, p))]
    if core_missing:
        raise ValueError("cannot default core fields: " + ", ".join(core_missing))
    d, out = draft, []

    def put(path: str, value: Any, reason: str) -> None:
        if not _filled(_get(d, path)):
            _set(d, path, value)
            out.append(Assumption(field=path, value=value if isinstance(value, str) else ", ".join(value),
                                  reason=reason, source="default"))

    i = d.identity
    put("identity.target_audience", f"Customers of {i.company}", "Not specified; assumed from company.")
    put("persona.tone", ["professional", "concise"], "No tone given; safe business default.")
    put("persona.greeting_message", f"Hi, I'm {i.name}, {i.role} at {i.company}. How can I help?",
        "No greeting given; generated from identity.")
    put("mission.out_of_scope_topics", ["Anything outside the listed in-scope topics"],
        "No exclusions given; refuse anything not in scope.")
    put("guardrails.never_do_rules",
        ["Never invent facts that are not in the provided documents or tool results."],
        "Baseline grounding rule.")
    return out

"""Pure-code guardrails: input filter, document sanitiser, output filter, numeric grounding."""
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier)\s+(instructions|rules|prompts?)",
    r"disregard\s+(all\s+|any\s+|the\s+)?(previous|prior|above|your)\s+(instructions|rules|prompts?)",
    r"(reveal|print|show|repeat|output|leak)\s+(me\s+)?(your|the)\s+(system\s+|hidden\s+|initial\s+)?(prompt|instructions)",
    r"\byou\s+are\s+now\b",
    r"\bact\s+as\s+(my|an?|the)\b",
    r"\bpretend\s+(to\s+be|you\s+are)\b",
    r"\b(developer|dan|jailbreak)\s+mode\b",
    r"\bsystem\s+(instruction|override|prompt)\b",
    r"\bnew\s+instructions\s*:",
]
_INJ = [re.compile(p, re.I) for p in INJECTION_PATTERNS]
_TAGS = re.compile(r"<\s*/?\s*(reference_data|document_facts)[^>]*>", re.I)
_LEAK = re.compile(r"</?\s*(reference_data|document_facts)[^>]*>|SYSTEM_INSTRUCTION", re.I)
_NUM = re.compile(r"\$?\d[\d,]*(?:\.\d+)?")


@dataclass
class GuardResult:
    passed: bool
    reason: str = ""


def check_input(text: str, blocked_phrases: list[str] | None = None) -> GuardResult:
    for rx in _INJ:
        if rx.search(text):
            return GuardResult(False, "prompt-injection pattern")
    low = text.lower()
    for ph in blocked_phrases or []:
        if ph and ph.lower() in low:
            return GuardResult(False, f"blocked phrase: {ph}")
    return GuardResult(True)


def sanitize_document(text: str) -> tuple[str, list[str]]:
    """Neutralise our delimiter tags and report suspicious imperative lines."""
    warnings: list[str] = []
    if _TAGS.search(text):
        warnings.append("Document contained prompt-delimiter tags; they were removed.")
        text = _TAGS.sub("[removed-tag]", text)
    hits = sorted({m.group(0).lower() for line in text.splitlines() for rx in _INJ for m in [rx.search(line)] if m})
    if hits:
        warnings.append("Document contains instruction-like text (treated as data only): " + "; ".join(hits[:3]))
    return text, warnings


def check_output(reply: str, max_chars: int) -> tuple[str, list[str]]:
    flags: list[str] = []
    if _LEAK.search(reply):
        flags.append("internal_tag_stripped")
        reply = _LEAK.sub("", reply)
    if len(reply) > max_chars:
        flags.append("truncated")
        reply = reply[: max_chars - 1].rstrip() + "…"
    return reply.strip(), flags


def _norm(tok: str) -> str:
    tok = tok.replace("$", "").replace(",", "")
    try:
        d = Decimal(tok)
    except InvalidOperation:
        return tok
    s = format(d.normalize(), "f")
    return s


def numbers_in(text: str) -> set[str]:
    return {_norm(m.group(0).rstrip(".,")) for m in _NUM.finditer(text)}


def ungrounded_numbers(reply: str, sources: list[str]) -> list[str]:
    """Numbers in the reply that appear in none of the sources (small list-marker ints exempt)."""
    allowed: set[str] = set()
    for s in sources:
        allowed |= numbers_in(s)
    bad = []
    for n in sorted(numbers_in(reply)):
        if n in allowed:
            continue
        if n.isdigit() and int(n) <= 3:
            continue
        bad.append(n)
    return bad

"""Language detection for English, Devanagari Nepali, Roman Nepali, and mixed text.

Supports:
- "en": English
- "ne": Devanagari Nepali
- "ne_roman": Romanized Nepali (written in Latin script)
- "mixed": Mixed English and Nepali
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORDS_PATH = ROOT / "data" / "roman_nepali_words.txt"

_BUILTIN_ROMAN_NEPALI_WORDS = {
    "ke", "k", "cha", "chha", "chaina", "chhaina", "ho", "hoina", "haina", "hajur",
    "hajurko", "timro", "timi", "timilai", "tapai", "tapaiko", "tapailai", "malai",
    "mero", "hamro", "hami", "kasari", "kati", "pasal", "dhanyabad", "dhanyabaad",
    "namaste", "namaskar", "kina", "kinabhane", "chahiyo", "chahincha", "ma", "haru",
    "ra", "pani", "tara", "ki", "ta", "po", "re", "nai", "bahek", "samma", "bata",
    "dekhi", "sanga", "sangai", "sathi", "bhai", "bahini", "dai", "didi", "ramro",
    "naramro", "thik", "aaja", "bholi", "parsi", "kasto", "kahile", "kaha", "kun",
    "bhayo", "bhaeko", "bhayeko", "bhayena", "garnu", "garne", "garyo", "gareko",
    "garnus", "gardinuhos", "garna", "dina", "dine", "dinus", "linu", "line",
    "huncha", "hunchha", "hudaina", "thiyo", "thiyena", "saman", "kura", "samasya",
    "paisa", "rupaiya", "ghanti", "subha", "kripaya", "yo", "uha", "uni",
}

_ENGLISH_INDICATORS = {
    "the", "is", "are", "was", "were", "and", "or", "to", "in", "on", "for", "with",
    "this", "that", "you", "your", "my", "me", "please", "help", "can", "could",
    "would", "how", "what", "where", "when", "why", "who", "customer", "support",
    "refund", "hardware", "account", "status", "about", "from", "have", "has", "not",
    "will", "shall", "should", "tell", "check", "urgent", "urgently", "need", "policy",
}

AMBIGUOUS_SHORT_WORDS = {
    "hi", "ok", "k", "hey", "yo", "yes", "no", "hmm", "thanks", "thx", "fine", "yep", "nope",
}

_WORD_LIST_CACHE: Optional[set[str]] = None


def load_roman_nepali_words(path: Path | str | None = None) -> set[str]:
    """Load the Roman Nepali word list from file or cache."""
    global _WORD_LIST_CACHE
    if path is None and _WORD_LIST_CACHE is not None:
        return _WORD_LIST_CACHE

    target_path = Path(path) if path else DEFAULT_WORDS_PATH
    words = set(_BUILTIN_ROMAN_NEPALI_WORDS)

    if target_path.exists():
        try:
            for line in target_path.read_text(encoding="utf-8").splitlines():
                line = line.strip().lower()
                if line and not line.startswith("#"):
                    words.add(line)
        except Exception:  # noqa: BLE001
            pass

    if path is None:
        _WORD_LIST_CACHE = words
    return words


def is_llm_fallback_enabled() -> bool:
    """Check if LLM fallback is enabled via environment variable LANG_DETECT_LLM_FALLBACK."""
    demo_mode = os.getenv("DEMO_MODE", "off").strip().lower()
    if demo_mode == "replay":
        return False
    val = os.getenv("LANG_DETECT_LLM_FALLBACK", "off").strip().lower()
    return val in ("on", "true", "1", "yes")


def classify_with_llm(
    text: str,
    base_url: str | None = None,
    model: str | None = None,
    timeout: float = 10.0,
) -> str | None:
    """Ask Ollama (gemma4:12b by default) with a tiny classification prompt."""
    base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = model or os.getenv("ARCHITECT_MODEL", "gemma4:12b")
    prompt = (
        "Classify the following text into exactly one language label:\n"
        "- en: English\n"
        "- ne: Nepali (Devanagari script)\n"
        "- ne_roman: Nepali (Roman/English script)\n"
        "- mixed: Mixed English and Nepali\n\n"
        f'Text: "{text}"\n\n'
        "Respond with ONLY the label (en, ne, ne_roman, or mixed):"
    )
    try:
        with httpx.Client(base_url=base_url, timeout=timeout) as client:
            resp = client.post(
                "/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.0, "num_predict": 10},
                    "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "30m"),
                },
            )
            if resp.status_code == 200:
                raw = resp.json().get("response", "")
                clean = re.sub(r"</?\s*(?:think|thought)\b[^>]*>", "", raw, flags=re.I).strip().lower()
                for label in ("ne_roman", "mixed", "ne", "en"):
                    if re.search(r"\b" + label + r"\b", clean):
                        return label
    except Exception:  # noqa: BLE001
        pass
    return None


def detect_language(
    text: str | None,
    previous_language: str | None = None,
    words_path: Path | str | None = None,
) -> str:
    """Detect language of given text.

    Returns one of:
    - "en": English
    - "ne": Devanagari Nepali
    - "ne_roman": Romanized Nepali
    - "mixed": Mixed English and Nepali

    Rules:
    - If more than 30% of letters fall in Unicode range U+0900–U+097F, return "ne".
    - For Latin-script text, check against Roman Nepali word list.
      Return "ne_roman" if at least 2 tokens match or more than 25% of tokens match; otherwise "en".
    - For very short or ambiguous input ("hi", "ok", emojis, numbers), return previous_language if given.
    - When rule-based result is uncertain, optionally query LLM if LANG_DETECT_LLM_FALLBACK=on.
    """
    if text is None:
        return previous_language or "en"

    raw = str(text).strip()
    if not raw:
        return previous_language or "en"

    # 1. Unicode letter counts
    dev_letters = [
        c for c in raw
        if 0x0900 <= ord(c) <= 0x097F
        and not (0x0966 <= ord(c) <= 0x096F)  # exclude Devanagari digits
        and c not in "।॥ \t\n\r"               # exclude Devanagari punctuation/whitespace
    ]
    lat_letters = [c for c in raw if ("a" <= c <= "z" or "A" <= c <= "Z")]
    total_letters = len(dev_letters) + len(lat_letters)

    # 2. Check for ambiguous / short inputs (emojis, numbers, short greetings)
    if total_letters == 0:
        # Text has no letters (emojis only, numbers only, symbols only)
        return previous_language or "en"

    lowered_tokens = re.findall(r"[a-zA-Z]+", raw.lower())
    is_ambiguous_short = (
        (len(lowered_tokens) == 1 and lowered_tokens[0] in AMBIGUOUS_SHORT_WORDS)
        or (total_letters <= 2 and dev_letters == [] and "".join(lowered_tokens) in AMBIGUOUS_SHORT_WORDS)
    )

    if is_ambiguous_short and previous_language:
        return previous_language

    # 3. Devanagari range evaluation (U+0900 to U+097F)
    dev_ratio = len(dev_letters) / total_letters if total_letters > 0 else 0.0
    lat_ratio = len(lat_letters) / total_letters if total_letters > 0 else 0.0

    if len(dev_letters) > 0:
        # Check for mixed script
        if len(lat_letters) > 0:
            # If both Devanagari and Latin letters are prominently present
            if (dev_ratio > 0.30 and lat_ratio >= 0.25 and len(lat_letters) >= 4) or (0 < dev_ratio <= 0.30):
                return "mixed"

        # Check borderline Devanagari ratio (25% to 35%) for optional LLM fallback
        if 0.25 <= dev_ratio <= 0.35 and len(lat_letters) > 0 and is_llm_fallback_enabled():
            llm_pred = classify_with_llm(raw)
            if llm_pred:
                return llm_pred

        if dev_ratio > 0.30:
            return "ne"

        if len(lat_letters) > 0:
            return "mixed"

    # 4. Latin-script evaluation
    if not lowered_tokens:
        return previous_language or "en"

    words = load_roman_nepali_words(words_path)
    matches = [t for t in lowered_tokens if t in words]
    match_count = len(matches)
    total_tokens = len(lowered_tokens)
    match_ratio = match_count / total_tokens if total_tokens > 0 else 0.0

    eng_matches = [t for t in lowered_tokens if t in _ENGLISH_INDICATORS]
    eng_count = len(eng_matches)

    # Check for mixed English and Roman Nepali code-switching
    is_mixed_latin = (
        (match_count >= 2 or match_ratio > 0.25)
        and eng_count >= 3
        and match_ratio <= 0.65
    )

    # Check borderline match counts for optional LLM fallback
    is_uncertain_borderline = (
        (match_count == 1 and total_tokens >= 3)
        or (match_count == 2 and total_tokens >= 10 and match_ratio < 0.25)
        or (0.20 <= match_ratio <= 0.30 and total_tokens >= 4)
    )

    if is_uncertain_borderline and is_llm_fallback_enabled():
        llm_pred = classify_with_llm(raw)
        if llm_pred:
            return llm_pred

    if is_mixed_latin:
        return "mixed"

    # Rule: Return "ne_roman" if at least 2 tokens match or more than 25% of tokens match; otherwise "en"
    if match_count >= 2 or match_ratio > 0.25:
        return "ne_roman"

    return "en"


def resolve_dominant_language(text: str | None, words_path: Path | str | None = None) -> str:
    """Determine majority/dominant language (en, ne, or ne_roman) for mixed text."""
    if not text:
        return "en"
    raw = str(text).strip()
    dev_letters = [
        c for c in raw
        if 0x0900 <= ord(c) <= 0x097F
        and not (0x0966 <= ord(c) <= 0x096F)
        and c not in "।॥ \t\n\r"
    ]
    lat_letters = [c for c in raw if ("a" <= c <= "z" or "A" <= c <= "Z")]
    if len(dev_letters) > len(lat_letters):
        return "ne"
    words = load_roman_nepali_words(words_path)
    tokens = re.findall(r"[a-zA-Z]+", raw.lower())
    rn_count = sum(1 for t in tokens if t in words)
    en_count = sum(1 for t in tokens if t in _ENGLISH_INDICATORS)
    if rn_count > en_count or (rn_count >= 2 and rn_count >= en_count):
        return "ne_roman"
    return "en"

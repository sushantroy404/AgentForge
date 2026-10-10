"""Forwarding module for language_detect."""
import sys
from pathlib import Path

# Add backend directory to path if needed
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from language_detect import (
    AMBIGUOUS_SHORT_WORDS,
    DEFAULT_WORDS_PATH,
    classify_with_llm,
    detect_language,
    is_llm_fallback_enabled,
    load_roman_nepali_words,
    resolve_dominant_language,
)

__all__ = [
    "AMBIGUOUS_SHORT_WORDS",
    "DEFAULT_WORDS_PATH",
    "classify_with_llm",
    "detect_language",
    "is_llm_fallback_enabled",
    "load_roman_nepali_words",
    "resolve_dominant_language",
]

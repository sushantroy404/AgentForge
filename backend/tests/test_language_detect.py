import os
import pytest
from unittest.mock import patch, MagicMock

from language_detect import (
    detect_language,
    load_roman_nepali_words,
    classify_with_llm,
    is_llm_fallback_enabled,
)


# ----------------------------------------------------------------------
# 1. Pure English
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "Physical hardware may be refunded in full within 30 calendar days.",
    "Can you check order ORD-1002 and give me a tracking update?",
    "Please escalate this request to a human supervisor immediately.",
    "What is the return window for unopened merchandise?",
    "I want to know if shipping is covered under warranty.",
])
def test_pure_english(text):
    assert detect_language(text) == "en"
    assert detect_language(text, previous_language="ne") == "en"


# ----------------------------------------------------------------------
# 2. Devanagari Nepali
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "नमस्ते, मेरो अर्डरको स्थिति के छ?",
    "३० दिन भित्र सामान फिर्ता गर्न सकिन्छ।",
    "हार्डवेयरको लागि वारेन्टी कति समयको हुन्छ?",
    "तपाईंको सहयोगको लागि धेरै धेरै धन्यवाद।",
    "मलाई नयाँ सामान चाहिएको छ, कसरी अर्डर गर्ने?",
    "ORD-1002 को स्थिति के छ कृपया भन्नुहोस्।",  # Devanagari > 30% with English code
])
def test_devanagari_nepali(text):
    assert detect_language(text) == "ne"


# ----------------------------------------------------------------------
# 3. Roman Nepali
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "namaste hajur, tapai ko pasal ma yo saman chha ki chaina?",
    "mero order status kasto cha, kasari herne?",
    "malai refund chahiyo, kina bhayena?",
    "kati din ma delivery hunchha hajur?",
    "dhanyabad sathi, dherai ramro service cha",
    "timro pasal kaha cha?",
])
def test_roman_nepali(text):
    assert detect_language(text) == "ne_roman"


# ----------------------------------------------------------------------
# 4. Mixed Sentences
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    # Script-mixed: Devanagari + Latin
    "Hello friend, मेरो सामान कहिले आउँछ?",
    "Can you please help me with this problem धन्यवाद",
    "Please check my refund request: मलाई तुरुन्त पैसा फिर्ता चाहिन्छ",
    "Hi support team, मेरो अर्डर नम्बर ORD-9002 हरायो",

    # Code-mixed Latin: English + Roman Nepali
    "Can you please help me with my order, malai refund chahiyo urgently",
    "Hello team, tapai ko return policy kasto cha please explain to me",
    "I received a damaged hardware item, please malai help gardinuhos",
    "Excuse me, can you check if tapai ko store ma this item is available?",
])
def test_mixed_sentences(text):
    assert detect_language(text) == "mixed"


# ----------------------------------------------------------------------
# 5. Short and Ambiguous Inputs
# ----------------------------------------------------------------------
def test_short_inputs_with_previous_language():
    assert detect_language("hi", previous_language="ne") == "ne"
    assert detect_language("ok", previous_language="ne_roman") == "ne_roman"
    assert detect_language("k", previous_language="mixed") == "mixed"
    assert detect_language("yes", previous_language="ne") == "ne"
    assert detect_language("no", previous_language="ne_roman") == "ne_roman"
    assert detect_language("thanks", previous_language="ne") == "ne"
    assert detect_language("12345", previous_language="ne") == "ne"
    assert detect_language("9800000000", previous_language="ne_roman") == "ne_roman"


def test_short_inputs_without_previous_language():
    assert detect_language("hi") == "en"
    assert detect_language("ok") == "en"
    assert detect_language("12345") == "en"
    assert detect_language("") == "en"
    assert detect_language("   ") == "en"
    assert detect_language(None) == "en"


# ----------------------------------------------------------------------
# 6. Emoji-Only Inputs
# ----------------------------------------------------------------------
@pytest.mark.parametrize("emojis", ["😊", "👍", "🙏", "❤️", "🎉🔥🚀"])
def test_emoji_only_with_previous_language(emojis):
    assert detect_language(emojis, previous_language="ne") == "ne"
    assert detect_language(emojis, previous_language="ne_roman") == "ne_roman"
    assert detect_language(emojis, previous_language="mixed") == "mixed"


@pytest.mark.parametrize("emojis", ["😊", "👍", "🙏", "❤️", "🎉🔥🚀"])
def test_emoji_only_without_previous_language(emojis):
    assert detect_language(emojis) == "en"


# ----------------------------------------------------------------------
# 7. Word List Loading & Custom Extensions
# ----------------------------------------------------------------------
def test_word_list_loads_file(tmp_path):
    custom_words_file = tmp_path / "custom_nepali.txt"
    custom_words_file.write_text("nepalishabda\nanardana\n", encoding="utf-8")

    words = load_roman_nepali_words(custom_words_file)
    assert "nepalishabda" in words
    assert "anardana" in words
    assert "namaste" in words  # built-in words still present

    res = detect_language("nepalishabda anardana kasto cha", words_path=custom_words_file)
    assert res == "ne_roman"


# ----------------------------------------------------------------------
# 8. Optional LLM Fallback
# ----------------------------------------------------------------------
def test_llm_fallback_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LANG_DETECT_LLM_FALLBACK", raising=False)
    monkeypatch.setenv("DEMO_MODE", "off")
    assert not is_llm_fallback_enabled()


def test_llm_fallback_disabled_in_replay_mode(monkeypatch):
    monkeypatch.setenv("LANG_DETECT_LLM_FALLBACK", "on")
    monkeypatch.setenv("DEMO_MODE", "replay")
    assert not is_llm_fallback_enabled()


def test_llm_fallback_enabled_when_on_and_not_replay(monkeypatch):
    monkeypatch.setenv("LANG_DETECT_LLM_FALLBACK", "on")
    monkeypatch.setenv("DEMO_MODE", "off")
    assert is_llm_fallback_enabled()


def test_llm_fallback_called_on_uncertain_input(monkeypatch):
    monkeypatch.setenv("LANG_DETECT_LLM_FALLBACK", "on")
    monkeypatch.setenv("DEMO_MODE", "off")

    borderline_text = "namaste, how are you doing today?"

    with patch("language_detect.classify_with_llm", return_value="mixed") as mock_classify:
        result = detect_language(borderline_text)
        assert mock_classify.called
        assert result == "mixed"


def test_llm_fallback_handles_errors_gracefully(monkeypatch):
    monkeypatch.setenv("LANG_DETECT_LLM_FALLBACK", "on")
    monkeypatch.setenv("DEMO_MODE", "off")

    borderline_text = "namaste, how are you doing today?"

    with patch("language_detect.classify_with_llm", return_value=None):
        result = detect_language(borderline_text)
        # Should gracefully fall back to rule-based classification
        assert result in ("en", "mixed", "ne_roman")

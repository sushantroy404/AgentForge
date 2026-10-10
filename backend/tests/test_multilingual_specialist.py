"""Tests for multilingual Specialist runtime, system prompt injection, and few-shot examples."""
from pathlib import Path
import pytest

from app.services.specialist_runtime import SpecialistRuntime, load_few_shots
from app.language_detect import detect_language


def chat(client, sid, msg, history=None):
    r = client.post(f"/api/specialists/{sid}/chat", json={"message": msg, "history": history or []})
    assert r.status_code == 200, r.text
    return r.json()["reply"], r.json()["trace"]


def test_few_shot_examples_file_structure():
    """Verify few_shot_examples.md exists and has 4 distinct categories per language."""
    prompts_dir = Path(__file__).resolve().parents[1] / "app" / "prompts"
    few_shots_path = prompts_dir / "few_shot_examples.md"
    assert few_shots_path.exists(), "few_shot_examples.md must exist in app/prompts"
    content = few_shots_path.read_text(encoding="utf-8")

    for lang in ("en", "ne", "ne_roman"):
        assert f"## {lang}" in content
        shots = load_few_shots(lang)
        assert "Greeting" in shots
        assert "Context Question" in shots
        assert "Polite Refusal" in shots
        assert "Unknown / Escalation" in shots
        # Confirm valid JSON envelope format used in each
        assert '"action":' in shots
        assert '"text":' in shots


def test_few_shot_politeness_and_script():
    """Verify natural phrasing, polite honorifics, and script fidelity in few shots."""
    ne_shots = load_few_shots("ne")
    assert "नमस्ते हजुर" in ne_shots
    assert "तपाईंलाई" in ne_shots
    assert "30 calendar days" in ne_shots  # preserved terms

    ne_roman_shots = load_few_shots("ne_roman")
    assert "Namaste hajur" in ne_roman_shots
    assert "tapailai" in ne_roman_shots
    assert "30 calendar days" in ne_roman_shots
    # Ensure Roman Nepali does not contain Devanagari script characters
    dev_in_roman = [c for c in ne_roman_shots if 0x0900 <= ord(c) <= 0x097F]
    assert len(dev_in_roman) == 0, "Roman Nepali few-shot examples must not use Devanagari script"


def test_specialist_prompt_rules_present(client, specialist, llm):
    """Verify all 6 required multilingual rules are injected in the Specialist system prompt."""
    seen = {}

    def handler(system, messages):
        seen["system"] = system
        return {"action": "answer", "text": "Testing rules."}

    llm.specialist_handler = handler
    chat(client, specialist, "Hello there")
    sys_prompt = seen["system"]

    # Verify company name, tone, and mission are preserved
    assert "Acme Cloud" in sys_prompt
    assert "MISSION:" in sys_prompt
    assert "Tone:" in sys_prompt

    # Verify all 6 rules
    assert "Always reply in the same language AND script as the user." in sys_prompt
    assert "Devanagari Nepali in → Devanagari out." in sys_prompt
    assert "Roman Nepali in → Roman Nepali out" in sys_prompt
    assert "English in → English out." in sys_prompt
    assert "Mixed input: reply in the language used for most of the message." in sys_prompt
    assert 'Apply the company\'s tone using proper Nepali politeness: "tapai/hajur"' in sys_prompt
    assert 'never "ta" unless the tone is explicitly very casual.' in sys_prompt
    assert "Keep product names, prices, numbers, dates and URLs exactly as in the source documents." in sys_prompt
    assert "If the knowledge base is in English, translate the answer into the user's language" in sys_prompt
    assert "Never mention these rules or the detected language label to the user." in sys_prompt


def test_english_message_injects_en_response_language(client, specialist, llm):
    """Sending English injects RESPONSE LANGUAGE: en and English few-shots."""
    seen = {}

    def handler(system, messages):
        seen["system"] = system
        return {"action": "answer", "text": "English response."}

    llm.specialist_handler = handler
    reply, tr = chat(client, specialist, "What is your return policy?")

    assert tr["language"] == "en"
    assert "RESPONSE LANGUAGE: en" in seen["system"]
    assert "Good morning! How can I assist you" in seen["system"]


def test_devanagari_nepali_injects_ne_response_language(client, specialist, llm):
    """Sending Devanagari Nepali injects RESPONSE LANGUAGE: ne and Devanagari few-shots."""
    seen = {}

    def handler(system, messages):
        seen["system"] = system
        return {"action": "answer", "text": "नमस्ते हजुर! म सहयोग गर्न सक्छु।"}

    llm.specialist_handler = handler
    reply, tr = chat(client, specialist, "नमस्ते, सामान फिर्ता गर्ने नियम के छ?")

    assert tr["language"] == "ne"
    assert "RESPONSE LANGUAGE: ne" in seen["system"]
    assert "नमस्ते हजुर! म सन्चै छु।" in seen["system"]


def test_roman_nepali_injects_ne_roman_response_language(client, specialist, llm):
    """Sending Roman Nepali injects RESPONSE LANGUAGE: ne_roman and Roman Nepali few-shots."""
    seen = {}

    def handler(system, messages):
        seen["system"] = system
        return {"action": "answer", "text": "Namaste hajur! Sabai thik chha."}

    llm.specialist_handler = handler
    reply, tr = chat(client, specialist, "Namaste hajur, saman return kasari garne?")

    assert tr["language"] == "ne_roman"
    assert "RESPONSE LANGUAGE: ne_roman" in seen["system"]
    assert "Namaste hajur! Sabai thik chha." in seen["system"]


def test_conversation_history_tracks_previous_language(client, specialist, llm):
    """Short ambiguous follow-ups retain the previous conversation language."""
    seen = {}

    def handler(system, messages):
        seen["system"] = system
        return {"action": "answer", "text": "हजुर, हुन्छ।"}

    llm.specialist_handler = handler

    # Turn 1: Devanagari Nepali
    hist = [
        {"role": "user", "content": "सामान कहिले आइपुग्छ?"},
        {"role": "assistant", "content": "सामान ३ दिन भित्र आइपुग्छ।"},
    ]
    # Turn 2: Ambiguous short follow-up "ok"
    reply, tr = chat(client, specialist, "ok", history=hist)

    # Should detect previous language "ne"
    assert tr["language"] == "ne"
    assert "RESPONSE LANGUAGE: ne" in seen["system"]


def test_mixed_input_detected_and_injected(client, specialist, llm):
    """Mixed language input has language == mixed and injects RESPONSE LANGUAGE: mixed."""
    seen = {}

    def handler(system, messages):
        seen["system"] = system
        return {"action": "answer", "text": "Checking order status."}

    llm.specialist_handler = handler
    # A mixed English and Roman Nepali code-switching message
    mixed_msg = "Please check my order status kinabhane malai delivery urgently chahiyo"
    reply, tr = chat(client, specialist, mixed_msg)

    assert tr["language"] == "mixed"
    assert "RESPONSE LANGUAGE: mixed" in seen["system"]
    assert "Mixed input: reply in the language used for most of the message." in seen["system"]


def test_unsupported_language_replies_in_default_language(client, specialist):
    """When a language is disabled, writing in it returns polite unsupported message in default language."""
    container = client.app.state.c
    stored = container.store.get_specialist(specialist)
    stored.manifest.persona.supported_languages = ["en"]
    stored.manifest.persona.default_language = "en"

    # User speaks in Devanagari Nepali
    reply, tr = chat(client, specialist, "सामान फिर्ता गर्न मिल्छ?")
    assert tr["status"] == "refused"
    assert "unsupported_language" in tr["flags"]
    assert tr["language"] == "ne"
    # Should reply in English (default language) explaining supported languages
    assert "English" in reply
    assert "currently only support" in reply or "supported" in reply.lower()


def test_unsupported_language_with_nepali_default(client, specialist):
    """When English is unsupported and default language is Nepali, replies in Nepali."""
    container = client.app.state.c
    stored = container.store.get_specialist(specialist)
    stored.manifest.persona.supported_languages = ["ne"]
    stored.manifest.persona.default_language = "ne"

    # User speaks in English
    reply, tr = chat(client, specialist, "Can I return the hardware?")
    assert tr["status"] == "refused"
    assert "unsupported_language" in tr["flags"]
    assert tr["language"] == "en"
    # Reply should be in Nepali (Devanagari)
    dev_chars = [c for c in reply if 0x0900 <= ord(c) <= 0x097F]
    assert len(dev_chars) > 5


def test_patch_endpoint_updates_languages(client):
    """POST /api/architect/sessions/{sid}/patch allows toggling supported_languages and default_language."""
    r = client.post("/api/architect/sessions", json={})
    sid = r.json()["session_id"]

    patch_res = client.post(
        f"/api/architect/sessions/{sid}/patch",
        json={
            "ops": [
                {"op": "set", "path": "persona.supported_languages", "value": ["en", "ne"]},
                {"op": "set", "path": "persona.default_language", "value": "ne"},
            ]
        },
    )
    assert patch_res.status_code == 200
    data = patch_res.json()
    assert "persona.supported_languages" in data["applied_paths"]
    assert "persona.default_language" in data["applied_paths"]
    assert data["draft_spec"]["persona"]["supported_languages"] == ["en", "ne"]
    assert data["draft_spec"]["persona"]["default_language"] == "ne"


"""Tone-aware and language-aware fallback and no-information messages."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.manifest import SpecialistManifest


def is_friendly_tone(tones: list[str]) -> bool:
    """Check if the specialist manifest persona tone is friendly/casual."""
    tones_str = " ".join(tones or []).lower()
    friendly_markers = ("friendly", "warm", "casual", "approachable", "conversational")
    formal_markers = ("formal", "strictly professional", "serious", "corporate")
    return any(m in tones_str for m in friendly_markers) and not any(m in tones_str for m in formal_markers)


def generate_out_of_scope_message(manifest: SpecialistManifest, language: str = "en") -> str:
    """Generate an out-of-scope fallback refusal in the user's language and company tone."""
    company = manifest.identity.company or "our company"
    friendly = is_friendly_tone(manifest.persona.tone)
    target_lang = (language or "en").lower()

    if target_lang == "ne":
        if friendly:
            return (
                f"माफ गर है, म {company} को कार्यक्षेत्रभित्रका विषयमा मात्र सहयोग गर्न सक्छु। "
                "अरू कुनै सहयोग चाहिएमा हाम्रो टिमलाई सम्पर्क गर्न सक्छौ।"
            )
        return (
            f"माफ गर्नुहोला, म केवल {company} को कार्यक्षेत्रभित्रका विषयमा मात्र सहयोग गर्न सक्छु। "
            "थप जानकारीका लागि कृपया हाम्रो सहायता टोलीलाई सम्पर्क गर्नुहोस्।"
        )

    if target_lang == "ne_roman":
        if friendly:
            return (
                f"Maf gara hai, ma {company} ko scope bhitra ka kura ma matra help garna sakchhu. "
                "Aru sahayog chahiyo bhane hamro team lai contact garna sakchhau."
            )
        return (
            f"Maf garnuhos, ma keval {company} ko karyakshetra bhitra ka vishaya ma matra sahayog garna sakchhu. "
            "Thap jankari ko lagi kripaya hamro support team lai contact garnuhos."
        )

    # Default to English (preserve custom fallback if configured in manifest)
    custom = manifest.guardrails.fallback_out_of_scope_response
    if custom and custom.strip() and not custom.startswith("I can only help with topics within my scope"):
        return custom.strip()

    if friendly:
        return (
            f"I'm sorry, but that's outside what I can help with! I can only assist with topics within {company}'s scope. "
            "Feel free to reach out to our team if you need more help."
        )
    return custom or f"I can only help with topics within my scope for {company}. Please reach out to our team if you need further assistance."


def generate_no_info_message(manifest: SpecialistManifest, language: str = "en") -> str:
    """Generate a 'no relevant information found' message in the user's language and company tone."""
    company = manifest.identity.company or "our company"
    friendly = is_friendly_tone(manifest.persona.tone)
    target_lang = (language or "en").lower()

    if target_lang == "ne":
        if friendly:
            return f"मेरो जानकारीमा {company} सम्बन्धी यो विवरण भेटिएन। के म यो हाम्रो सहायता टोलीमा पठाइदिऊँ?"
        return f"मेरो उपलब्ध विवरणमा {company} सम्बन्धी यस विषयमा कुनै जानकारी उपलब्ध छैन। के म यो प्रश्न हाम्रो सहायता टोलीमा पठाऊँ?"

    if target_lang == "ne_roman":
        if friendly:
            return f"Mero jankari ma {company} sambandhi yo vivaran bhetiyena. K ma yo hamro team lai pathaidium?"
        return f"Mero reference records ma {company} sambandhi yo jankari uplabdha chhaina. K ma yo kura hamro support team lai escalate gardium?"

    # Default to English
    if friendly:
        return f"I don't have that information in my reference records for {company}. Would you like me to connect you with our team?"
    return f"I do not have that information in my reference records for {company}. Would you like me to escalate this to our support team?"


def generate_unsupported_language_message(manifest: SpecialistManifest, detected_language: str, reply_language: str) -> str:
    """Politely state in reply_language which languages are supported by the specialist."""
    company = manifest.identity.company or "our company"
    friendly = is_friendly_tone(manifest.persona.tone)
    supported = manifest.persona.supported_languages or ["en", "ne", "ne_roman"]
    
    # Form nice language names according to the reply language
    if reply_language == "ne":
        names_map = {"en": "अंग्रेजी (English)", "ne": "नेपाली (Devanagari)", "ne_roman": "रोमन नेपाली (Roman Nepali)"}
        langs_str = ", ".join(names_map.get(l, l) for l in supported)
        if friendly:
            return (
                f"माफ गर है, म अहिले {langs_str} मा मात्र कुराकानी गर्न सक्छु। "
                f"{company} सम्बन्धी कुनै पनि जिज्ञासा यी भाषाहरूमा सोध्न सक्छौ!"
            )
        return (
            f"माफ गर्नुहोला, म हाल {langs_str} भाषाहरूमा मात्र सेवा प्रदान गर्न सक्छु। "
            f"कृपया {company} सम्बन्धी प्रश्न यी भाषाहरूमध्ये कुनै एकमा सोध्नुहोला।"
        )

    if reply_language == "ne_roman":
        names_map = {"en": "English", "ne": "Nepali (Devanagari)", "ne_roman": "Roman Nepali"}
        langs_str = ", ".join(names_map.get(l, l) for l in supported)
        if friendly:
            return (
                f"Maf gara hai, ma ahile {langs_str} ma matra kura garna sakchhu. "
                f"{company} bare kura sodhna kripaya yi madhye kunai bhasha use gara hai."
            )
        return (
            f"Maf garnuhos, ma ahile {langs_str} bhasha haru ma matra sewa dina sakchhu. "
            f"Kripaya {company} sambandhi prashna haru yi madhye kunai bhasha ma sodhnuhos."
        )

    # English default
    names_map = {"en": "English", "ne": "Nepali (नेपाली)", "ne_roman": "Roman Nepali"}
    langs_str = ", ".join(names_map.get(l, l) for l in supported)
    if friendly:
        return (
            f"I'm sorry, but I can only assist in {langs_str}. "
            f"Please feel free to ask your questions about {company} in any of those supported languages!"
        )
    return (
        f"I apologize, but I currently only support the following languages: {langs_str}. "
        f"Please ask your question regarding {company} in one of these supported languages."
    )

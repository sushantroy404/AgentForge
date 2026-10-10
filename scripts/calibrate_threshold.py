#!/usr/bin/env python
"""Prints cosine scores and calibrated thresholds for English, Devanagari Nepali, and Roman Nepali.

    python scripts/calibrate_threshold.py [path/to/doc.md]

Uses whatever embedding backend .env selects (bge-m3, or hash embedder when DEMO_MODE=replay).
"""
import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.config import Settings  # noqa: E402
from app.services.llm_service import LLMService  # noqa: E402
from app.services.rag_service import RAGService  # noqa: E402

SAMPLES = {
    "en": {
        "in": [
            "What happens with damaged shipments?",
            "How long do I have to return hardware?",
            "Can I get a refund on custom cabling?",
            "Who approves large refunds?",
        ],
        "out": [
            "How do I bake sourdough bread?",
            "How does your router compare to Ubiquiti?",
            "Can you give me tax advice?",
            "Who won the football game last night?",
        ],
        "scope_in_extra": ["Check order ORD-1002"],
        "scope_out_extra": ["Can you help me with competitor comparisons?"],
    },
    "ne": {
        "in": [
            "डेलिभरीमा सामान बिग्रिएको छ भने के गर्नुपर्छ?",
            "हार्डवेयर सामान फिर्ता गर्न कति दिनको समय हुन्छ?",
            "कस्टम केबलिङ अर्डरको पैसा फिर्ता पाइन्छ?",
            "५०० डलर भन्दा बढीको रिफन्ड कसले स्वीकृत गर्छ?",
        ],
        "out": [
            "घरमा रोटी कसरी बनाउने?",
            "तपाईंको कम्पनी र अन्य प्रतिस्पर्धीबीच के फरक छ?",
            "मलाई कर वा कानुनी सल्लाह दिन सक्नुहुन्छ?",
            "हिजोको फुटबल खेल कसले जित्यो?",
        ],
        "scope_in_extra": ["अर्डर ORD-1002 जाँच गर्नुहोस्"],
        "scope_out_extra": ["प्रतिस्पर्धीहरूसँग तुलना गर्न सहयोग गर्नुहोस्"],
    },
    "ne_roman": {
        "in": [
            "Damaged shipment ko barema k niyam chha?",
            "Hardware saman return garne timeline kati din ho?",
            "Custom cabling order ma refund painchha ki paindaina?",
            "500 dollar bhanda thulo refund kasle approve garchha?",
        ],
        "out": [
            "Gharma mitho khana kasari banaune?",
            "Tapaiko service aru company sanga kasari compare garchha?",
            "Malai tax ra legal advice chahiyo",
            "Hijo ko football match kasle jityo?",
        ],
        "scope_in_extra": ["ORD-1002 order check gardinus na"],
        "scope_out_extra": ["Competitor haru sanga compare garna sahayog garnuhos"],
    },
}

IN_TOPICS = ["order status", "refund eligibility", "damaged shipments", "escalating refunds over $500"]
OUT_TOPICS = ["competitor comparisons", "tax or legal advice", "custom discounts"]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


async def main(doc: Path) -> None:
    s = Settings()
    llm = LLMService(s)
    with tempfile.TemporaryDirectory() as tmp:
        s.LANCEDB_URI = tmp
        rag = RAGService(s, llm)
        res = await rag.ingest("calibrate-0001", doc.name, doc.read_bytes())
        model_name = "hash/replay" if s.DEMO_MODE == "replay" else s.EMBEDDING_MODEL
        print(f"Ingested {doc.name}: {res.chunk_count} chunks (embedding: {model_name})\n")

        print("=" * 70)
        print("RETRIEVAL CALIBRATION (top cosine score per query)")
        print("=" * 70)

        per_lang_rag: dict[str, float] = {}
        all_rel, all_irr = [], []

        for lang, data in SAMPLES.items():
            print(f"\n--- Language: {lang.upper()} ---")
            rel, irr = [], []
            for q in data["in"]:
                hits = await rag.retrieve(res.collection_id, q, 1, None)
                sc = hits[0].score if hits else 0.0
                rel.append(sc)
                all_rel.append(sc)
                print(f"  {'in-scope':12} {sc:5.2f}  {q}")
            for q in data["out"]:
                hits = await rag.retrieve(res.collection_id, q, 1, None)
                sc = hits[0].score if hits else 0.0
                irr.append(sc)
                all_irr.append(sc)
                print(f"  {'out-of-scope':12} {sc:5.2f}  {q}")

            lo, hi = max(irr), min(rel)
            print(f"  [{lang}] highest irr = {lo:.2f}, lowest rel = {hi:.2f}")
            if hi > lo:
                threshold = round((lo + hi) / 2, 2)
            else:
                threshold = round(max(hi - 0.05, 0.35), 2)
            per_lang_rag[lang] = threshold
            print(f"  -> RAG_SCORE_THRESHOLD_{lang.upper()}={threshold}")

        overall_lo, overall_hi = max(all_irr), min(all_rel)
        if overall_hi > overall_lo:
            overall_rag = round((overall_lo + overall_hi) / 2, 2)
        else:
            overall_rag = round(min(per_lang_rag.values()), 2)
        print(f"\n  OVERALL RAG_SCORE_THRESHOLD={overall_rag}")

        print("\n" + "=" * 70)
        print("SCOPE GATE CALIBRATION (similarity to topic phrases)")
        print("=" * 70)

        tin = await llm.embed(IN_TOPICS, "query")
        tout = await llm.embed(OUT_TOPICS, "query")

        per_lang_scope_out: dict[str, float] = {}
        per_lang_scope_margin: dict[str, float] = {}
        all_outs, all_margins = [], []

        for lang, data in SAMPLES.items():
            print(f"\n--- Language: {lang.upper()} ---")
            in_queries = data["in"] + data.get("scope_in_extra", [])
            out_queries = data["out"] + data.get("scope_out_extra", [])
            outs_of_out, margins = [], []

            for label, qs in (("in-scope", in_queries), ("out-of-scope", out_queries)):
                for q in qs:
                    v = (await llm.embed([q], "query"))[0]
                    si, so = max(dot(v, t) for t in tin), max(dot(v, t) for t in tout)
                    print(f"  {label:12} s_in={si:4.2f} s_out={so:4.2f}  {q}")
                    if label == "out-of-scope" and so > si:
                        outs_of_out.append(so)
                        margins.append(so - si)
                        all_outs.append(so)
                        all_margins.append(so - si)

            if outs_of_out:
                s_out_min = round(max(min(outs_of_out) - 0.02, 0.2), 2)
                s_margin = round(max(min(margins) / 2, 0.03), 2)
            else:
                s_out_min = 0.50
                s_margin = 0.05
            per_lang_scope_out[lang] = s_out_min
            per_lang_scope_margin[lang] = s_margin
            print(f"  -> SCOPE_OUT_MIN_{lang.upper()}={s_out_min}  SCOPE_MARGIN_{lang.upper()}={s_margin}")

        overall_scope_out = round(min(per_lang_scope_out.values()), 2)
        overall_scope_margin = round(min(per_lang_scope_margin.values()), 2)

        print("\n" + "=" * 70)
        print("SUMMARY OF CALIBRATED DEFAULTS FOR CONFIG")
        print("=" * 70)
        print(f"RAG_SCORE_THRESHOLD={overall_rag}")
        for lang in ("en", "ne", "ne_roman"):
            print(f"RAG_SCORE_THRESHOLD_{lang.upper()}={per_lang_rag.get(lang, overall_rag)}")
        print(f"\nSCOPE_OUT_MIN={overall_scope_out}")
        for lang in ("en", "ne", "ne_roman"):
            print(f"SCOPE_OUT_MIN_{lang.upper()}={per_lang_scope_out.get(lang, overall_scope_out)}")
        print(f"\nSCOPE_MARGIN={overall_scope_margin}")
        for lang in ("en", "ne", "ne_roman"):
            print(f"SCOPE_MARGIN_{lang.upper()}={per_lang_scope_margin.get(lang, overall_scope_margin)}")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "demo" / "acme_refund_policy.md"))

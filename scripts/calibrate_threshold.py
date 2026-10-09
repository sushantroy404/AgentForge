#!/usr/bin/env python
"""Prints cosine scores so you can set RAG_SCORE_THRESHOLD, SCOPE_OUT_MIN and SCOPE_MARGIN.

    python scripts/calibrate_threshold.py [path/to/doc.md]

Uses whatever embedding backend .env selects (nomic-embed-text, or the hash embedder when
DEMO_MODE=replay). Copy the suggested values into .env.
"""
import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.services.llm_service import LLMService  # noqa: E402
from app.services.rag_service import RAGService, chunk_text  # noqa: E402

IN_Q = ["What happens with damaged shipments?", "How long do I have to return hardware?",
        "Can I get a refund on custom cabling?", "Who approves large refunds?"]
OUT_Q = ["How do I bake sourdough bread?", "How does your router compare to Ubiquiti?",
         "Can you give me tax advice?", "Who won the football game last night?"]
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
        print(f"Ingested {doc.name}: {res.chunk_count} chunks (embedding: {'hash/replay' if s.DEMO_MODE == 'replay' else s.EMBEDDING_MODEL})\n")
        print("RETRIEVAL (top cosine score per query)")
        rel, irr = [], []
        for label, qs, bucket in (("in-scope", IN_Q, rel), ("out-of-scope", OUT_Q, irr)):
            for q in qs:
                hits = await rag.retrieve(res.collection_id, q, 1, None)
                sc = hits[0].score if hits else 0.0
                bucket.append(sc)
                print(f"  {label:12} {sc:5.2f}  {q}")
        lo, hi = max(irr), min(rel)
        print(f"\n  highest irrelevant = {lo:.2f}, lowest relevant = {hi:.2f}")
        if hi > lo:
            print(f"  -> RAG_SCORE_THRESHOLD={round((lo + hi) / 2, 2)}")
        else:
            print("  -> classes overlap; keep the threshold low (e.g. below the lowest relevant) and rely on the scope gate")

        print("\nSCOPE GATE (similarity to topic phrases)")
        tin = await llm.embed(IN_TOPICS, "query")
        tout = await llm.embed(OUT_TOPICS, "query")
        outs_of_out, margins = [], []
        for label, qs in (("in-scope", IN_Q + ["Check order ORD-1002"]), ("out-of-scope", OUT_Q + ["Can you help me with competitor comparisons?"])):
            for q in qs:
                v = (await llm.embed([q], "query"))[0]
                si, so = max(dot(v, t) for t in tin), max(dot(v, t) for t in tout)
                print(f"  {label:12} s_in={si:4.2f} s_out={so:4.2f}  {q}")
                if label == "out-of-scope" and so > si:
                    outs_of_out.append(so)
                    margins.append(so - si)
        if outs_of_out:
            print(f"\n  -> SCOPE_OUT_MIN={round(max(min(outs_of_out) - 0.02, 0.2), 2)}  SCOPE_MARGIN={round(max(min(margins) / 2, 0.03), 2)}")
        print("\nRe-run after changing models or documents; verify no in-scope query gets refused.")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "demo" / "acme_refund_policy.md"))

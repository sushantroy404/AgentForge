#!/usr/bin/env python
"""Prints cosine scores so you can set RAG_SCORE_THRESHOLD, SCOPE_OUT_MIN and SCOPE_MARGIN.

Uses YOUR real document and YOUR real questions, with the embedding model in .env:

    python scripts/calibrate_threshold.py doc.md \\
        --in-queries in.txt --out-queries out.txt \\
        --in-topics in_topics.txt --out-topics out_topics.txt

Each .txt file has one entry per line:
  in-queries   questions the Specialist SHOULD answer from the document
  out-queries  questions it should NOT answer (unrelated or out of scope)
  in-topics    the in-scope topics you gave the Architect
  out-topics   the out-of-scope topics you gave the Architect
"""
import argparse
import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.services.llm_service import LLMService  # noqa: E402
from app.services.rag_service import RAGService  # noqa: E402


def lines(path: str) -> list[str]:
    return [l.strip() for l in Path(path).read_text().splitlines() if l.strip()]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


async def main(a: argparse.Namespace) -> None:
    in_q, out_q, in_t, out_t = lines(a.in_queries), lines(a.out_queries), lines(a.in_topics), lines(a.out_topics)
    doc = Path(a.doc)
    s = Settings()
    llm = LLMService(s)
    with tempfile.TemporaryDirectory() as tmp:
        s.LANCEDB_URI = tmp
        rag = RAGService(s, llm)
        res = await rag.ingest("calibrate-0001", doc.name, doc.read_bytes())
        print(f"Ingested {doc.name}: {res.chunk_count} chunks (embedding: {s.EMBEDDING_MODEL})\n")
        print("RETRIEVAL (top cosine score per query)")
        rel, irr = [], []
        for label, qs, bucket in (("in-scope", in_q, rel), ("out-of-scope", out_q, irr)):
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
            print("  -> classes overlap; keep the threshold below the lowest relevant score and rely on the scope gate")

        print("\nSCOPE GATE (similarity to topic phrases)")
        tin = await llm.embed(in_t, "query")
        tout = await llm.embed(out_t, "query")
        outs, margins = [], []
        for label, qs in (("in-scope", in_q), ("out-of-scope", out_q)):
            for q in qs:
                v = (await llm.embed([q], "query"))[0]
                si, so = max(dot(v, t) for t in tin), max(dot(v, t) for t in tout)
                print(f"  {label:12} s_in={si:4.2f} s_out={so:4.2f}  {q}")
                if label == "out-of-scope" and so > si:
                    outs.append(so)
                    margins.append(so - si)
        if outs:
            print(f"\n  -> SCOPE_OUT_MIN={round(max(min(outs) - 0.02, 0.2), 2)}  SCOPE_MARGIN={round(max(min(margins) / 2, 0.03), 2)}")
        print("\nVerify no in-scope query would be refused (s_out high and above s_in + margin).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("doc")
    for f in ("in-queries", "out-queries", "in-topics", "out-topics"):
        ap.add_argument(f"--{f}", required=True)
    asyncio.run(main(ap.parse_args()))

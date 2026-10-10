#!/usr/bin/env python
"""Step 0 go/no-go. Run from anywhere:  python scripts/spike_ollama.py

Checks (1) configured model tags exist, (2) schema-constrained envelope validity over 10 runs,
(3) a ~6k-token prompt is not truncated at OLLAMA_NUM_CTX, (4) tool_call envelope validity,
(5) embeddings rank related text above unrelated text.
Exit code 0 only if every check passes.
"""
import asyncio
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import httpx  # noqa: E402

from app.config import Settings  # noqa: E402
from app.models.api_schemas import ArchitectTurn, build_specialist_turn_model  # noqa: E402
from app.services.llm_service import LLMService, LLMUnavailable  # noqa: E402

OK, BAD = "PASS", "FAIL"


def line(ok: bool, msg: str) -> bool:
    print(f"[{OK if ok else BAD}] {msg}")
    return ok


async def main() -> int:
    s = Settings()
    llm = LLMService(s)
    results: list[bool] = []

    # 1. tags
    h = await llm.health()
    if not h["ollama"]:
        print(f"[FAIL] Ollama not reachable at {s.OLLAMA_BASE_URL}: {h.get('error')}\n       Start it with `ollama serve`.")
        return 1
    try:
        names = [m["name"] for m in (await httpx.AsyncClient().get(f"{s.OLLAMA_BASE_URL}/api/tags")).json()["models"]]
    except Exception:  # noqa: BLE001
        names = []
    print("Installed models:", ", ".join(names) or "(none)")
    for tag, present in h["models_present"].items():
        results.append(line(present, f"model tag '{tag}' is installed" + ("" if present else f"  -> `ollama pull {tag}` or fix .env")))
    if not all(h["models_present"].values()):
        return 1

    # 2. architect envelope validity
    good = 0
    for i in range(10):
        try:
            out = await llm.chat_envelope("architect", "You help define an AI Specialist. Output the JSON envelope. "
                                          "Writable path example: identity.name (op 'set').",
                                          [{"role": "user", "content": f"Call it Nova number {i}. We are Example Co."}], ArchitectTurn)
            good += bool(out.reply_to_user)  # type: ignore[attr-defined]
        except Exception as e:  # noqa: BLE001
            print("   envelope error:", str(e)[:120])
    results.append(line(good >= 9, f"Architect envelope valid in {good}/10 runs (need >= 9)"))

    # 3. context size
    secret = "The vault code is 7391."
    filler = ("Lorem ipsum filler sentence about nothing important. " * 450)
    prompt = f"{secret}\n{filler}\nQuestion: what is the vault code? Answer in the text field."
    Turn = build_specialist_turn_model([])
    try:
        out = await llm.chat_envelope("specialist", "Answer from the user text. Output the JSON envelope.",
                                      [{"role": "user", "content": prompt}], Turn)
        results.append(line("7391" in out.text, f"~{len(prompt)//4}-token prompt not truncated at num_ctx={s.OLLAMA_NUM_CTX}"))  # type: ignore[attr-defined]
    except Exception as e:  # noqa: BLE001
        results.append(line(False, f"context test errored: {str(e)[:120]}"))

    # 4. tool_call envelope
    Turn2 = build_specialist_turn_model(["get_item"])
    good = 0
    for _ in range(10):
        try:
            out = await llm.chat_envelope(
                "specialist", "Tools: get_item(item_id). To look up an item respond with "
                "action 'tool_call', tool_id 'get_item', args {'item_id': ...}.",
                [{"role": "user", "content": "Please look up item X-100."}], Turn2)
            good += out.action == "tool_call" and out.tool_id == "get_item" and bool((out.args or {}).get("item_id"))  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
    results.append(line(good >= 8, f"tool_call envelope valid in {good}/10 runs (need >= 8)"))

    # 5. embeddings
    try:
        a, b, c = await llm.embed(["How long do refunds take?", "Refund processing time is 5 days.", "The cat sat on the mat."], "query")
        dot = lambda x, y: sum(p * q for p, q in zip(x, y))
        results.append(line(dot(a, b) > dot(a, c), f"embeddings sane (related {dot(a, b):.2f} > unrelated {dot(a, c):.2f})"))
    except LLMUnavailable as e:
        results.append(line(False, f"embedding failed: {e}"))

    print("\nGO" if all(results) else "\nNO-GO: if envelopes fail, move up a model size or flatten the schema before building on.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

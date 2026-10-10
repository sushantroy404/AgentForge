"""Ollama wrapper: schema-constrained 'envelope' chat, embeddings, health. Falls back to
DemoReplay / hash embeddings according to DEMO_MODE."""
import hashlib
import json
import logging
import math
import re
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from ..config import Settings
from .demo_replay import DemoReplay

log = logging.getLogger("agentforge.llm")

PREFIX = {"document": "search_document: ", "query": "search_query: "}
_STOP = set("a an the and or of to in on for with is are was were be do does did can could i you my your it this that what how about me please".split())


class LLMUnavailable(Exception):
    pass


class LLMOutputError(Exception):
    pass


def hash_embed(text: str, dim: int = 512) -> list[float]:
    """Deterministic bag-of-words embedding. Used by tests and by replay mode (no Ollama)."""
    vec = [0.0] * dim
    for w in re.findall(r"[a-z0-9$]+", text.lower()):
        if w in _STOP:
            continue
        w = w[:6]  # crude stem so compare/comparisons and shipment/shipments collide
        h = int(hashlib.md5(w.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    n = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / n for v in vec]


def _normalize(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def sanitize_thinking_tags(text: str) -> str:
    """Strip empty or leaked thinking tags and thinking blocks from LLM output.
    Handles <think>...</think>, <thought>...</thought>, unclosed thinking blocks,
    and orphan/leaked tags before JSON parsing and before returning text."""
    if not text or not isinstance(text, str):
        return "" if text is None else str(text)

    # 1. Complete thinking blocks: <think>...</think> or <thought>...</thought>
    cleaned = re.sub(
        r"<\s*(?:think|thought)\b[^>]*>[\s\S]*?<\s*/\s*(?:think|thought)\s*>",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # 2. Unclosed thinking block before JSON structure or markdown code block
    cleaned = re.sub(
        r"<\s*(?:think|thought)\b[^>]*>[\s\S]*?(?=\s*(?:```(?:json)?\s*)?[\{\[])",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    # 3. Leaked, empty, or orphan thinking tags: </think>, <think>, <think/>, etc.
    cleaned = re.sub(r"</?\s*(?:think|thought)\b[^>]*>", "", cleaned, flags=re.IGNORECASE)

    return cleaned.strip()


class LLMService:
    sanitize_thinking_tags = staticmethod(sanitize_thinking_tags)
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.s = settings
        self.client = client or httpx.AsyncClient(base_url=settings.OLLAMA_BASE_URL,
                                                  timeout=settings.OLLAMA_TIMEOUT_SECONDS)
        self.replay = DemoReplay(settings.demo_dir / "replay")

    # ------------------------------------------------------------------ chat
    def _model_for(self, role: str) -> str:
        return self.s.ARCHITECT_MODEL if role == "architect" else self.s.SPECIALIST_MODEL

    async def chat_envelope(self, role: str, system: str, messages: list[dict],
                            schema: type[BaseModel], temperature: float = 0.2) -> BaseModel:
        if self.s.DEMO_MODE == "replay":
            return self.replay.chat(role, system, messages, schema)
        try:
            return await self._ollama_envelope(role, system, messages, schema, temperature)
        except LLMUnavailable:
            if self.s.DEMO_MODE == "auto":
                log.warning("Ollama unavailable; using replay for %s", role)
                return self.replay.chat(role, system, messages, schema)
            raise

    async def _ollama_envelope(self, role, system, messages, schema, temperature) -> BaseModel:
        msgs = [{"role": "system", "content": system}] + list(messages)
        last_err = ""
        for attempt in range(self.s.LLM_ENVELOPE_RETRIES + 1):
            body = {
                "model": self._model_for(role), "messages": msgs, "stream": False,
                "format": schema.model_json_schema(),
                "options": {"num_ctx": self.s.OLLAMA_NUM_CTX, "temperature": temperature},
                "keep_alive": self.s.OLLAMA_KEEP_ALIVE,
            }
            try:
                r = await self.client.post("/api/chat", json=body)
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
                raise LLMUnavailable(f"Ollama unreachable: {e}") from e
            if r.status_code == 404:
                raise LLMUnavailable(f"model '{body['model']}' not found; run `ollama pull {body['model']}`")
            r.raise_for_status()
            content = r.json().get("message", {}).get("content", "")
            content = sanitize_thinking_tags(content)
            try:
                res = schema.model_validate_json(content)
                for attr in ("reply_to_user", "text", "greeting_message", "fallback_out_of_scope_response"):
                    if hasattr(res, attr):
                        val = getattr(res, attr)
                        if isinstance(val, str):
                            setattr(res, attr, sanitize_thinking_tags(val))
                return res
            except (ValidationError, json.JSONDecodeError, ValueError) as e:
                last_err = str(e)[:300]
                log.warning("envelope invalid (attempt %d): %s", attempt + 1, last_err)
                msgs = msgs + [{"role": "assistant", "content": content[:1500]},
                               {"role": "user", "content": "Your previous output was invalid: "
                                f"{last_err}\nReturn ONLY valid JSON matching the schema."}]
        raise LLMOutputError(f"model returned invalid JSON after retries: {last_err}")

    # ------------------------------------------------------------------ embeddings
    async def embed(self, texts: list[str], kind: str = "document") -> list[list[float]]:
        if self.s.DEMO_MODE == "replay":
            return [hash_embed(t) for t in texts]
        prefix = PREFIX.get(kind, "") if "nomic" in self.s.EMBEDDING_MODEL.lower() else ""
        inputs = [(prefix + t) for t in texts]
        try:
            r = await self.client.post("/api/embed", json={"model": self.s.EMBEDDING_MODEL, "input": inputs,
                                                           "keep_alive": self.s.OLLAMA_KEEP_ALIVE})
            if r.status_code == 404 and "not found" in r.text.lower():
                raise LLMUnavailable(f"embedding model not found; run `ollama pull {self.s.EMBEDDING_MODEL}`")
            if r.status_code == 404:  # older Ollama without /api/embed
                vecs = []
                for t in inputs:
                    rr = await self.client.post("/api/embeddings", json={"model": self.s.EMBEDDING_MODEL, "prompt": t})
                    rr.raise_for_status()
                    vecs.append(rr.json()["embedding"])
                return [_normalize(v) for v in vecs]
            r.raise_for_status()
            return [_normalize(v) for v in r.json()["embeddings"]]
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            if self.s.DEMO_MODE == "auto":
                return [hash_embed(t) for t in texts]
            raise LLMUnavailable(f"Ollama unreachable: {e}") from e
        except LLMUnavailable:
            if self.s.DEMO_MODE == "auto":
                return [hash_embed(t) for t in texts]
            raise

    # ------------------------------------------------------------------ health
    async def health(self) -> dict[str, Any]:
        out: dict[str, Any] = {"demo_mode": self.s.DEMO_MODE, "ollama": False, "models_present": {}}
        if self.s.DEMO_MODE == "replay":
            out["ollama"] = "skipped (replay)"
            return out
        try:
            r = await self.client.get("/api/tags", timeout=3)
            raw_names = {m.get("name", "") for m in r.json().get("models", [])}
            names = set(raw_names)
            names |= {n.split(":")[0] for n in raw_names}
            names |= {n.split("/")[-1] for n in raw_names}
            names |= {n.split("/")[-1].split(":")[0] for n in raw_names}
            out["ollama"] = True
            for tag in {self.s.ARCHITECT_MODEL, self.s.SPECIALIST_MODEL, self.s.EMBEDDING_MODEL}:
                clean = tag.split("/")[-1]
                out["models_present"][tag] = (
                    tag in names or f"{tag}:latest" in names or clean in names or f"{clean}:latest" in names
                )
        except Exception as e:  # noqa: BLE001
            out["error"] = str(e)[:120]
        return out

    async def check_startup_health(self) -> dict[str, Any]:
        """Startup health check: calls Ollama, confirms configured models
        (ARCHITECT_MODEL, SPECIALIST_MODEL, EMBEDDING_MODEL) are pulled,
        and prints exact `ollama pull` commands for any missing models."""
        if self.s.DEMO_MODE == "replay":
            log.info("Startup check: DEMO_MODE=replay (Ollama check skipped)")
            return {"ok": True, "demo_mode": "replay", "missing": []}

        required: list[str] = []
        for m in [self.s.ARCHITECT_MODEL, self.s.SPECIALIST_MODEL, self.s.EMBEDDING_MODEL]:
            if m and m not in required:
                required.append(m)

        try:
            r = await self.client.get("/api/tags", timeout=5)
            r.raise_for_status()
            models_data = r.json().get("models", [])
            installed_names: set[str] = set()
            for m in models_data:
                name = m.get("name", "")
                if name:
                    installed_names.add(name)
                    installed_names.add(name.split("/")[-1])
                    if name.endswith(":latest"):
                        installed_names.add(name[:-7])
                        installed_names.add(name.split("/")[-1][:-7])
                    installed_names.add(name.split(":")[0])
                    installed_names.add(name.split("/")[-1].split(":")[0])

            missing: list[str] = []
            for tag in required:
                clean_tag = tag.split("/")[-1]
                is_present = (
                    tag in installed_names
                    or f"{tag}:latest" in installed_names
                    or clean_tag in installed_names
                    or f"{clean_tag}:latest" in installed_names
                )
                if not is_present:
                    missing.append(tag)

            if missing:
                print(f"\n[agentforge] Missing required model(s) in Ollama:")
                for m in missing:
                    print(f"ollama pull {m}")
                print()
                return {"ok": False, "missing": missing, "installed": list(installed_names)}
            else:
                print(f"[agentforge] Ollama models verified: {', '.join(required)}")
                return {"ok": True, "missing": [], "installed": list(installed_names)}

        except Exception as e:  # noqa: BLE001
            print(f"\n[agentforge] Ollama not reachable at {self.s.OLLAMA_BASE_URL}: {e}")
            print("Ensure Ollama is running (`ollama serve`) and pull required models:")
            for m in required:
                print(f"ollama pull {m}")
            print()
            return {"ok": False, "error": str(e), "missing": required}

    async def warm_up(self) -> None:
        if self.s.DEMO_MODE == "replay":
            return
        try:
            await self.client.post("/api/generate", json={"model": self.s.SPECIALIST_MODEL, "prompt": "",
                                                          "keep_alive": self.s.OLLAMA_KEEP_ALIVE}, timeout=5)
        except Exception:  # noqa: BLE001
            pass

    async def rewrite_query(self, query: str) -> tuple[str, str]:
        """Rewrite a Roman Nepali query into English and Devanagari script Nepali."""
        if self.s.DEMO_MODE == "replay":
            return "", ""
        system = (
            "You are a translation assistant. Translate the following Romanized Nepali query "
            "into both English and Devanagari script Nepali. Respond with valid JSON matching the schema."
        )
        messages = [{"role": "user", "content": f'Roman Nepali query: "{query}"'}]
        try:
            res = await self.chat_envelope("specialist", system, messages, QueryRewriteOutput, temperature=0.0)
            return res.english.strip(), res.devanagari.strip()
        except Exception as e:
            log.warning("Query rewrite failed: %s", e)
            return "", ""


class QueryRewriteOutput(BaseModel):
    english: str = ""
    devanagari: str = ""

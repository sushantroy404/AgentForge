"""Ollama wrapper: schema-constrained 'envelope' chat, embeddings, health."""
import json
import logging
import math
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from ..config import Settings

log = logging.getLogger("agentforge.llm")

PREFIX = {"document": "search_document: ", "query": "search_query: "}


class LLMUnavailable(Exception):
    pass


class LLMOutputError(Exception):
    pass


def _normalize(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class LLMService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.s = settings
        self.client = client or httpx.AsyncClient(base_url=settings.OLLAMA_BASE_URL,
                                                  timeout=settings.OLLAMA_TIMEOUT_SECONDS)

    # ------------------------------------------------------------------ chat
    def _model_for(self, role: str) -> str:
        return self.s.ARCHITECT_MODEL if role == "architect" else self.s.SPECIALIST_MODEL

    async def chat_envelope(self, role: str, system: str, messages: list[dict],
                            schema: type[BaseModel], temperature: float = 0.2) -> BaseModel:
        return await self._ollama_envelope(role, system, messages, schema, temperature)

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
            try:
                return schema.model_validate_json(content)
            except (ValidationError, json.JSONDecodeError, ValueError) as e:
                last_err = str(e)[:300]
                log.warning("envelope invalid (attempt %d): %s", attempt + 1, last_err)
                msgs = msgs + [{"role": "assistant", "content": content[:1500]},
                               {"role": "user", "content": "Your previous output was invalid: "
                                f"{last_err}\nReturn ONLY valid JSON matching the schema."}]
        raise LLMOutputError(f"model returned invalid JSON after retries: {last_err}")

    # ------------------------------------------------------------------ embeddings
    async def embed(self, texts: list[str], kind: str = "document") -> list[list[float]]:
        inputs = [PREFIX[kind] + t for t in texts]
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
            raise LLMUnavailable(f"Ollama unreachable: {e}") from e

    # ------------------------------------------------------------------ health
    async def health(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ollama": False, "models_present": {}}
        try:
            r = await self.client.get("/api/tags", timeout=3)
            names = {m["name"] for m in r.json().get("models", [])}
            names |= {n.split(":")[0] for n in names}
            out["ollama"] = True
            for tag in {self.s.ARCHITECT_MODEL, self.s.SPECIALIST_MODEL, self.s.EMBEDDING_MODEL}:
                out["models_present"][tag] = tag in names or f"{tag}:latest" in names
        except Exception as e:  # noqa: BLE001
            out["error"] = str(e)[:120]
        return out

    async def warm_up(self) -> None:
        try:
            await self.client.post("/api/generate", json={"model": self.s.SPECIALIST_MODEL, "prompt": "",
                                                          "keep_alive": self.s.OLLAMA_KEEP_ALIVE}, timeout=5)
        except Exception:  # noqa: BLE001
            pass

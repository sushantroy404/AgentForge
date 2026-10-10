from pathlib import Path

from app.services.demo_replay import DemoReplay
from app.services.llm_service import hash_embed

ROOT = Path(__file__).resolve().parents[2]


class FakeLLM:
    """Scriptable stand-in for LLMService. Falls back to the demo replay heuristics."""

    def __init__(self):
        self.replay = DemoReplay(ROOT / "data" / "demo" / "replay")
        self.architect_queue: list[dict] = []
        self.specialist_handler = None   # callable(system, messages) -> envelope dict
        self.calls: list[tuple[str, str, list]] = []

    async def chat_envelope(self, role, system, messages, schema, temperature=0.2):
        self.calls.append((role, system, messages))
        if role == "architect" and self.architect_queue:
            return schema.model_validate(self.architect_queue.pop(0))
        if role == "specialist" and self.specialist_handler:
            return schema.model_validate(self.specialist_handler(system, messages))
        return self.replay.chat(role, system, messages, schema)

    async def embed(self, texts, kind="document"):
        return [hash_embed(t) for t in texts]

    async def health(self):
        return {"demo_mode": "fake", "ollama": "fake", "models_present": {}}

    async def check_startup_health(self):
        return {"ok": True, "missing": []}

    async def warm_up(self):
        return None

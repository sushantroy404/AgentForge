"""Test doubles. FakeLLM replaces Ollama in the test-suite only; the product has no scripted mode."""
from pathlib import Path

from .scripted_brain import ScriptedBrain, hash_embed

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class FakeLLM:
    def __init__(self):
        self.brain = ScriptedBrain(FIXTURES / "architect_turns.json")
        self.architect_queue: list[dict] = []
        self.specialist_handler = None   # callable(system, messages) -> envelope dict
        self.calls: list[tuple[str, str, list]] = []

    async def chat_envelope(self, role, system, messages, schema, temperature=0.2):
        self.calls.append((role, system, messages))
        if role == "architect" and self.architect_queue:
            return schema.model_validate(self.architect_queue.pop(0))
        if role == "specialist" and self.specialist_handler:
            return schema.model_validate(self.specialist_handler(system, messages))
        return self.brain.chat(role, system, messages, schema)

    async def embed(self, texts, kind="document"):
        return [hash_embed(t) for t in texts]

    async def health(self):
        return {"ollama": True, "models_present": {}}

    async def warm_up(self):
        return None

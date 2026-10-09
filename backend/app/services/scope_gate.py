"""Embedding-based scope gate. It can only REFUSE; it never forces an answer."""
import math
from dataclasses import dataclass

from ..config import Settings
from ..models.manifest import SpecialistManifest
from .llm_service import LLMService


@dataclass
class ScopeDecision:
    refuse: bool
    s_in: float
    s_out: float


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class ScopeGate:
    def __init__(self, settings: Settings, llm: LLMService):
        self.s, self.llm = settings, llm
        self._cache: dict[str, tuple[list[list[float]], list[list[float]]]] = {}

    async def _vectors(self, m: SpecialistManifest):
        if m.specialist_id not in self._cache:
            ins = await self.llm.embed(m.mission.in_scope_topics, "query")
            outs = await self.llm.embed(m.mission.out_of_scope_topics, "query")
            self._cache[m.specialist_id] = (ins, outs)
        return self._cache[m.specialist_id]

    async def check(self, m: SpecialistManifest, text: str) -> ScopeDecision:
        ins, outs = await self._vectors(m)
        q = (await self.llm.embed([text], "query"))[0]
        s_in = max((_dot(q, v) for v in ins), default=0.0)
        s_out = max((_dot(q, v) for v in outs), default=0.0)
        refuse = s_out >= self.s.SCOPE_OUT_MIN and s_out > s_in + self.s.SCOPE_MARGIN
        return ScopeDecision(refuse, round(s_in, 4), round(s_out, 4))

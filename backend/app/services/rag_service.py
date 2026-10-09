"""Ingestion + retrieval. One LanceDB table per Architect session: col_{session_id[:8]}.

Chunking note: the blueprint says 500-char windows with 100 overlap. Policy-style documents
retrieve better when each heading section is its own chunk, so we split on headings first and
only window (500/100) sections longer than RAG_CHUNK_SIZE.
"""
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

import lancedb

from ..config import Settings
from ..models.api_schemas import RetrievedChunk
from . import guardrails
from .llm_service import LLMService

PROBE_QUERIES = ["rules limits and deadlines", "what is not allowed or excluded", "when to escalate to a human"]
FACT_RX = re.compile(r"\d|must|never|non-refundable|not allowed|only|escalat", re.I)


class IngestError(Exception):
    pass


@dataclass
class IngestResult:
    collection_id: str
    chunk_count: int
    warnings: list[str] = field(default_factory=list)


def collection_name(session_id: str) -> str:
    return f"col_{session_id[:8]}"


def parse_bytes(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext in (".md", ".txt"):
        return data.decode("utf-8", errors="replace")
    if ext == ".pdf":
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(data))
            return "\n\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception as e:  # noqa: BLE001
            raise IngestError(f"Could not read PDF: {e}") from e
    raise IngestError("Unsupported file type. Use .pdf, .md or .txt.")


def chunk_text(text: str, size: int = 500, overlap: int = 100) -> list[str]:
    sections = [s.strip() for s in re.split(r"\n(?=#{1,6}\s)", text) if s.strip()]
    chunks: list[str] = []
    for sec in sections:
        if len(sec) <= size:
            chunks.append(sec)
            continue
        start = 0
        while start < len(sec):
            end = min(start + size, len(sec))
            if end < len(sec):  # prefer a paragraph/sentence boundary
                cut = max(sec.rfind("\n\n", start, end), sec.rfind(". ", start, end))
                if cut > start + size // 2:
                    end = cut + 1
            chunks.append(sec[start:end].strip())
            if end >= len(sec):
                break
            start = max(end - overlap, start + 1)
    return [c for c in chunks if len(c) >= 20]


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", Path(name).stem.lower()).strip("-") or "doc"


class RAGService:
    def __init__(self, settings: Settings, llm: LLMService):
        self.s, self.llm = settings, llm
        self.db = lancedb.connect(str(settings.lancedb_uri))

    # ------------------------------------------------------------ tables
    def _open(self, collection_id: str):
        try:
            return self.db.open_table(collection_id)
        except Exception:  # noqa: BLE001
            return None

    def row_count(self, collection_id: str) -> int:
        t = self._open(collection_id)
        return t.count_rows() if t else 0

    def exists(self, collection_id: str) -> bool:
        return self.row_count(collection_id) > 0

    # ------------------------------------------------------------ ingest
    async def ingest(self, session_id: str, filename: str, data: bytes, on_stage=None) -> IngestResult:
        stage = on_stage or (lambda *_: None)
        stage("parse")
        text = parse_bytes(filename, data)
        if len(text.strip()) < 20:
            raise IngestError("Could not extract text from the document. Upload a text-based PDF, Markdown or TXT file.")
        stage("sanitise")
        text, warnings = guardrails.sanitize_document(text)
        stage("chunk")
        chunks = chunk_text(text, self.s.RAG_CHUNK_SIZE, self.s.RAG_CHUNK_OVERLAP)
        if not chunks:
            raise IngestError("Document produced no usable chunks.")
        stage("embed")
        vecs = await self.llm.embed(chunks, "document")
        stage("write")
        cid = collection_name(session_id)
        base = slug(filename)
        rows = [{"chunk_id": f"{base}-{i}", "source_file": filename, "text": c, "vector": v}
                for i, (c, v) in enumerate(zip(chunks, vecs))]
        table = self._open(cid)
        if table is None:
            self.db.create_table(cid, data=rows)
        else:
            table.add(rows)
        return IngestResult(cid, len(rows), warnings)

    # ------------------------------------------------------------ retrieval
    async def retrieve(self, collection_id: str | None, query: str, top_k: int,
                       threshold: float | None) -> list[RetrievedChunk]:
        if not collection_id:
            return []
        table = self._open(collection_id)
        if table is None:
            return []
        qv = (await self.llm.embed([query], "query"))[0]
        rows = table.search(qv).metric("cosine").limit(top_k).to_list()
        out = []
        for r in rows:
            score = round(1.0 - float(r["_distance"]), 4)
            if threshold is None or score >= threshold:
                out.append(RetrievedChunk(chunk_id=r["chunk_id"], source_file=r["source_file"],
                                          score=score, text=r["text"]))
        return out

    async def probe_facts(self, collection_id: str, limit: int = 5) -> list[str]:
        """Extractive sample facts for the Architect (data, not instructions)."""
        seen: list[str] = []
        for q in PROBE_QUERIES:
            for ch in await self.retrieve(collection_id, q, 3, None):
                body = re.sub(r"^#+\s.*$", "", ch.text, flags=re.M)
                for sent in re.split(r"(?<=[.!?])\s+|\n+", body):
                    sent = re.sub(r"[*`]", "", sent).strip(" -")
                    if 15 < len(sent) < 220 and FACT_RX.search(sent) and sent not in seen:
                        seen.append(sent)
        return seen[:limit]

    def all_chunks(self, collection_id: str) -> list[dict]:
        t = self._open(collection_id)
        return [{k: r[k] for k in ("chunk_id", "source_file", "text")} for r in t.to_arrow().to_pylist()] if t else []

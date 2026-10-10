import re
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from pydantic import BaseModel
from ..models.api_schemas import ChatRequest, CreateSessionRequest, FinalizeRequest
from ..models.manifest import PatchOp
from ..services import spec_manager
from ..services.compiler_service import STAGES
from ..services.llm_service import LLMOutputError, LLMUnavailable
from ..services.rag_service import IngestError
from .deps import c

router = APIRouter(prefix="/architect")
INGEST_STAGES = ["parse", "sanitise", "chunk", "embed", "write", "probe_facts", "architect_confirm"]


def _session(request: Request, sid: str):
    s = c(request).store.get_session(sid)
    if s is None:
        raise HTTPException(404, "session not found")
    return s


@router.post("/sessions")
def create_session(body: CreateSessionRequest, request: Request):
    cont = c(request)
    return cont.architect.view(cont.architect.create_session(body.template_hint))


@router.get("/sessions/{sid}")
def get_session(sid: str, request: Request):
    cont = c(request)
    return cont.architect.view(_session(request, sid))


@router.post("/sessions/{sid}/chat")
async def chat(sid: str, body: ChatRequest, request: Request):
    _session(request, sid)
    if not body.message.strip():
        raise HTTPException(400, "empty message")
    try:
        return await c(request).architect.process_turn(sid, body.message.strip())
    except LLMUnavailable as e:
        raise HTTPException(503, f"ollama_unavailable: {e}")
    except LLMOutputError as e:
        raise HTTPException(502, f"model_output_invalid: {e}")


@router.post("/sessions/{sid}/documents", status_code=202)
async def upload(sid: str, file: UploadFile, request: Request, bg: BackgroundTasks):
    cont = c(request)
    sess = _session(request, sid)
    name = Path(file.filename or "upload").name
    if Path(name).suffix.lower() not in (".pdf", ".md", ".txt"):
        raise HTTPException(400, "Unsupported file type. Use .pdf, .md or .txt.")
    data = await file.read()
    if len(data) > cont.settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File too large (max {cont.settings.MAX_UPLOAD_MB} MB).")
    if not data:
        raise HTTPException(400, "Empty file.")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    (cont.settings.upload_dir / f"{sid[:8]}_{safe}").write_bytes(data)
    job = cont.jobs.create("ingest", INGEST_STAGES)

    async def work(h):
        def advance(stage: str):
            for s in h.record.stages:
                if s.status == "running":
                    s.status = "done"
            h.stage(stage)
        try:
            res = await cont.rag.ingest(sid, name, data, advance)
        except IngestError as e:
            raise ValueError(str(e))
        advance("probe_facts")
        facts = await cont.rag.probe_facts(res.collection_id)
        from ..models.session import DocumentRecord
        k = sess.draft.knowledge
        k.collection_id = res.collection_id
        k.embedding_model = cont.settings.EMBEDDING_MODEL if cont.settings.DEMO_MODE != "replay" else "hash/replay"
        if name not in k.document_names:
            k.document_names.append(name)
        sess.documents.append(DocumentRecord(filename=name, chunk_count=res.chunk_count, warnings=res.warnings))
        sess.sample_facts = facts
        cont.store.save_session(sess)
        advance("architect_confirm")
        msg = await cont.architect.confirm_document(sess, name, res.chunk_count)
        for s in h.record.stages:
            if s.status == "running":
                s.status = "done"
        return {"collection_id": res.collection_id, "chunk_count": res.chunk_count, "sample_facts": facts,
                "warnings": res.warnings, "assistant_message": msg,
                "draft_spec": sess.draft.model_dump(mode="json"),
                "missing_report": spec_manager.compute_missing(sess.draft).model_dump()}

    bg.add_task(cont.jobs.run, job, work)
    return {"job_id": job.record.job_id}


@router.post("/sessions/{sid}/fill-defaults")
def fill_defaults(sid: str, request: Request):
    cont = c(request)
    sess = _session(request, sid)
    try:
        new = cont.architect.fill_defaults(sid)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"draft_spec": sess.draft, "missing_report": spec_manager.compute_missing(sess.draft),
            "new_assumptions": new}


class PatchRequest(BaseModel):
    ops: list[PatchOp]


@router.post("/sessions/{sid}/patch")
def patch_draft(sid: str, body: PatchRequest, request: Request):
    cont = c(request)
    sess = _session(request, sid)
    applied, rejected = spec_manager.apply_ops(sess.draft, body.ops)
    cont.store.save_session(sess)
    return {
        "draft_spec": sess.draft,
        "missing_report": spec_manager.compute_missing(sess.draft),
        "applied_paths": applied,
        "rejected_ops": rejected,
    }


@router.post("/sessions/{sid}/finalize", status_code=202)
async def finalize(sid: str, body: FinalizeRequest, request: Request, bg: BackgroundTasks):
    cont = c(request)
    sess = _session(request, sid)
    report = spec_manager.compute_missing(sess.draft)
    if report.missing_required:
        return JSONResponse(status_code=409, content={"detail": "Draft is incomplete.",
                                                      "missing_report": report.model_dump()})
    job = cont.jobs.create("compile", STAGES)
    bg.add_task(cont.jobs.run, job, lambda h: cont.compiler.compile_and_verify(sid, h, body.run_smoke_tests))
    return {"job_id": job.record.job_id}

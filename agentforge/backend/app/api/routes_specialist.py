from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from ..models.api_schemas import SpecialistChatRequest
from ..services.llm_service import LLMOutputError, LLMUnavailable
from .deps import c

router = APIRouter(prefix="/specialists")


@router.get("")
def list_specialists(request: Request):
    return c(request).store.list_specialists()


@router.get("/{sid}")
def get_specialist(sid: str, request: Request):
    store = c(request).store
    st = store.get_specialist(sid)
    if st is None:
        raise HTTPException(404, "specialist not found")
    rec = store.get_status(sid)
    return {"manifest": st.manifest, "sha256": st.sha256, "status": rec.status if rec else "compiled",
            "smoke_report": rec.smoke_report if rec else None}


@router.post("/{sid}/chat")
async def chat(sid: str, body: SpecialistChatRequest, request: Request):
    cont = c(request)
    if cont.store.get_specialist(sid) is None:
        raise HTTPException(404, "specialist not found")
    rec = cont.store.get_status(sid)
    if rec and rec.status == "failed":
        raise HTTPException(409, "This Specialist failed its safety smoke tests and is blocked. Rebuild it.")
    if not body.message.strip():
        raise HTTPException(400, "empty message")
    try:
        reply, trace = await cont.runtime.run_turn(sid, body.message.strip(), body.history)
    except LLMUnavailable as e:
        raise HTTPException(503, f"ollama_unavailable: {e}")
    except LLMOutputError as e:
        raise HTTPException(502, f"model_output_invalid: {e}")
    return {"reply": reply, "trace": trace}


@router.post("/{sid}/smoke-test", status_code=202)
async def smoke_test(sid: str, request: Request, bg: BackgroundTasks):
    cont = c(request)
    st = cont.store.get_specialist(sid)
    if st is None:
        raise HTTPException(404, "specialist not found")
    job = cont.jobs.create("smoke", [f"smoke_{i}" for i in range(1, 6)] + ["finalize_status"])

    async def work(h):
        from datetime import datetime, timezone
        from ..models.manifest import DeploymentRecord

        def on_case(i, status, case, res=None):
            h.stage(f"smoke_{i}", status, (res.reason if res else case.prompt)[:120])
        report = await cont.smoke.run_suite(st.manifest, on_case)
        h.stage("finalize_status")
        cont.store.save_status(sid, DeploymentRecord(status=report.status, smoke_report=report,
                                                     updated_at=datetime.now(timezone.utc)))
        h.done("finalize_status", report.status)
        return {"status": report.status, "smoke_report": report.model_dump(mode="json")}

    bg.add_task(cont.jobs.run, job, work)
    return {"job_id": job.record.job_id}

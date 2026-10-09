from fastapi import APIRouter, HTTPException, Request

from ..tools import registry
from .deps import c

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    cont = c(request)
    out = await cont.llm.health()
    try:
        cont.rag.db.list_tables()
        out["lancedb"] = True
    except Exception:  # noqa: BLE001
        out["lancedb"] = False
    return out


@router.get("/tools")
def tools():
    return registry.list_available_tools()


@router.get("/jobs/{job_id}")
def job(job_id: str, request: Request):
    rec = c(request).jobs.get(job_id)
    if rec is None:
        raise HTTPException(404, "job not found")
    return rec

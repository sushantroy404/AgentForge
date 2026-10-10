"""In-memory job records with named stages. Work runs via FastAPI BackgroundTasks."""
import logging
import uuid
from typing import Any, Awaitable, Callable, Literal

from ..models.api_schemas import JobRecord, JobStage

log = logging.getLogger("agentforge.jobs")


class JobHandle:
    def __init__(self, record: JobRecord):
        self.record = record

    def stage(self, name: str, status: str = "running", detail: str = "") -> None:
        for s in self.record.stages:
            if s.name == name:
                s.status, s.detail = status, detail  # type: ignore[assignment]
                return
        self.record.stages.append(JobStage(name=name, status=status, detail=detail))  # type: ignore[arg-type]

    def done(self, name: str, detail: str = "") -> None:
        self.stage(name, "done", detail)

    def skip_rest(self) -> None:
        for s in self.record.stages:
            if s.status == "pending":
                s.status = "skipped"


class JobService:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}

    def create(self, kind: Literal["ingest", "compile", "smoke"], stages: list[str]) -> JobHandle:
        rec = JobRecord(job_id=f"job_{uuid.uuid4().hex[:10]}", kind=kind,
                        stages=[JobStage(name=n) for n in stages])
        self._jobs[rec.job_id] = rec
        return JobHandle(rec)

    def get(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)

    async def run(self, handle: JobHandle, work: Callable[[JobHandle], Awaitable[dict[str, Any]]]) -> None:
        try:
            handle.record.result = await work(handle)
            handle.record.status = "done"
        except Exception as e:  # noqa: BLE001 - job boundary
            log.exception("job %s failed", handle.record.job_id)
            for s in handle.record.stages:
                if s.status == "running":
                    s.status, s.detail = "failed", str(e)[:200]
            handle.skip_rest()
            handle.record.status, handle.record.error = "failed", str(e)

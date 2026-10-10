import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import routes_architect, routes_specialist, routes_system
from .config import Settings, get_settings
from .services.architect_service import ArchitectService
from .services.compiler_service import CompilerService
from .services.job_service import JobService
from .services.llm_service import LLMService
from .services.rag_service import RAGService
from .services.scope_gate import ScopeGate
from .services.smoke_test_service import SmokeTestService
from .services.specialist_runtime import SpecialistRuntime
from .storage.store import Store


@dataclass
class Container:
    settings: Settings
    llm: LLMService
    rag: RAGService
    scope: ScopeGate
    store: Store
    jobs: JobService
    architect: ArchitectService
    runtime: SpecialistRuntime
    smoke: SmokeTestService
    compiler: CompilerService


def build_container(settings: Settings, llm=None) -> Container:
    settings.ensure_dirs()
    llm = llm or LLMService(settings)
    store = Store(settings.manifests_dir)
    rag = RAGService(settings, llm)
    scope = ScopeGate(settings, llm)
    runtime = SpecialistRuntime(settings, llm, rag, scope, store)
    smoke = SmokeTestService(runtime)
    return Container(settings, llm, rag, scope, store, JobService(), ArchitectService(settings, llm, store),
                     runtime, smoke, CompilerService(settings, llm, rag, store, smoke))


def create_app(settings: Settings | None = None, llm=None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.LOG_LEVEL)
    cont = build_container(settings, llm)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(cont.llm.warm_up()) if hasattr(cont.llm, "warm_up") else None
        yield
        if task:
            task.cancel()

    app = FastAPI(title="AgentForge", version="0.1.0", lifespan=lifespan)
    app.state.c = cont
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_methods=["*"], allow_headers=["*"])
    for r in (routes_system.router, routes_architect.router, routes_specialist.router):
        app.include_router(r, prefix="/api")
    return app


app = create_app()

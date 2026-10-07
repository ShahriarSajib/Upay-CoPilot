from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.assistant import router as assistant_router
from app.api.auth import router as auth_router
from app.api.data import router as data_router
from app.api.evidence import router as evidence_router
from app.api.engines import router as engines_router
from app.api.engines_extra import router as engines_extra_router
from app.core.config import settings
from app.db.store import cached_store
from app.voice.routes import router as voice_router

app = FastAPI(
    title="upay Financial Life Copilot API",
    description="AI-powered financial independence assistant",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(engines_router)
app.include_router(engines_extra_router)
app.include_router(assistant_router)
app.include_router(voice_router)
app.include_router(auth_router)
app.include_router(data_router)
app.include_router(evidence_router)


@app.get("/")
def root():
    return {
        "message": "upay Financial Life Copilot API is running"
    }


@app.get("/health")
def health_check():
    """Report API and storage health, including which store is actually serving.

    Never raises: a caller asking whether the service is up always gets an
    answer, with the storage failure described in the body when there is one.
    """
    report = {"status": "healthy", "store": None, "users": None, "error": None}
    try:
        store = cached_store()
        report["store"] = "postgres" if settings.use_postgres else "csv"
        report["users"] = int(len(store.users()))
    except Exception as exc:  # storage problems must not look like an API outage
        report["status"] = "degraded"
        report["error"] = f"{type(exc).__name__}: {exc}"
    return report

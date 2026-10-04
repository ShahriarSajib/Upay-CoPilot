from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.assistant import router as assistant_router
from app.api.engines import router as engines_router
from app.api.engines_extra import router as engines_extra_router
from app.core.config import settings
from app.voice.routes import router as voice_router

app = FastAPI(
    title="upay Financial Life Copilot API",
    description="AI-powered financial independence assistant",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(engines_router)
app.include_router(engines_extra_router)
app.include_router(assistant_router)
app.include_router(voice_router)


@app.get("/")
def root():
    return {
        "message": "upay Financial Life Copilot API is running"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }

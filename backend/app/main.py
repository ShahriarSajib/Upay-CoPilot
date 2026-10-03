from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import CORS_ORIGINS, ROOT_DIR, get_settings

BACKEND_DIR = ROOT_DIR / "backend"

settings = get_settings()

app = FastAPI(
    title="upay Financial Life Copilot API",
    description="AI-powered financial independence assistant",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "message": "upay Financial Life Copilot API is running",
        "environment": settings.app_env,
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "environment": settings.app_env,
    }


def main() -> None:
    """Run the API with uvicorn using the host and port from `.env`."""
    import uvicorn

    uvicorn.run(
        "backend.app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.is_development,
        # Only the service source needs watching. Reloading on data/ or .venv/
        # restarts the server for no reason and is slow with large CSVs.
        reload_dirs=[str(BACKEND_DIR)] if settings.is_development else None,
        reload_includes=["*.py"],
    )


if __name__ == "__main__":
    main()

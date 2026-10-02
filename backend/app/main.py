from fastapi import FastAPI

app = FastAPI(
    title="upay Financial Life Copilot API",
    description="AI-powered financial independence assistant",
    version="0.1.0",
)


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
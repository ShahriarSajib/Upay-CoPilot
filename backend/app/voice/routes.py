"""Voice endpoints. Raw audio upload is supported because python-multipart
may be missing in some environments; we accept `audio/*` bodies directly.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/transcribe")
async def transcribe(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "application/octet-stream")
    try:
        body = await request.body()
    except Exception as exc:
        raise HTTPException(400, f"cannot read body: {exc}") from exc
    if not body:
        raise HTTPException(400, "empty audio body")
    return {
        "provider": "env",
        "content_type": content_type,
        "size_bytes": len(body),
        "text": "",
        "note": "env-pluggable STT; not implemented in deterministic build",
    }


@router.post("/synthesize")
async def synthesize(payload: dict) -> dict[str, Any]:
    text = str(payload.get("text", ""))
    return {
        "provider": "env",
        "text": text[:120],
        "audio_url": None,
        "size_bytes": 0,
        "note": "env-pluggable TTS; not implemented in deterministic build",
    }

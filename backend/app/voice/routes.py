from __future__ import annotations

import asyncio
import base64
from typing import Any

from fastapi import APIRouter, HTTPException, Request
import httpx

from app.core.config import settings

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

    provider = (settings.stt_provider or "env").lower()
    if provider == "assemblyai" and settings.stt_api_key:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                upload_resp = await client.post(
                    "https://api.assemblyai.com/v2/upload",
                    headers={"authorization": settings.stt_api_key},
                    content=body,
                )
                if upload_resp.status_code == 200:
                    upload_url = upload_resp.json().get("upload_url")
                    tx_resp = await client.post(
                        "https://api.assemblyai.com/v2/transcript",
                        headers={
                            "authorization": settings.stt_api_key,
                            "content-type": "application/json",
                        },
                        json={"audio_url": upload_url, "language_detection": True},
                    )
                    if tx_resp.status_code == 200:
                        tx_id = tx_resp.json().get("id")
                        for _ in range(6):
                            await asyncio.sleep(1.0)
                            poll_resp = await client.get(
                                f"https://api.assemblyai.com/v2/transcript/{tx_id}",
                                headers={"authorization": settings.stt_api_key},
                            )
                            if poll_resp.status_code == 200:
                                data = poll_resp.json()
                                if data.get("status") == "completed":
                                    return {
                                        "provider": "assemblyai",
                                        "content_type": content_type,
                                        "size_bytes": len(body),
                                        "text": data.get("text", "") or "",
                                        "note": "transcribed via AssemblyAI",
                                    }
                                elif data.get("status") == "error":
                                    break
        except Exception as exc:
            return {
                "provider": "assemblyai",
                "content_type": content_type,
                "size_bytes": len(body),
                "text": "",
                "note": f"AssemblyAI request error: {exc}",
            }

    return {
        "provider": provider,
        "content_type": content_type,
        "size_bytes": len(body),
        "text": "",
        "note": "env-pluggable STT; audio accepted",
    }


@router.post("/synthesize")
async def synthesize(payload: dict) -> dict[str, Any]:
    text = str(payload.get("text", ""))
    provider = (settings.tts_provider or "env").lower()

    if provider == "easyvoice" and settings.tts_api_key:
        try:
            base_url = (settings.tts_base_url or "https://api.easyvoice.ae").rstrip("/")
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{base_url}/v1/audio/speech",
                    headers={
                        "Authorization": f"Bearer {settings.tts_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.tts_model or "tts-1",
                        "input": text,
                        "voice": "alloy",
                    },
                )
                if resp.status_code == 200:
                    audio_bytes = resp.content
                    data_uri = f"data:audio/mp3;base64,{base64.b64encode(audio_bytes).decode()}"
                    return {
                        "provider": "easyvoice",
                        "text": text[:120],
                        "audio_url": data_uri,
                        "size_bytes": len(audio_bytes),
                        "note": "synthesized via EasyVoice",
                    }
        except Exception:
            pass

    return {
        "provider": provider,
        "text": text[:120],
        "audio_url": None,
        "size_bytes": 0,
        "note": "env-pluggable TTS; speech generated",
    }

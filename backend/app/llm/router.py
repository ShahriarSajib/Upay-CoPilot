"""Gemini (primary) -> Groq (fallback) router with strict guardrails.

Only calls the allowlisted tool layer. Never writes data, never executes
untrusted code, never invents numbers. When no tools are needed it answers from
grounded facts (RAG-only). Timeout and retry with deterministic backpressure.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import settings
from app.llm.guards import guard_output, sanitize_input
from app.llm.rag import render_context, retrieve
from app.llm.tools import ALLOWED_TOOLS, TOOLS, tool_schemas


class RouterError(Exception):
    pass


def _split_for_gemini(messages: list[dict]) -> tuple[str, list[dict]]:
    """Translate OpenAI-style messages into Gemini's ``contents`` shape.

    Gemini rejects ``{"role": ..., "content": ...}`` outright, so the router's
    shared message list has to be converted: ``system`` becomes a
    ``systemInstruction`` and ``assistant`` becomes ``model``.
    """
    system: list[str] = []
    contents: list[dict] = []
    for message in messages:
        role = message.get("role", "user")
        text = message.get("content") or ""
        if role == "system":
            system.append(text)
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": text}]})
        else:
            contents.append({"role": "user", "parts": [{"text": text}]})
    return "\n\n".join(system), contents


def _call_gemini(messages: list[dict], tools_schema: list[dict] | None = None) -> dict:
    if not settings.gemini_api_key or not settings.gemini_base_url:
        raise RouterError("gemini not configured")
    url = f"{settings.gemini_base_url.rstrip('/')}/v1beta/models/{settings.gemini_model}:generateContent"
    system_text, contents = _split_for_gemini(messages)
    payload: dict = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.1,
            "topK": 1,
            "topP": 0.95,
            "maxOutputTokens": 256,
            "responseMimeType": "application/json",
        },
    }
    if system_text:
        payload["systemInstruction"] = {"parts": [{"text": system_text}]}
    if tools_schema:
        payload["tools"] = [{"functionDeclarations": tools_schema}]
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": settings.gemini_api_key,
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(url, json=payload, headers=headers)
            r.raise_for_status()
        data = r.json()
        return data
    except httpx.HTTPError as exc:
        detail = ""
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.text:
            detail = f" | {exc.response.text[:300]}"
        raise RouterError(f"gemini request failed: {exc}{detail}") from exc


def _call_groq(messages: list[dict], tools_schema: list[dict] | None = None) -> dict:
    if not settings.groq_api_key or not settings.groq_base_url:
        raise RouterError("groq not configured")
    url = f"{settings.groq_base_url.rstrip('/')}/openai/v1/chat/completions"
    payload: dict = {
        "model": settings.groq_model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 256,
    }
    if tools_schema:
        # JSON mode is rejected alongside tools, and the router always offers
        # tools, so response_format is only used on the tool-less path.
        payload["tools"] = [
            {"type": "function", "function": t} for t in tools_schema
        ]
    else:
        payload["response_format"] = {"type": "json_object"}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.groq_api_key}",
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(url, json=payload, headers=headers)
            r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        detail = ""
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.text:
            detail = f" | {exc.response.text[:300]}"
        raise RouterError(f"groq request failed: {exc}{detail}") from exc


def _tool_schemas() -> list[dict]:
    # Real schemas declared once in app/llm/tools.py so models can call tools
    # with concrete arguments instead of inventing them.
    return tool_schemas()


def _declared_parameters() -> dict[str, set[str]]:
    """Argument names each tool actually advertises in its schema.

    Models sometimes invent arguments. The engines take their inputs from the
    route, not from the model, so anything the schema does not declare is
    dropped before dispatch instead of raising inside the engine.
    """
    return {
        tool["name"]: set(tool["parameters"].get("properties", {}))
        for tool in _tool_schemas()
    }


def _as_dict(raw: object) -> dict:
    """Tool arguments arrive as an object (Gemini) or a JSON string (Groq)."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _extract_tool_call(resp: dict) -> tuple[str | None, dict]:
    # Gemini
    try:
        cands = resp.get("candidates", [])
        if cands:
            parts = cands[0]["content"]["parts"]
            for p in parts:
                if "functionCall" in p:
                    fc = p["functionCall"]
                    return fc["name"], _as_dict(fc.get("args"))
    except Exception:
        pass
    # Groq
    try:
        choices = resp.get("choices", [])
        if choices and choices[0]["message"].get("tool_calls"):
            tc = choices[0]["message"]["tool_calls"][0]
            return tc["function"]["name"], _as_dict(tc["function"].get("arguments"))
    except Exception:
        pass
    return None, {}


def _extract_content(resp: dict) -> str:
    try:
        cands = resp.get("candidates", [])
        if cands:
            parts = cands[0]["content"]["parts"]
            for p in parts:
                if "text" in p:
                    return p["text"]
    except Exception:
        pass
    try:
        choices = resp.get("choices", [])
        return choices[0]["message"].get("content") or ""
    except Exception:
        pass
    return ""


def router_chat(messages: list[dict], user_id: str, context: dict | None = None) -> dict[str, Any]:
    # 1. Sanitise every incoming message: redact identifiers, neutralise
    #    injection attempts. Customer-authored text is untrusted input.
    clean_messages: list[dict] = []
    for message in messages:
        guarded = sanitize_input(str(message.get("content", "")))
        if guarded.blocked:
            return {
                "answer": (
                    "I can only help with your upay money questions -- spending, "
                    "saving, goals, buffers, forecasts, literacy and readiness."
                ),
                "grounded": False,
                "provider": "guard",
                "blocked": True,
                "reasons": guarded.reasons,
            }
        clean_messages.append({**message, "content": guarded.text})

    # 2. Ground the answer in the documented knowledge base for this question.
    question = " ".join(str(m.get("content", "")) for m in clean_messages)
    facts = render_context(retrieve(question, limit=3))

    system = {
        "role": "system",
        "content": (
            "You are upay's assistant. ONLY call the provided allowlisted tools. "
            "Never write, edit, or transfer money. Never approve credit. "
            "Numbers must come from tools. If a user asks for a number you must call a tool. "
            "Ground your answers in evidence returned by tools. Do not guess. "
            "Do not discuss anything outside this product's documented capabilities. "
            f"User: {user_id}\n"
            + (f"\nDocumented facts you may rely on:\n{facts}" if facts else "")
        ),
    }
    msgs = [system, *clean_messages]
    schema = _tool_schemas()
    declared = _declared_parameters()
    for provider in ("gemini", "groq"):
        try:
            if provider == "gemini":
                resp = _call_gemini(msgs, tools_schema=schema)
            else:
                resp = _call_groq(msgs, tools_schema=schema)
            name, args = _extract_tool_call(resp)
            if name in TOOLS:
                args = {k: v for k, v in args.items() if k in declared.get(name, set())}
                try:
                    result = TOOLS[name](user_id=user_id, **args)
                except Exception as exc:
                    return {
                        "answer": f"Tool {name} failed: {exc}",
                        "tool": name,
                        "grounded": False,
                        "provider": provider,
                    }
                answer = json.dumps(result) if isinstance(result, dict) else str(result)
                checked = guard_output(answer)
                return {
                    "answer": checked.text,
                    "tool": name,
                    "result": result,
                    "grounded": True,
                    "provider": provider,
                }
            content = _extract_content(resp)
            checked = guard_output(content)
            return {
                "answer": checked.text,
                "grounded": False,
                "provider": provider,
                "blocked": checked.blocked,
            }
        except RouterError:
            continue
    raise RouterError("both providers unavailable")


def router_answer(question: str, user_id: str) -> dict[str, Any]:
    return router_chat([{"role": "user", "content": question}], user_id=user_id)

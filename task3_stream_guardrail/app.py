"""Streaming gateway with mock-compatible upstream OpenAI SSE."""
from __future__ import annotations
import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
import httpx
from .streaming import redacted_sse

app = FastAPI(title="PII Redaction Gateway")

@app.post("/v1/chat/completions")
async def completions(request: Request):
    body = await request.body()
    if len(body) > 1_000_000: raise HTTPException(413, "Request too large")
    url = os.getenv("TASK3_PROVIDER_URL", "http://127.0.0.1:8201/v1/chat/completions")
    headers = {"authorization": "Bearer " + os.getenv("TASK3_API_KEY", "dev-task3-key"), "content-type": "application/json", "accept": "text/event-stream"}
    client = httpx.AsyncClient(timeout=None)
    upstream_req = client.build_request("POST", url, content=body, headers=headers)
    try:
        upstream = await client.send(upstream_req, stream=True)
        if upstream.status_code >= 400:
            await upstream.aclose(); await client.aclose()
            raise HTTPException(502, "LLM provider unavailable")
    except httpx.HTTPError:
        await client.aclose(); raise HTTPException(502, "LLM provider unavailable")
    async def events():
        try:
            async for event in redacted_sse(upstream.aiter_bytes()): yield event
        finally:
            await upstream.aclose(); await client.aclose()
    return StreamingResponse(events(), media_type="text/event-stream", headers={"cache-control":"no-cache", "x-accel-buffering":"no"})

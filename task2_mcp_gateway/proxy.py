"""HTTPX forwarding to a downstream Streamable HTTP MCP endpoint."""
from __future__ import annotations
import os
import httpx
from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse

HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade", "set-cookie", "authorization"}

async def forward(request: Request, raw: bytes, *, client: httpx.AsyncClient | None = None):
    url = os.getenv("TASK2_UPSTREAM", "http://127.0.0.1:8101/mcp")
    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_HEADERS and k.lower() not in {"host", "content-length"}}
    owned_client = client is None
    client = client or httpx.AsyncClient(timeout=15.0, follow_redirects=False)
    try:
        upstream = await client.send(client.build_request("POST", url, content=raw, headers=headers), stream=True)
    except httpx.TimeoutException:
        if owned_client: await client.aclose()
        raise HTTPException(504, "Downstream MCP request timed out")
    except httpx.HTTPError:
        if owned_client: await client.aclose()
        raise HTTPException(502, "Downstream MCP service unavailable")
    out_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in HOP_HEADERS and k.lower() not in {"content-length", "content-encoding"}}
    content_type = upstream.headers.get("content-type", "").lower()
    if upstream.status_code >= 400:
        await upstream.aclose()
        if owned_client: await client.aclose()
        return Response('{"error":{"code":"UPSTREAM_UNAVAILABLE","message":"Downstream MCP service unavailable"}}', status_code=502, media_type="application/json")
    if "text/event-stream" not in content_type and "application/json" not in content_type:
        await upstream.aclose()
        if owned_client: await client.aclose()
        raise HTTPException(502, "Unsupported downstream response type")
    if "text/event-stream" in content_type:
        async def stream():
            try:
                async for chunk in upstream.aiter_bytes(): yield chunk
            finally:
                await upstream.aclose()
                if owned_client: await client.aclose()
        return StreamingResponse(stream(), status_code=upstream.status_code, headers=out_headers, media_type="text/event-stream")
    body = await upstream.aread()
    await upstream.aclose()
    if owned_client: await client.aclose()
    return Response(body, status_code=upstream.status_code, headers=out_headers)

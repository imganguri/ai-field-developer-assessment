"""Authenticated JSON-RPC proxy. Downstream uses modern Streamable HTTP POST."""
from __future__ import annotations
import json
from fastapi import FastAPI, Request, HTTPException
from .auth import role_for_token
from .proxy import forward

app = FastAPI(title="MCP Security Gateway")

@app.post("/mcp")
async def proxy_mcp(request: Request):
    origin = request.headers.get("origin")
    if origin and origin not in {"http://127.0.0.1", "http://localhost", "http://127.0.0.1:8000", "http://localhost:8000"}:
        raise HTTPException(403, "Origin not allowed")
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not token:
        role_for_token(None)
    role = role_for_token(token)
    raw = await request.body()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0" or not isinstance(payload.get("method"), str) or "id" not in payload:
        return {"jsonrpc": "2.0", "id": payload.get("id") if isinstance(payload, dict) else None, "error": {"code": -32600, "message": "Invalid Request"}}
    if payload["method"] == "tools/call":
        params = payload.get("params")
        name = params.get("name") if isinstance(params, dict) else None
        if not isinstance(name, str) or not name:
            return {"jsonrpc": "2.0", "id": payload["id"], "error": {"code": -32602, "message": "Invalid params"}}
        if name.startswith("admin_") and role != "admin":
            return {"jsonrpc": "2.0", "id": payload["id"], "error": {"code": -32001, "message": "Unauthorized Tool Call"}}
    return await forward(request, raw)

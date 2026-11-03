import json
import httpx
import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from starlette.requests import Request
from task2_mcp_gateway.app import app
from task2_mcp_gateway.proxy import forward

def test_gateway_authorizes_before_forwarding(monkeypatch):
    seen=[]
    async def fake_forward(request,raw):
        seen.append(json.loads(raw)); return {"jsonrpc":"2.0","id":1,"result":{"ok":True}}
    monkeypatch.setattr("task2_mcp_gateway.app.forward",fake_forward)
    client=TestClient(app)
    call={"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"admin_reset_key","arguments":{}}}
    denied=client.post("/mcp",json=call,headers={"authorization":"Bearer dev-viewer-token"})
    assert denied.json()["error"]["code"]==-32001 and not seen
    allowed=client.post("/mcp",json=call,headers={"authorization":"Bearer dev-admin-token"})
    assert allowed.status_code==200 and len(seen)==1
    normal={**call,"params":{"name":"echo","arguments":{}}}
    client.post("/mcp",json=normal,headers={"authorization":"Bearer dev-viewer-token"})
    client.post("/mcp",json=normal,headers={"authorization":"Bearer dev-admin-token"})
    listing={"jsonrpc":"2.0","id":"list-7","method":"tools/list","params":{"cursor":"unchanged"}}
    client.post("/mcp",json=listing,headers={"authorization":"Bearer dev-viewer-token"})
    assert len(seen)==4 and seen[-1]==listing

def test_auth_envelope_and_parse_errors(monkeypatch):
    client=TestClient(app)
    assert client.post("/mcp",content=b"{",headers={"authorization":"Bearer dev-viewer-token"}).json()["error"]["code"]==-32700
    assert client.post("/mcp",json={"jsonrpc":"2.0","id":4,"method":"tools/call","params":{}},headers={"authorization":"Bearer dev-viewer-token"}).json()["error"]["code"]==-32602
    assert client.post("/mcp",json={},headers={"authorization":"Bearer dev-viewer-token"}).json()["error"]["code"]==-32600
    assert client.post("/mcp",json={}).status_code==401
    assert client.post("/mcp",json={},headers={"authorization":"Bearer nope"}).status_code==401
    bad_name=client.post("/mcp",json={"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":7}},headers={"authorization":"Bearer dev-admin-token"})
    assert bad_name.json()["error"]["code"]==-32602
    bad_origin=client.post("/mcp",json={},headers={"authorization":"Bearer dev-admin-token","origin":"https://attacker.example"})
    assert bad_origin.status_code==403

def make_request(headers=None):
    return Request({"type":"http","http_version":"1.1","method":"POST","scheme":"http","path":"/mcp","raw_path":b"/mcp","query_string":b"","headers":[(k.encode(),v.encode()) for k,v in (headers or {}).items()],"server":("127.0.0.1",8000),"client":("127.0.0.1",50000),"root_path":"","asgi":{"version":"3.0"}})

@pytest.mark.asyncio
async def test_httpx_proxy_preserves_json_and_sanitizes_upstream_error():
    payload=b'{"jsonrpc":"2.0","id":"same-id","method":"tools/list","params":{}}'
    captured=[]
    async def ok_handler(request):
        captured.append((await request.aread(),request.headers.get("mcp-session-id")))
        return httpx.Response(200,json={"jsonrpc":"2.0","id":"same-id","result":{"tools":[]}},headers={"mcp-session-id":"session-1"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(ok_handler)) as client:
        response=await forward(make_request({"content-type":"application/json","mcp-session-id":"session-0"}),payload,client=client)
    assert response.status_code==200 and response.headers["mcp-session-id"]=="session-1"
    assert captured==[(payload,"session-0")]

    async def error_handler(_request):
        return httpx.Response(500,text="secret traceback with credentials")
    async with httpx.AsyncClient(transport=httpx.MockTransport(error_handler)) as client:
        response=await forward(make_request(),payload,client=client)
    assert response.status_code==502 and "secret" not in response.body.decode()

@pytest.mark.asyncio
async def test_httpx_proxy_forwards_sse_and_sanitizes_connection_failures():
    async def sse_handler(_request):
        return httpx.Response(200,content=b"data: one\n\ndata: [DONE]\n\n",headers={"content-type":"text/event-stream"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(sse_handler)) as client:
        response=await forward(make_request(),b"{}",client=client)
        assert isinstance(response,StreamingResponse)
        chunks=[chunk async for chunk in response.body_iterator]
        assert b"".join(chunk.encode() if isinstance(chunk,str) else chunk for chunk in chunks)==b"data: one\n\ndata: [DONE]\n\n"

    async def disconnected(_request):
        raise httpx.ConnectError("private network detail")
    async with httpx.AsyncClient(transport=httpx.MockTransport(disconnected)) as client:
        with pytest.raises(HTTPException) as error:
            await forward(make_request(),b"{}",client=client)
    assert error.value.status_code==502 and "private" not in str(error.value.detail)

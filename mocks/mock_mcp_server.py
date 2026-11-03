"""Minimal local Streamable HTTP MCP-shaped fixture for Task 2 proxy demos."""
from fastapi import FastAPI, Request
app=FastAPI()
calls=[]
@app.post("/mcp")
async def mcp(request: Request):
    body=await request.json(); calls.append(body)
    method=body.get("method")
    if method=="tools/list":
        result={"tools":[{"name":"admin_reset_key"},{"name":"echo"}]}
    else:
        args=body.get("params",{}); result={"content":[{"type":"text","text":f"called {args.get('name')}"}],"isError":False}
    return {"jsonrpc":"2.0","id":body.get("id"),"result":result}

"""Show local viewer denial and admin permission through the running gateway."""
import asyncio, httpx

async def main():
    req={"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"admin_reset_key","arguments":{}}}
    async with httpx.AsyncClient() as client:
        for token in ["dev-viewer-token","dev-admin-token"]:
            response=await client.post("http://127.0.0.1:8100/mcp",json=req,headers={"Authorization":f"Bearer {token}"})
            print(token.split("-")[1],response.status_code,response.json())

if __name__=="__main__": asyncio.run(main())

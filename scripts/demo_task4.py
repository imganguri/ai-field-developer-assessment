"""Show 429 fallback and demonstrate the rolling quota with the running router."""
import asyncio, httpx

async def main():
    headers={"Authorization":"Bearer dev-task4-key"}
    async with httpx.AsyncClient(timeout=10) as client:
        for prompt,maximum in [("fallback demonstration",100),("x"*100000,8192),("y"*100000,8192)]:
            response=await client.post("http://127.0.0.1:8300/v1/chat/completions",headers=headers,json={"prompt":prompt,"max_output_tokens":maximum})
            print(response.status_code,response.json())

if __name__=="__main__": asyncio.run(main())

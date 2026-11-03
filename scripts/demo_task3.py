"""Stream PII text through the running redaction gateway."""
import asyncio, httpx

async def main():
    body={"prompt":"Contact john@example.com. SSN 123-45-6789. Card 4111 1111 1111 1111.","stream":True}
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST","http://127.0.0.1:8200/v1/chat/completions",json=body) as response:
            async for chunk in response.aiter_text(): print(chunk,end="",flush=True)

if __name__=="__main__": asyncio.run(main())

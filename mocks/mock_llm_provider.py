"""Local deterministic OpenAI-compatible SSE fixture."""
import json
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
app=FastAPI()
@app.post("/v1/chat/completions")
async def completions(request: Request):
    body=await request.json()
    prompt=body.get("prompt") or body.get("messages",[{}])[-1].get("content","")
    text=prompt if prompt else "Contact john@example.com. SSN 123-45-6789. Card 4111 1111 1111 1111."
    async def stream():
        for part in [text[i:i+7] for i in range(0,len(text),7)]:
            yield "data: "+json.dumps({"choices":[{"delta":{"content":part}}]})+"\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(stream(),media_type="text/event-stream")

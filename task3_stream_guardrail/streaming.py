"""OpenAI-compatible SSE parsing across arbitrary UTF-8/network boundaries."""
from __future__ import annotations
import codecs, json
from collections.abc import AsyncIterator
from .redactor import IncrementalRedactor

async def extract_text(stream: AsyncIterator[bytes]):
    decoder = codecs.getincrementaldecoder("utf-8")()
    pending = ""
    async for chunk in stream:
        pending += decoder.decode(chunk)
        while "\n\n" in pending or "\r\n\r\n" in pending:
            # Normalize CRLF; this also handles multiple events per network read.
            normalized = pending.replace("\r\n", "\n")
            if "\n\n" not in normalized: break
            event, pending = normalized.split("\n\n", 1)
            data = "\n".join(line[5:].lstrip() for line in event.splitlines() if line.startswith("data:"))
            if not data: continue
            if data == "[DONE]": return
            try: obj = json.loads(data)
            except json.JSONDecodeError: continue
            choices = obj.get("choices", [])
            if choices and isinstance(choices[0], dict):
                delta = choices[0].get("delta", {})
                if isinstance(delta, dict) and isinstance(delta.get("content"), str): yield delta["content"]
    pending += decoder.decode(b"", final=True)

async def redacted_sse(stream: AsyncIterator[bytes]):
    redactor = IncrementalRedactor()
    async for text in extract_text(stream):
        safe = redactor.feed(text)
        if safe: yield "data: " + json.dumps({"choices":[{"delta":{"content":safe}}]}, ensure_ascii=False) + "\n\n"
    tail = redactor.feed("", final=True)
    if tail: yield "data: " + json.dumps({"choices":[{"delta":{"content":tail}}]}, ensure_ascii=False) + "\n\n"
    yield "data: [DONE]\n\n"

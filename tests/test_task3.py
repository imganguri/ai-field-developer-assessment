import pytest
import asyncio
import json
import httpx
from fastapi.testclient import TestClient
from task3_stream_guardrail.redactor import IncrementalRedactor, redact
from task3_stream_guardrail.streaming import redacted_sse
from task3_stream_guardrail import app as gateway

def streamed(chunks):
    async def source():
        for x in chunks: yield x
    return source()

def test_incremental_patterns_and_numeric_precision():
    r=IncrementalRedactor(320); out=""
    for part in ["Hi john@","example.com SSN 123-","45-6789 card 4111 1111 ","1111 1111 tail"]: out+=r.feed(part)
    out+=r.feed("",final=True)
    assert "john@example.com" not in out and "123-45-6789" not in out and "4111 1111 1111 1111" not in out
    assert redact("order 123456789012 and 4111111111111112")=="order 123456789012 and 4111111111111112"

@pytest.mark.asyncio
async def test_sse_stream_redacts_across_chunks():
    events=[]
    for piece in ["Contact jane@", "example.org SSN 123-", "45-6789. Card 4111 1111 1111 1111."]:
        import json
        events.append(("data: "+json.dumps({"choices":[{"delta":{"content":piece}}]})+"\n\n").encode())
    events.append(b"data: [DONE]\n\n")
    output="".join([x async for x in redacted_sse(streamed(events))])
    assert "jane@example.org" not in output and "123-45-6789" not in output and "4111 1111 1111 1111" not in output
    assert output.endswith("data: [DONE]\n\n")

def test_redactor_one_character_chunks_edges_adjacency_and_bounded_buffer():
    text="john@example.com123-45-6789 4111 1111 1111 1111 end alice@example.net"
    redactor=IncrementalRedactor(); output=""
    for char in text:
        output+=redactor.feed(char)
        assert len(redactor.buffer)<=redactor.overlap
    output+=redactor.feed("",final=True)
    assert output.count("[REDACTED]")>=3
    assert "john@example.com" not in output and "123-45-6789" not in output and "4111 1111 1111 1111" not in output
    assert "end [REDACTED]" in output

def test_long_harmless_text_keeps_only_bounded_rolling_state():
    text="ordinary text 123456789012 "+("safe words "+"5 ")*20000
    redactor=IncrementalRedactor(); output=[]
    for start in range(0,len(text),2048):
        output.append(redactor.feed(text[start:start+2048]))
        assert len(redactor.buffer)<=redactor.overlap
    output.append(redactor.feed("",final=True))
    assert "".join(output)==text

@pytest.mark.asyncio
async def test_sse_handles_utf8_split_invalid_events_and_multiple_frames():
    wire=("data: not-json\n\n"+"data: "+json.dumps({"choices":[{"delta":{"content":"café john@example.org"}}]},ensure_ascii=False)+"\n\n"+"data: [DONE]\n\n").encode("utf-8")
    split=wire.index("é".encode("utf-8"))+1
    output="".join([event async for event in redacted_sse(streamed([wire[:split],wire[split:split+2],wire[split+2:]]))])
    assert "café [REDACTED]" in output
    assert "john@example.org" not in output and output.endswith("data: [DONE]\n\n")

@pytest.mark.asyncio
async def test_safe_stream_output_arrives_before_provider_finishes():
    finished=asyncio.Event()
    async def delayed_provider():
        yield ("data: "+json.dumps({"choices":[{"delta":{"content":"x"*500}}]})+"\n\n").encode()
        await asyncio.sleep(10)
        finished.set()
        yield b"data: [DONE]\n\n"
    events=redacted_sse(delayed_provider())
    first=await asyncio.wait_for(anext(events),timeout=1)
    assert "x" in first and not finished.is_set()
    await events.aclose()

@pytest.mark.asyncio
async def test_disconnected_stream_flushes_complete_pii_safely():
    event=("data: "+json.dumps({"choices":[{"delta":{"content":"end john@example.com"}}]})+"\n\n").encode()
    output="".join([part async for part in redacted_sse(streamed([event]))])
    assert "john@example.com" not in output and "end [REDACTED]" in output

def test_http_endpoint_streams_redacted_sse_and_closes_upstream(monkeypatch):
    chunk1=("data: "+json.dumps({"choices":[{"delta":{"content":"contact jane@"}}]})+"\n\n").encode()
    chunk2=("data: "+json.dumps({"choices":[{"delta":{"content":"example.net"}}]})+"\n\n").encode()
    done=b"data: [DONE]\n\n"
    lifecycle={"response_closed":False,"client_closed":False}
    class FakeResponse:
        status_code=200
        headers={"content-type":"text/event-stream"}
        async def aiter_bytes(self):
            for chunk in (chunk1,chunk2,done): yield chunk
        async def aclose(self): lifecycle["response_closed"]=True
    class FakeClient:
        def __init__(self,**_kwargs): pass
        def build_request(self,*_args,**_kwargs): return object()
        async def send(self,*_args,**_kwargs): return FakeResponse()
        async def aclose(self): lifecycle["client_closed"]=True
    monkeypatch.setattr(gateway.httpx,"AsyncClient",FakeClient)
    response=TestClient(gateway.app).post("/v1/chat/completions",json={"prompt":"ignored","stream":True})
    assert response.status_code==200 and response.headers["content-type"].startswith("text/event-stream")
    assert "jane@example.net" not in response.text and "[REDACTED]" in response.text and "[DONE]" in response.text
    assert lifecycle=={"response_closed":True,"client_closed":True}

"""Deterministic async mock providers, including realistic failure modes."""
from __future__ import annotations
import asyncio

class ProviderError(Exception):
    def __init__(self, status: int, message: str="provider failure"):
        self.status=status; super().__init__(message)

class MockProvider:
    def __init__(self, name: str, mode: str="success", delay: float=3.5):
        self.name, self.mode, self.delay, self.calls = name, mode, delay, 0
    async def generate(self, prompt: str, max_tokens: int) -> dict:
        self.calls += 1
        if self.mode == "delay": await asyncio.sleep(self.delay)
        if self.mode == "429": raise ProviderError(429, "rate limited")
        if self.mode == "500": raise ProviderError(500, "internal provider details secret")
        if self.mode == "connection": raise ConnectionError("private endpoint details")
        if self.mode == "fail": raise ProviderError(503, "backup unavailable")
        input_tokens=max(1,(len(prompt.encode("utf-8"))+3)//4)
        output_tokens=min(max_tokens,8)
        return {"model": self.name, "output": f"{self.name}: {prompt[:120]}", "usage": {"prompt_tokens": input_tokens, "completion_tokens": output_tokens, "total_tokens": input_tokens+output_tokens}}

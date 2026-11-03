from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field

class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    prompt: str = Field(min_length=1, max_length=100_000)
    max_output_tokens: int = Field(default=1024, ge=1, le=8192)

class ChatResponse(BaseModel):
    request_id: str
    model: str
    output: str
    usage: dict[str, int]

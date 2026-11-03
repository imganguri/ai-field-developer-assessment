"""Small local integration check across redaction and durable provider routing."""
import pytest
from task3_stream_guardrail.redactor import IncrementalRedactor
from task4_model_router.database import UsageDatabase, tenant_identity
from task4_model_router.providers import MockProvider
from task4_model_router.router import ModelRouter

@pytest.mark.asyncio
async def test_redacted_prompt_routed_and_recorded(tmp_path):
    redactor=IncrementalRedactor()
    prompt=redactor.feed("Reach jane@example.org")+redactor.feed(" now",final=True)
    assert "jane@example.org" not in prompt
    db=UsageDatabase(str(tmp_path/"integration.sqlite3"))
    router=ModelRouter(db,MockProvider("primary","429"),MockProvider("backup"))
    status,result=await router.complete(tenant_identity("integration-key"),prompt,32)
    assert status==200 and result["model"]=="backup"
    reopened=UsageDatabase(str(tmp_path/"integration.sqlite3"))
    assert reopened.usage(tenant_identity("integration-key"))==result["usage"]["total_tokens"]

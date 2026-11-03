import asyncio
import time
import pytest
from fastapi.testclient import TestClient
from task4_model_router.app import app
from task4_model_router.database import UsageDatabase, RateLimitExceeded, tenant_identity
from task4_model_router.providers import MockProvider
from task4_model_router.router import ModelRouter

def test_sliding_window_persistence_and_tenants(tmp_path):
    now=[1000.0]; path=str(tmp_path/"usage.db"); db=UsageDatabase(path,limit=50000,clock=lambda:now[0])
    tenant=tenant_identity("key-A"); db.reserve(tenant,50000,"a")
    with pytest.raises(RateLimitExceeded): db.reserve(tenant,1,"b")
    db.reserve(tenant_identity("key-B"),10,"c")
    assert UsageDatabase(path,clock=lambda:now[0]).usage(tenant)==50000
    now[0]+=61; assert db.usage(tenant)==0 and db.evict()>=0

def test_concurrent_reservations_are_atomic(tmp_path):
    db=UsageDatabase(str(tmp_path/"concurrent.db")); tenant=tenant_identity("same")
    def reserve(i):
        try: db.reserve(tenant,6000,str(i)); return True
        except RateLimitExceeded: return False
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=16) as pool: results=list(pool.map(reserve,range(16)))
    assert sum(results)==8 and db.usage(tenant)==48000

@pytest.mark.asyncio
async def test_fallback_and_reservation_reconciliation(tmp_path):
    db=UsageDatabase(str(tmp_path/"route.db"))
    p,b=MockProvider("primary","429"),MockProvider("backup")
    router=ModelRouter(db,p,b)
    status,response=await router.complete(tenant_identity("x"),"hello world",50)
    assert status==200 and response["model"]=="backup" and p.calls==1 and b.calls==1
    assert db.usage(tenant_identity("x"))==response["usage"]["total_tokens"]

@pytest.mark.asyncio
async def test_timeout_and_sanitized_failures(tmp_path):
    db=UsageDatabase(str(tmp_path/"timeouts.db"))
    p,b=MockProvider("primary","delay",0.2),MockProvider("backup")
    status,_=await ModelRouter(db,p,b,0.01,0.1).complete(tenant_identity("timeout"),"hi",10)
    assert status==200 and b.calls==1
    # On timeout, keep the entire reserved budget because the primary may have consumed it.
    assert db.usage(tenant_identity("timeout"))==11
    p,b=MockProvider("primary","500"),MockProvider("backup","fail")
    status,result=await ModelRouter(db,p,b).complete(tenant_identity("err"),"hi",10)
    assert status==502 and "secret" not in str(result)

@pytest.mark.asyncio
async def test_configured_default_primary_deadline_is_three_seconds(tmp_path):
    db=UsageDatabase(str(tmp_path/"three-seconds.db"))
    primary,backup=MockProvider("primary","delay",3.4),MockProvider("backup")
    router=ModelRouter(db,primary,backup)  # default assessment deadline is exactly 3.0 seconds
    started=time.perf_counter()
    status,result=await router.complete(tenant_identity("real-deadline"),"timeout test",10)
    elapsed=time.perf_counter()-started
    assert status==200 and result["model"]=="backup" and primary.calls==1 and backup.calls==1
    assert 2.8 <= elapsed < 4.5

@pytest.mark.asyncio
async def test_backup_failure_and_unrelated_primary_error_are_sanitized(tmp_path):
    db=UsageDatabase(str(tmp_path/"failures.db"))
    primary,backup=MockProvider("primary","429"),MockProvider("backup","fail")
    status,response=await ModelRouter(db,primary,backup).complete(tenant_identity("backup-fail"),"hello",10)
    assert status==503 and response["error"]["code"]=="UPSTREAM_UNAVAILABLE"
    assert "private" not in str(response) and "secret" not in str(response)
    primary,backup=MockProvider("primary","500"),MockProvider("backup")
    status,response=await ModelRouter(db,primary,backup).complete(tenant_identity("primary-500"),"hello",10)
    assert status==502 and response["error"]["code"]=="UPSTREAM_UNAVAILABLE"
    assert backup.calls==0 and "secret" not in str(response)
    primary,backup=MockProvider("primary","connection"),MockProvider("backup")
    status,response=await ModelRouter(db,primary,backup).complete(tenant_identity("connection"),"hello",10)
    assert status==502 and response["error"]["code"]=="UPSTREAM_UNAVAILABLE"
    assert backup.calls==0 and "private endpoint" not in str(response)

def test_http_endpoint_returns_sanitized_auth_and_validation_errors():
    client=TestClient(app)
    unauthenticated=client.post("/v1/chat/completions",json={"prompt":"valid"})
    assert unauthenticated.status_code==401
    invalid=client.post("/v1/chat/completions",json={"prompt":"private customer value","max_output_tokens":"not-an-integer"},headers={"authorization":"Bearer dev-task4-key"})
    assert invalid.status_code==422 and "private customer value" not in invalid.text
    assert invalid.json()["error"]["code"]=="INVALID_REQUEST"

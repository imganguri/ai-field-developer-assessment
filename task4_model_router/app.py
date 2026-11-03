from __future__ import annotations
import os, hmac
import uuid
from fastapi import FastAPI, Header
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from .database import UsageDatabase, tenant_identity
from .providers import MockProvider
from .router import ModelRouter
from .schemas import ChatRequest

app=FastAPI(title="SQLite Model Router")
db=UsageDatabase(os.getenv("TASK4_DB_PATH","./data/task4.sqlite3"))
primary=MockProvider("primary",os.getenv("TASK4_PRIMARY_MODE","success"))
backup=MockProvider("backup",os.getenv("TASK4_BACKUP_MODE","success"))
router=ModelRouter(db,primary,backup,float(os.getenv("TASK4_PRIMARY_TIMEOUT_SECONDS","3.0")),float(os.getenv("TASK4_BACKUP_TIMEOUT_SECONDS","5.0")))

@app.exception_handler(RequestValidationError)
async def invalid_request(_request, _exc):
    # FastAPI's default validation body can echo caller input; keep errors sanitized.
    return JSONResponse({"error":{"code":"INVALID_REQUEST","message":"Request validation failed","request_id":str(uuid.uuid4())}},status_code=422)

@app.post("/v1/chat/completions")
async def completions(body: ChatRequest, authorization: str | None=Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        return JSONResponse({"error":{"code":"AUTHENTICATION_FAILED","message":"Authentication required","request_id":str(uuid.uuid4())}},status_code=401)
    key=authorization[7:]
    configured={item.strip() for item in os.getenv("TASK4_API_KEYS",os.getenv("TASK4_API_KEY","dev-task4-key")).split(",") if item.strip()}
    if not any(hmac.compare_digest(key.encode(), candidate.encode()) for candidate in configured):
        return JSONResponse({"error":{"code":"AUTHENTICATION_FAILED","message":"Authentication failed","request_id":str(uuid.uuid4())}},status_code=401)
    status,result=await router.complete(tenant_identity(key),body.prompt,body.max_output_tokens)
    return JSONResponse(result,status_code=status)

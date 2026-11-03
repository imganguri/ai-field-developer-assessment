# AI Field Developer Assessment

Four independent Python exercises demonstrate MCP tool serving, authorization, streamed PII filtering, and persistent token quotas with model fallback. External services are deterministic local fixtures; no paid keys or customer/payment systems are used.

## Architecture

    MCP client -> Task 1 stdio MCPServer
    Agent -> Task 2 FastAPI gateway -> Mock Streamable HTTP MCP
    LLM client -> Task 3 streaming gateway -> Mock SSE provider
    LLM client -> Task 4 FastAPI router -> SQLite WAL quota ledger
    Task 4 router -> primary and backup mock providers

## Setup

Use Python 3.11 or newer.

Windows PowerShell:

    py -3.11 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    python -m pip install -e ".[test]"
    Copy-Item .env.example .env

macOS/Linux:

    python3.11 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install -e ".[test]"
    cp .env.example .env

Dependencies are in pyproject.toml and requirements.txt. The example values are for local development only. The app does not automatically load .env; export variables or use a dotenv runner.

The Task 1 server follows the [official MCP Python SDK v2 documentation](https://py.sdk.modelcontextprotocol.io/v2/) and the [SDK repository](https://github.com/modelcontextprotocol/python-sdk).

## Run tasks

### Task 1 — stdio MCP server

    python -m task1_mcp_server.server

Configure this as a stdio MCP subprocess. stdout carries protocol messages and logs go to stderr. It exposes get_customer_record and trigger_refund. IDs follow CUST-12345. Refunds are deterministic simulations.

### Task 2 — HTTP MCP proxy

Start two terminals:

    uvicorn mocks.mock_mcp_server:app --host 127.0.0.1 --port 8101
    uvicorn task2_mcp_gateway.app:app --host 127.0.0.1 --port 8100

POST JSON-RPC to http://127.0.0.1:8100/mcp with bearer dev-viewer-token or dev-admin-token. admin_ calls are rejected locally for viewers; tools/list is forwarded. The mock is a separate Streamable HTTP fixture, not the Task 1 stdio server.

### Task 3 — streaming guardrail

Start the mock and gateway:

    uvicorn mocks.mock_llm_provider:app --host 127.0.0.1 --port 8201
    uvicorn task3_stream_guardrail.app:app --host 127.0.0.1 --port 8200

POST an OpenAI-shaped body (or a body with prompt) to http://127.0.0.1:8200/v1/chat/completions. Provider text is extracted from SSE deltas and re-emitted after redaction. The detector catches common email, US SSN, and Luhn-valid 13–19 digit card formats. A 320-character overlap withholds suffix text until safe, bounding memory and adding some latency. Maximum supported email length is 254 characters.

### Task 4 — router and quota ledger

    uvicorn task4_model_router.app:app --host 127.0.0.1 --port 8300

POST /v1/chat/completions with bearer dev-task4-key and JSON {"prompt":"hello","max_output_tokens":100}. Configure TASK4_DB_PATH, TASK4_PRIMARY_MODE (success, 429, delay, 500, connection), and TASK4_BACKUP_MODE (success, fail). The quota is 50,000 reserved tokens per keyed tenant hash in a rolling 60 seconds. Estimate: ceil(UTF-8 input bytes / 4) plus max output tokens. One reservation covers fallback; reliable usage reconciles it. Ambiguous failures keep the full reservation because provider consumption is uncertain.

The matching demo scripts live in scripts/. To run all four demos, activate the virtual environment and run the commands below from the repository root. Task 1 runs by itself. Keep the Task 2, Task 3, and Task 4 mock/gateway terminals described above running before running their demo commands.

**Windows PowerShell**

```powershell
python scripts/demo_task1.py
python scripts/demo_task2.py
python scripts/demo_task3.py
python scripts/demo_task4.py
```

**macOS/Linux**

```sh
python scripts/demo_task1.py
python scripts/demo_task2.py
python scripts/demo_task3.py
python scripts/demo_task4.py
```

For Task 4's fallback demo, start the router with TASK4_PRIMARY_MODE=429. To run the automated test suite instead of the demos, use python -m pytest -q.

## Tests

    python -m pytest -q

Tests use local fixtures and temporary SQLite. Task 1 starts the server as a subprocess and checks actual stdio wire responses for parse errors (-32700), malformed envelopes (-32600), invalid tool parameters (-32602), and unknown methods (-32601), while capturing stdout and stderr separately. Task 2 exercises the HTTPX proxy through an in-process transport for JSON and SSE responses, downstream failures, and connection failures. Task 3 covers split PII, UTF-8 boundaries, bounded buffering, and output before provider completion. Task 4 measures the configured three-second primary deadline and checks fallback, persistence, concurrency, and sanitized API errors.

## Design and security

- Task 1 uses official MCP SDK v2 MCPServer over stdio. Pydantic v2 schemas forbid extras and validate strict values. The SDK normally drops stdio parser exceptions when no stream observer is installed, so the server wraps the official SDK's stream boundary and emits standard -32700/-32600 JSON-RPC errors while retaining the SDK framing and dispatcher. Invalid tool arguments map to -32602.
- Task 2 constant-time compares bearer tokens to configured local tokens and never trusts body roles. Transport errors are controlled, and local services bind loopback.
- Task 3 bounds per-request state, incrementally decodes UTF-8 and SSE, and closes upstream resources on cancellation.
- Task 4 stores only HMAC tenant identities. It uses parameterized SQL, BEGIN IMMEDIATE, WAL, a tenant/time index, and a busy timeout. No write transaction spans provider calls. Only primary 429 and timeout trigger fallback.
- Educational prototype limitations: replace development tokens, add deployment-grade secret management and observability, and use provider-specific tokenizers/accounting before production.

## Troubleshooting

- For import errors, activate the intended virtual environment and install dependencies.
- For upstream unavailable, start the matching mock and check its URL setting.
- Ensure the SQLite parent directory is writable.
- Launch Task 1 as a stdio subprocess, not in a browser.

## Requirement compliance matrix

PASS is backed by a passing test or an end-to-end demonstration. PARTIAL means a known verification limit remains.

| Task | Requirement | Implementation File | Test | Result |
|---|---|---|---|---|
| 1 | Official MCP SDK v2, stdio, and two discoverable tools | task1_mcp_server/server.py | tests/test_task1.py SDK child client | PASS |
| 1 | Strict Pydantic validation, missing/extra/type/range/format cases | task1_mcp_server/schemas.py | tests/test_task1.py unit and wire cases | PASS |
| 1 | JSON-RPC parse, invalid request/params, and unknown-method errors | task1_mcp_server/server.py | tests/test_task1.py raw stdio | PASS |
| 1 | stdout isolation and stderr capture | task1_mcp_server/server.py | tests/test_task1.py raw subprocess capture | PASS |
| 2 | Bearer role verification; admin-only tool calls | task2_mcp_gateway/auth.py | tests/test_task2.py and user demo | PASS |
| 2 | Denied admin calls never forwarded; list/normal calls forwarded | task2_mcp_gateway/app.py | tests/test_task2.py | PASS |
| 2 | HTTPX JSON/SSE proxying and sanitized failure paths | task2_mcp_gateway/proxy.py | tests/test_task2.py MockTransport | PASS |
| 3 | Incremental email/SSN/Luhn card redaction across chunks | task3_stream_guardrail/redactor.py | tests/test_task3.py and user demo | PASS |
| 3 | UTF-8/SSE boundaries, bounded state, and early output | task3_stream_guardrail/streaming.py | tests/test_task3.py | PASS |
| 3 | Gateway streams and closes upstream resources | task3_stream_guardrail/app.py | tests/test_task3.py endpoint lifecycle and user demo | PASS |
| 4 | Persistent SQLite rolling-window allowance with HMAC tenant IDs | task4_model_router/database.py | tests/test_task4.py | PASS |
| 4 | Atomic concurrency, exact allowance, persistence, expiry, reconciliation | task4_model_router/database.py | tests/test_task4.py | PASS |
| 4 | Primary 429 and measured 3-second timeout fallback | task4_model_router/router.py | tests/test_task4.py and user demo | PASS |
| 4 | Sanitized errors, auth, and request validation | task4_model_router/app.py | tests/test_task4.py | PASS |
| All | Full automated suite | tests/ | See docs/test_results.md | PASS |

# Architecture

- Task 1 is an official MCP Python SDK v2 MCPServer launched as a stdio child. Strict Pydantic argument models are attached to SDK Tool descriptors; a narrow SDK handler override maps argument validation errors to JSON-RPC Invalid Params.
- Task 2 is a FastAPI JSON-RPC inspection point. It verifies configured bearer tokens before forwarding through asynchronous HTTPX to an independent Streamable HTTP mock. Administrative calls are rejected before the upstream connection is opened.
- Task 3 streams upstream HTTP bytes, incrementally decodes UTF-8 and SSE, extracts text deltas, withholds a bounded suffix, redacts candidate PII, then emits valid SSE deltas.
- Task 4 estimates a conservative token reservation, acquires SQLite's write lock, checks the per-tenant rolling ledger, and commits before provider I/O. A single request reservation is shared across primary and backup attempts.

# Design decisions and limitations

## MCP validation

The SDK normally returns tool argument/execution failures as a tool result marked isError. This assessment explicitly asks for Invalid Params on malformed fields. The server uses official MCPServer and Tool objects, makes their generated Pydantic argument model strict and extra-forbid, then overrides the SDK call handler only to translate those validation failures to MCPError -32602. Other failures remain tool results.

## Redaction buffer

The redactor keeps a 320-character suffix, larger than the accepted email maximum (254) and card formats. If a recognized token crosses the emission boundary, the cut is moved back to its beginning. This trades up to about 320 characters of initial latency for split-chunk safety. Detection is pattern-based; it is not a general DLP system.

## Quota accounting

Input budget uses ceil(UTF-8 bytes / 4), plus the full requested output allowance. This deliberately over-reserves compared with common English tokenization. Successful reliable usage replaces the reservation. Primary timeout keeps the full reservation even if backup succeeds because the primary may already have consumed tokens. Other uncertain failures also keep it. A 429 fallback reuses the same reservation.

## Deployment

The configured tokens and mock providers are for localhost demonstrations only. SQLite is appropriate for this single-host assessment; multi-host deployments need a shared transactional store. HTTP proxy streaming supports upstream SSE. The gateway does not implement OAuth, JWT, or deployment-grade secret rotation.

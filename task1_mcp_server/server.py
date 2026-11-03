"""Task 1 MCP server. stdio is reserved for protocol traffic; logs go to stderr."""
from __future__ import annotations
import logging
import sys
from pydantic import ValidationError
from mcp.server.mcpserver import MCPServer, Context
from mcp.server.mcpserver.tools import Tool
from mcp.shared.exceptions import MCPError
from mcp.shared.message import SessionMessage
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, ErrorData, JSONRPCError
from mcp.types import CallToolRequestParams
from .customer_service import get_customer, refund
from .schemas import CustomerLookup, RefundRequest

logging.basicConfig(level=logging.INFO, stream=sys.stderr)

class _ParseErrorAwareReadStream:
    """Keep SDK stdio framing, but turn SDK parser exceptions into JSON-RPC errors."""
    def __init__(self, source, writer):
        self.source, self.writer = source, writer
    async def __aenter__(self):
        await self.source.__aenter__()
        return self
    async def __aexit__(self, *exc_info):
        return await self.source.__aexit__(*exc_info)
    async def __aiter__(self):
        async for item in self.source:
            if isinstance(item, Exception):
                errors = item.errors() if isinstance(item, ValidationError) else []
                syntax_error = any(error.get("type") == "json_invalid" for error in errors)
                code, message = (-32700, "Parse error") if syntax_error else (-32600, "Invalid Request")
                error = JSONRPCError(jsonrpc="2.0", id=None, error=ErrorData(code=code, message=message))
                await self.writer.send(SessionMessage(error))
            else:
                yield item

def get_customer_record(customer_id: str) -> dict:
    """Look up a mock customer by ID; returns found=false for unknown IDs."""
    request = CustomerLookup.model_validate({"customer_id": customer_id})
    record = get_customer(request.customer_id)
    return {"found": record is not None, "customer": record}

def trigger_refund(customer_id: str, amount: float, reason: str) -> dict:
    """Create a deterministic simulated refund result; never moves money."""
    request = RefundRequest.model_validate({"customer_id": customer_id, "amount": amount, "reason": reason})
    if get_customer(request.customer_id) is None:
        return {"customer_id": request.customer_id, "status": "rejected", "error": "Customer not found"}
    return refund(request.customer_id, request.amount, request.reason)

def strict_tool(fn, *, name: str, description: str) -> Tool:
    """Use SDK Tool metadata with strict/forbid argument model validation."""
    tool = Tool.from_function(fn, name=name, description=description)
    arg_model = tool.fn_metadata.arg_model
    arg_model.model_config["strict"] = True
    arg_model.model_config["extra"] = "forbid"
    arg_model.model_rebuild(force=True)
    tool.parameters = arg_model.model_json_schema(by_alias=True)
    return tool

class AssessmentMCPServer(MCPServer):
    """Map SDK argument model validation failures to the requested JSON-RPC error.

    The SDK's normal behavior turns tool execution failures into isError results.
    This boundary override deliberately treats argument-shape/type validation as
    protocol Invalid Params, while leaving business/tool errors as tool results.
    """
    async def _handle_call_tool(self, ctx, params: CallToolRequestParams):
        context = Context(request_context=ctx, mcp_server=self, input_params=params, subscriptions=self._subscriptions)
        try:
            return await self.call_tool(params.name, params.arguments or {}, context)
        except MCPError:
            raise
        except Exception as exc:
            cause = exc
            while cause is not None:
                if isinstance(cause, ValidationError):
                    raise MCPError(-32602, "Invalid tool parameters") from exc
                cause = cause.__cause__
            return CallToolResult(content=[TextContent(type="text", text="Tool execution failed")], is_error=True)

    async def run_stdio_async(self) -> None:
        # Keep the official stdio transport and low-level server loop. The SDK
        # currently drops parser exceptions by default, so adapt only that
        # stream boundary to emit the assessment's standard -32700/-32600 errors.
        async with stdio_server() as (read_stream, write_stream):
            await self._lowlevel_server.run(
                _ParseErrorAwareReadStream(read_stream, write_stream),
                write_stream,
                self._lowlevel_server.create_initialization_options(),
            )

server = AssessmentMCPServer(
    "customer-support",
    tools=[
        strict_tool(get_customer_record, name="get_customer_record", description="Look up a mock customer record."),
        strict_tool(trigger_refund, name="trigger_refund", description="Return a simulated refund result."),
    ],
)

def main() -> None:
    # MCPServer.run owns the anyio event loop; do not wrap it in asyncio.run().
    server.run(transport="stdio")

if __name__ == "__main__":
    main()

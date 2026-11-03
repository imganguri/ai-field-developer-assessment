"""Call both stdio tools through the official MCP SDK client."""
import asyncio, sys
from pathlib import Path
from mcp import Client, StdioServerParameters

async def main():
    params=StdioServerParameters(command=sys.executable,args=["-m","task1_mcp_server.server"],cwd=str(Path(__file__).parents[1]))
    async with Client(params) as client:
        print([tool.name for tool in (await client.list_tools()).tools])
        print((await client.call_tool("get_customer_record",{"customer_id":"CUST-12345"})).content)
        print((await client.call_tool("trigger_refund",{"customer_id":"CUST-12345","amount":150.5,"reason":"Duplicate payment received"})).content)

if __name__=="__main__": asyncio.run(main())

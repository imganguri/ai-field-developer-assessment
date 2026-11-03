import pytest
import asyncio
import json
import sys
from pathlib import Path
from mcp import Client, StdioServerParameters
from mcp.shared.exceptions import MCPError
from pydantic import ValidationError
from task1_mcp_server.schemas import CustomerLookup, RefundRequest
from task1_mcp_server.customer_service import get_customer, refund

def test_customer_schema_and_fixtures():
    assert get_customer(CustomerLookup(customer_id="CUST-12345").customer_id)["name"]=="Ada Example"
    assert get_customer("CUST-00000") is None
    for data in [{}, {"customer_id":"bad"}, {"customer_id":"CUST-12345","extra":1}, {"customer_id":12345}]:
        with pytest.raises(ValidationError): CustomerLookup.model_validate(data)

@pytest.mark.parametrize("amount",[0,-1,float("inf"),float("nan"),True,"12.5"])
def test_refund_rejects_invalid_amount(amount):
    with pytest.raises(ValidationError): RefundRequest.model_validate({"customer_id":"CUST-12345","amount":amount,"reason":"Duplicate payment"})

def test_refund_strict_reason_and_result():
    for reason in ["short", "          "]:
        with pytest.raises(ValidationError): RefundRequest.model_validate({"customer_id":"CUST-12345","amount":1.25,"reason":reason})
    request=RefundRequest(customer_id="CUST-12345",amount=1.25,reason="Duplicate payment")
    assert refund(request.customer_id,request.amount,request.reason)["status"]=="simulated"

@pytest.mark.asyncio
async def test_real_stdio_mcp_client_wire_calls():
    params=StdioServerParameters(command=sys.executable,args=["-m","task1_mcp_server.server"],cwd=str(__import__("pathlib").Path(__file__).parents[1]))
    async with Client(params) as client:
        tools=(await client.list_tools()).tools
        assert {tool.name for tool in tools}=={"get_customer_record","trigger_refund"}
        customer=await client.call_tool("get_customer_record",{"customer_id":"CUST-12345"})
        missing_customer=await client.call_tool("get_customer_record",{"customer_id":"CUST-00000"})
        refund_result=await client.call_tool("trigger_refund",{"customer_id":"CUST-12345","amount":150.5,"reason":"Duplicate payment received"})
        missing_refund=await client.call_tool("trigger_refund",{"customer_id":"CUST-00000","amount":150.5,"reason":"Duplicate payment received"})
        assert not customer.is_error and '"found": true' in customer.content[0].text
        assert not missing_customer.is_error and '"found": false' in missing_customer.content[0].text
        assert not refund_result.is_error and '"status": "simulated"' in refund_result.content[0].text
        assert not missing_refund.is_error and '"status": "rejected"' in missing_refund.content[0].text
        invalid_calls=[("get_customer_record",{}), ("get_customer_record",{"customer_id":"bad"}), ("get_customer_record",{"customer_id":"CUST-12345","unexpected":True}), ("trigger_refund",{"customer_id":"CUST-12345"}), ("trigger_refund",{"customer_id":"CUST-12345","amount":True,"reason":"Long enough reason"}), ("trigger_refund",{"customer_id":"CUST-12345","amount":"3.5","reason":"Long enough reason"})]
        invalid_calls += [("trigger_refund",{"customer_id":"CUST-12345","amount":amount,"reason":"Long enough reason"}) for amount in (0,-1)]
        invalid_calls += [("trigger_refund",{"customer_id":"CUST-12345","amount":1.0,"reason":reason}) for reason in ("short","          ")]
        for name,args in invalid_calls:
            with pytest.raises(MCPError) as err:
                await client.call_tool(name,args)
            assert err.value.code == -32602

@pytest.mark.asyncio
async def test_stdio_wire_stdout_is_protocol_only_and_unknown_method_is_jsonrpc_error():
    root=Path(__file__).parents[1]
    proc=await asyncio.create_subprocess_exec(sys.executable,"-m","task1_mcp_server.server",cwd=str(root),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    replies=[]
    for message in (b"not-json\n",b"{}\n",b'{"jsonrpc":"2.0","id":44,"method":"unknown/method","params":{}}\n'):
        proc.stdin.write(message); await proc.stdin.drain()
        replies.append(json.loads(await asyncio.wait_for(proc.stdout.readline(),timeout=5)))
    proc.stdin.close(); proc.terminate(); await asyncio.wait_for(proc.wait(),timeout=5)
    trailing=await proc.stdout.read(); diagnostics=await proc.stderr.read()
    assert replies[0]["id"] is None and replies[0]["error"]["code"]==-32700
    assert replies[1]["id"] is None and replies[1]["error"]["code"]==-32600
    assert replies[2]["id"]==44 and replies[2]["error"]["code"]==-32601
    assert trailing==b""  # no startup/debug output on stdout
    assert isinstance(diagnostics,bytes)  # stderr was captured independently from protocol stdout

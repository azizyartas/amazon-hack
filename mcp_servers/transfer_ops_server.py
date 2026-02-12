"""
Transfer Operations MCP Server

Provides tools for executing transfers, managing approvals, and logging agent decisions.
Handles atomic DynamoDB transactions for stock transfers.

Tables used: Transfers (PK: transfer_id, GSI: StatusTimeIndex), AgentDecisions (PK: decision_id, GSI: AgentTimeIndex), Inventory
"""

import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import env_loader
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import boto3
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Dict, List
from mcp.server import Server
from mcp.types import Tool, TextContent

app = Server("transfer-ops")

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")
dynamodb = boto3.resource("dynamodb", region_name=REGION, verify=False)
dynamodb_client = boto3.client("dynamodb", region_name=REGION, verify=False)


def _to_json(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj == int(obj) else float(obj)
    if isinstance(obj, dict):
        return {k: _to_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_json(i) for i in obj]
    return obj

def _result(data):
    return [TextContent(type="text", text=json.dumps(_to_json(data), indent=2, ensure_ascii=False))]


@app.list_tools()
async def list_tools() -> List[Tool]:
    return [
        Tool(name="execute_transfer", description="Execute an atomic stock transfer between warehouses",
             inputSchema={"type": "object", "properties": {
                 "source_warehouse_id": {"type": "string"}, "target_warehouse_id": {"type": "string"},
                 "sku": {"type": "string"}, "quantity": {"type": "integer", "minimum": 1},
                 "reason": {"type": "string"}
             }, "required": ["source_warehouse_id", "target_warehouse_id", "sku", "quantity"]}),
        Tool(name="get_transfer_history", description="Get transfer history, optionally filtered by warehouse or SKU",
             inputSchema={"type": "object", "properties": {
                 "warehouse_id": {"type": "string"}, "sku": {"type": "string"},
                 "status": {"type": "string"}, "limit": {"type": "integer", "default": 50}
             }}),
        Tool(name="get_transfer_status", description="Get status of a specific transfer",
             inputSchema={"type": "object", "properties": {"transfer_id": {"type": "string"}}, "required": ["transfer_id"]}),
        Tool(name="log_decision", description="Log an agent decision for audit trail",
             inputSchema={"type": "object", "properties": {
                 "agent_name": {"type": "string"}, "decision_type": {"type": "string"},
                 "input_data": {"type": "object"}, "output_data": {"type": "object"},
                 "reasoning": {"type": "string"}
             }, "required": ["agent_name", "decision_type"]}),
        Tool(name="get_agent_decisions", description="Get decision history for an agent",
             inputSchema={"type": "object", "properties": {
                 "agent_name": {"type": "string"}, "limit": {"type": "integer", "default": 50}
             }, "required": ["agent_name"]}),
        Tool(name="rollback_transfer", description="Rollback a completed transfer (emergency use)",
             inputSchema={"type": "object", "properties": {
                 "transfer_id": {"type": "string"}, "reason": {"type": "string"}
             }, "required": ["transfer_id", "reason"]}),
        Tool(name="list_transfers_by_status", description="List transfers by status using StatusTimeIndex GSI",
             inputSchema={"type": "object", "properties": {
                 "status": {"type": "string"}, "limit": {"type": "integer", "default": 50}
             }, "required": ["status"]}),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> List[TextContent]:
    handlers = {
        "execute_transfer": lambda a: execute_transfer(a["source_warehouse_id"], a["target_warehouse_id"], a["sku"], a["quantity"], a.get("reason", "")),
        "get_transfer_history": lambda a: get_transfer_history(a.get("warehouse_id"), a.get("sku"), a.get("status"), a.get("limit", 50)),
        "get_transfer_status": lambda a: get_transfer_status(a["transfer_id"]),
        "log_decision": lambda a: log_decision(a["agent_name"], a["decision_type"], a.get("input_data", {}), a.get("output_data", {}), a.get("reasoning", "")),
        "get_agent_decisions": lambda a: get_agent_decisions(a["agent_name"], a.get("limit", 50)),
        "rollback_transfer": lambda a: rollback_transfer(a["transfer_id"], a["reason"]),
        "list_transfers_by_status": lambda a: list_transfers_by_status(a["status"], a.get("limit", 50)),
    }
    handler = handlers.get(name)
    if not handler:
        raise ValueError(f"Unknown tool: {name}")
    return _result(handler(arguments))


# --- Implementation ---

def execute_transfer(source_wh: str, target_wh: str, sku: str, quantity: int, reason: str = "") -> Dict:
    """Atomic stock transfer using DynamoDB transact_write_items."""
    transfer_id = f"TRF-{uuid.uuid4().hex[:8].upper()}"
    ts = datetime.utcnow().isoformat() + "Z"

    try:
        dynamodb_client.transact_write_items(TransactItems=[
            {"Update": {
                "TableName": "Inventory",
                "Key": {"warehouse_id": {"S": source_wh}, "sku": {"S": sku}},
                "UpdateExpression": "SET quantity = quantity - :qty, last_updated = :ts",
                "ConditionExpression": "quantity >= :qty",
                "ExpressionAttributeValues": {":qty": {"N": str(quantity)}, ":ts": {"S": ts}}
            }},
            {"Update": {
                "TableName": "Inventory",
                "Key": {"warehouse_id": {"S": target_wh}, "sku": {"S": sku}},
                "UpdateExpression": "SET quantity = quantity + :qty, last_updated = :ts",
                "ExpressionAttributeValues": {":qty": {"N": str(quantity)}, ":ts": {"S": ts}}
            }},
            {"Put": {
                "TableName": "Transfers",
                "Item": {
                    "transfer_id": {"S": transfer_id},
                    "source_warehouse": {"S": source_wh},
                    "target_warehouse": {"S": target_wh},
                    "sku": {"S": sku},
                    "quantity": {"N": str(quantity)},
                    "status": {"S": "completed"},
                    "reason": {"S": reason},
                    "created_at": {"S": ts},
                    "completed_at": {"S": ts},
                    "initiated_by": {"S": "mcp_transfer_ops"}
                }
            }}
        ])
        return {"success": True, "transfer_id": transfer_id, "status": "completed", "timestamp": ts,
                "details": {"source": source_wh, "target": target_wh, "sku": sku, "quantity": quantity, "reason": reason}}
    except dynamodb_client.exceptions.TransactionCanceledException as e:
        return {"success": False, "error": "Transaction failed - insufficient stock or condition not met", "details": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_transfer_history(warehouse_id: str = None, sku: str = None, status: str = None, limit: int = 50) -> Dict:
    """Transfer gecmisi. GSI yok (WarehouseIndex/SKUIndex), scan+filter kullaniyoruz.
    Sadece StatusTimeIndex GSI mevcut."""
    try:
        table = dynamodb.Table("Transfers")

        if status:
            # StatusTimeIndex GSI kullan
            from boto3.dynamodb.conditions import Key, Attr
            kwargs = {
                "IndexName": "StatusTimeIndex",
                "KeyConditionExpression": Key("status").eq(status),
                "Limit": limit,
                "ScanIndexForward": False
            }
            fe_parts = []
            eav = {}
            if warehouse_id:
                fe_parts.append("(source_warehouse = :wh OR target_warehouse = :wh)")
                eav[":wh"] = warehouse_id
            if sku:
                fe_parts.append("sku = :sku")
                eav[":sku"] = sku
            if fe_parts:
                kwargs["FilterExpression"] = " AND ".join(fe_parts)
                kwargs["ExpressionAttributeValues"] = {**kwargs.get("ExpressionAttributeValues", {}), **eav}
            resp = table.query(**kwargs)
        else:
            # Scan with filters
            from boto3.dynamodb.conditions import Attr
            filters = []
            if warehouse_id:
                filters.append(Attr("source_warehouse").eq(warehouse_id) | Attr("target_warehouse").eq(warehouse_id))
            if sku:
                filters.append(Attr("sku").eq(sku))

            kwargs = {"Limit": limit}
            if filters:
                combined = filters[0]
                for f in filters[1:]:
                    combined = combined & f
                kwargs["FilterExpression"] = combined

            resp = table.scan(**kwargs)

        return {"success": True, "count": len(resp.get("Items", [])), "data": resp.get("Items", [])}
    except Exception as e:
        return {"success": False, "error": str(e), "data": []}


def get_transfer_status(transfer_id: str) -> Dict:
    try:
        table = dynamodb.Table("Transfers")
        resp = table.get_item(Key={"transfer_id": transfer_id})
        if "Item" in resp:
            return {"success": True, "data": resp["Item"]}
        return {"success": False, "error": "Transfer not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def log_decision(agent_name: str, decision_type: str, input_data: Dict = None,
                 output_data: Dict = None, reasoning: str = "") -> Dict:
    decision_id = f"DEC-{uuid.uuid4().hex[:8].upper()}"
    ts = datetime.utcnow().isoformat() + "Z"
    try:
        table = dynamodb.Table("AgentDecisions")
        table.put_item(Item={
            "decision_id": decision_id, "agent_name": agent_name,
            "decision_type": decision_type, "input_data": input_data or {},
            "output_data": output_data or {}, "reasoning": reasoning, "timestamp": ts
        })
        return {"success": True, "decision_id": decision_id, "timestamp": ts}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_agent_decisions(agent_name: str, limit: int = 50) -> Dict:
    """AgentTimeIndex GSI kullanarak agent kararlarini getirir."""
    try:
        from boto3.dynamodb.conditions import Key
        table = dynamodb.Table("AgentDecisions")
        resp = table.query(
            IndexName="AgentTimeIndex",
            KeyConditionExpression=Key("agent_name").eq(agent_name),
            Limit=limit, ScanIndexForward=False
        )
        return {"success": True, "count": len(resp.get("Items", [])), "data": resp.get("Items", [])}
    except Exception as e:
        return {"success": False, "error": str(e), "data": []}


def list_transfers_by_status(status: str, limit: int = 50) -> Dict:
    """StatusTimeIndex GSI ile status bazli transfer listesi."""
    try:
        from boto3.dynamodb.conditions import Key
        table = dynamodb.Table("Transfers")
        resp = table.query(
            IndexName="StatusTimeIndex",
            KeyConditionExpression=Key("status").eq(status),
            Limit=limit, ScanIndexForward=False
        )
        return {"success": True, "count": len(resp.get("Items", [])), "data": resp.get("Items", [])}
    except Exception as e:
        return {"success": False, "error": str(e), "data": []}


def rollback_transfer(transfer_id: str, reason: str) -> Dict:
    try:
        table = dynamodb.Table("Transfers")
        resp = table.get_item(Key={"transfer_id": transfer_id})
        if "Item" not in resp:
            return {"success": False, "error": "Transfer not found"}

        transfer = resp["Item"]
        if transfer.get("status") != "completed":
            return {"success": False, "error": f"Cannot rollback status: {transfer.get('status')}"}

        # Reverse transfer
        rb = execute_transfer(
            source_wh=str(transfer["target_warehouse"]),
            target_wh=str(transfer["source_warehouse"]),
            sku=str(transfer["sku"]),
            quantity=int(transfer["quantity"]),
            reason=f"ROLLBACK: {reason}"
        )

        # Mark original as rolled back
        ts = datetime.utcnow().isoformat() + "Z"
        table.update_item(
            Key={"transfer_id": transfer_id},
            UpdateExpression="SET #s = :s, rollback_reason = :r, rollback_at = :t",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": "rolled_back", ":r": reason, ":t": ts}
        )
        return {"success": True, "transfer_id": transfer_id, "status": "rolled_back", "rollback_transfer": rb}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    import asyncio
    from mcp.server.stdio import stdio_server

    async def run():
        async with stdio_server() as (read, write):
            await app.run(read, write, app.create_initialization_options())

    asyncio.run(run())

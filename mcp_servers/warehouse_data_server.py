"""
Warehouse Data MCP Server

Provides tools for accessing warehouse, inventory, and product data from DynamoDB.
"""

import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import env_loader
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import boto3
from decimal import Decimal
from typing import Dict, List, Optional
from mcp.server import Server
from mcp.types import Tool, TextContent

app = Server("warehouse-data")

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")
dynamodb = boto3.resource("dynamodb", region_name=REGION, verify=False)


def _to_json(obj):
    """Decimal ve diger tipleri JSON serializable yapar."""
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
        Tool(name="get_inventory", description="Get inventory for a warehouse and SKU",
             inputSchema={"type": "object", "properties": {"warehouse_id": {"type": "string"}, "sku": {"type": "string"}}, "required": ["warehouse_id", "sku"]}),
        Tool(name="get_warehouse_info", description="Get warehouse information",
             inputSchema={"type": "object", "properties": {"warehouse_id": {"type": "string"}}, "required": ["warehouse_id"]}),
        Tool(name="list_warehouses", description="List all warehouses",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="list_low_stock_items", description="List items below min threshold in a warehouse",
             inputSchema={"type": "object", "properties": {"warehouse_id": {"type": "string"}}, "required": ["warehouse_id"]}),
        Tool(name="get_product_info", description="Get product information by SKU",
             inputSchema={"type": "object", "properties": {"sku": {"type": "string"}}, "required": ["sku"]}),
        Tool(name="list_products_by_category", description="List products by category",
             inputSchema={"type": "object", "properties": {"category": {"type": "string"}}, "required": ["category"]}),
        Tool(name="get_warehouse_inventory", description="Get all inventory for a warehouse",
             inputSchema={"type": "object", "properties": {"warehouse_id": {"type": "string"}}, "required": ["warehouse_id"]}),
        Tool(name="list_warehouses_by_region", description="List warehouses in a region",
             inputSchema={"type": "object", "properties": {"region": {"type": "string"}}, "required": ["region"]}),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> List[TextContent]:
    handlers = {
        "get_inventory": lambda a: get_inventory(a["warehouse_id"], a["sku"]),
        "get_warehouse_info": lambda a: get_warehouse_info(a["warehouse_id"]),
        "list_warehouses": lambda a: list_warehouses(),
        "list_low_stock_items": lambda a: list_low_stock_items(a["warehouse_id"]),
        "get_product_info": lambda a: get_product_info(a["sku"]),
        "list_products_by_category": lambda a: list_products_by_category(a["category"]),
        "get_warehouse_inventory": lambda a: get_warehouse_inventory(a["warehouse_id"]),
        "list_warehouses_by_region": lambda a: list_warehouses_by_region(a["region"]),
    }
    handler = handlers.get(name)
    if not handler:
        raise ValueError(f"Unknown tool: {name}")
    return _result(handler(arguments))


# --- Implementation ---

def get_inventory(warehouse_id: str, sku: str) -> Dict:
    try:
        table = dynamodb.Table("Inventory")
        resp = table.get_item(Key={"warehouse_id": warehouse_id, "sku": sku})
        if "Item" not in resp:
            return {"success": False, "error": "Inventory item not found"}
        return {"success": True, "data": resp["Item"]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_warehouse_info(warehouse_id: str) -> Dict:
    try:
        table = dynamodb.Table("Warehouses")
        resp = table.get_item(Key={"warehouse_id": warehouse_id})
        if "Item" not in resp:
            return {"success": False, "error": "Warehouse not found"}
        return {"success": True, "data": resp["Item"]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_warehouses() -> Dict:
    try:
        table = dynamodb.Table("Warehouses")
        resp = table.scan()
        return {"success": True, "count": len(resp["Items"]), "data": resp["Items"]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_low_stock_items(warehouse_id: str) -> Dict:
    try:
        from boto3.dynamodb.conditions import Key
        table = dynamodb.Table("Inventory")
        resp = table.query(KeyConditionExpression=Key("warehouse_id").eq(warehouse_id))
        low_stock = []
        for item in resp.get("Items", []):
            qty = item.get("quantity", 0)
            threshold = item.get("min_threshold", 0)
            if threshold and qty < threshold:
                low_stock.append(item)
        low_stock.sort(key=lambda x: x.get("quantity", 0))
        return {"success": True, "count": len(low_stock), "data": low_stock}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_product_info(sku: str) -> Dict:
    try:
        table = dynamodb.Table("Products")
        resp = table.get_item(Key={"sku": sku})
        if "Item" not in resp:
            return {"success": False, "error": "Product not found"}
        return {"success": True, "data": resp["Item"]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_products_by_category(category: str) -> Dict:
    try:
        from boto3.dynamodb.conditions import Key
        table = dynamodb.Table("Products")
        resp = table.query(
            IndexName="CategoryIndex",
            KeyConditionExpression=Key("category").eq(category)
        )
        return {"success": True, "count": len(resp["Items"]), "data": resp["Items"]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_warehouse_inventory(warehouse_id: str) -> Dict:
    try:
        from boto3.dynamodb.conditions import Key
        table = dynamodb.Table("Inventory")
        resp = table.query(KeyConditionExpression=Key("warehouse_id").eq(warehouse_id))
        return {"success": True, "count": len(resp["Items"]), "data": resp["Items"]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_warehouses_by_region(region: str) -> Dict:
    """Warehouses tablosunda GSI yok, scan + filter kullaniyoruz."""
    try:
        from boto3.dynamodb.conditions import Attr
        table = dynamodb.Table("Warehouses")
        resp = table.scan(FilterExpression=Attr("region").eq(region))
        return {"success": True, "count": len(resp["Items"]), "data": resp["Items"]}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    import asyncio
    from mcp.server.stdio import stdio_server

    async def run():
        async with stdio_server() as (read, write):
            await app.run(read, write, app.create_initialization_options())

    asyncio.run(run())

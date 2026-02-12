"""
Analytics MCP Server

Provides tools for sales history analysis, aging calculations, and predictive analytics.
Reads sales data from DynamoDB SalesHistory table and S3 for bulk data.
"""

import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import env_loader
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import boto3
from io import StringIO
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
from mcp.server import Server
from mcp.types import Tool, TextContent

app = Server("analytics")

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")
dynamodb = boto3.resource("dynamodb", region_name=REGION, verify=False)
s3 = boto3.client("s3", region_name=REGION, verify=False)

# S3 bucket name: warehouse-stock-mgmt-{account_id}
S3_BUCKET = None

def _get_bucket():
    global S3_BUCKET
    if S3_BUCKET is None:
        sts = boto3.client("sts", region_name=REGION, verify=False)
        account_id = sts.get_caller_identity()["Account"]
        S3_BUCKET = f"warehouse-stock-mgmt-{account_id}"
    return S3_BUCKET


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
        Tool(name="get_sales_history", description="Get historical sales data for a SKU and warehouse from DynamoDB",
             inputSchema={"type": "object", "properties": {
                 "sku": {"type": "string"}, "warehouse_id": {"type": "string", "description": "Optional: filter by warehouse"},
                 "months": {"type": "integer", "default": 12, "description": "Number of months to retrieve"}
             }, "required": ["sku"]}),
        Tool(name="calculate_sales_potential", description="Calculate sales potential score for a warehouse and SKU",
             inputSchema={"type": "object", "properties": {
                 "sku": {"type": "string"}, "warehouse_id": {"type": "string"}
             }, "required": ["sku", "warehouse_id"]}),
        Tool(name="get_aging_data", description="Get product aging information for a warehouse and SKU",
             inputSchema={"type": "object", "properties": {
                 "warehouse_id": {"type": "string"}, "sku": {"type": "string"}
             }, "required": ["warehouse_id", "sku"]}),
        Tool(name="get_category_threshold", description="Get aging threshold for a product category",
             inputSchema={"type": "object", "properties": {"category": {"type": "string"}}, "required": ["category"]}),
        Tool(name="prioritize_aged_stock", description="Get list of aged stock items prioritized by aging severity",
             inputSchema={"type": "object", "properties": {
                 "warehouse_id": {"type": "string", "description": "Optional"}, "category": {"type": "string", "description": "Optional"}
             }}),
        Tool(name="predict_demand", description="Predict future demand for a SKU based on historical data",
             inputSchema={"type": "object", "properties": {
                 "sku": {"type": "string"}, "warehouse_id": {"type": "string"},
                 "forecast_days": {"type": "integer", "default": 30}
             }, "required": ["sku", "warehouse_id"]}),
        Tool(name="get_regional_sales_multiplier", description="Get sales multiplier for a region",
             inputSchema={"type": "object", "properties": {"region": {"type": "string"}}, "required": ["region"]}),
        Tool(name="calculate_transfer_priority", description="Calculate priority score for a transfer",
             inputSchema={"type": "object", "properties": {
                 "sku": {"type": "string"}, "source_warehouse_id": {"type": "string"},
                 "target_warehouse_id": {"type": "string"}, "quantity": {"type": "integer"}
             }, "required": ["sku", "source_warehouse_id", "target_warehouse_id", "quantity"]}),
        Tool(name="get_seasonal_multiplier", description="Get seasonal sales multiplier for a category and month",
             inputSchema={"type": "object", "properties": {
                 "category": {"type": "string"}, "month": {"type": "integer", "minimum": 1, "maximum": 12}
             }, "required": ["category", "month"]}),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> List[TextContent]:
    handlers = {
        "get_sales_history": lambda a: get_sales_history(a["sku"], a.get("warehouse_id"), a.get("months", 12)),
        "calculate_sales_potential": lambda a: calculate_sales_potential(a["sku"], a["warehouse_id"]),
        "get_aging_data": lambda a: get_aging_data(a["warehouse_id"], a["sku"]),
        "get_category_threshold": lambda a: get_category_threshold(a["category"]),
        "prioritize_aged_stock": lambda a: prioritize_aged_stock(a.get("warehouse_id"), a.get("category")),
        "predict_demand": lambda a: predict_demand(a["sku"], a["warehouse_id"], a.get("forecast_days", 30)),
        "get_regional_sales_multiplier": lambda a: get_regional_sales_multiplier(a["region"]),
        "calculate_transfer_priority": lambda a: calculate_transfer_priority(a["sku"], a["source_warehouse_id"], a["target_warehouse_id"], a["quantity"]),
        "get_seasonal_multiplier": lambda a: get_seasonal_multiplier(a["category"], a["month"]),
    }
    handler = handlers.get(name)
    if not handler:
        raise ValueError(f"Unknown tool: {name}")
    return _result(handler(arguments))


# --- Implementation ---

def get_sales_history(sku: str, warehouse_id: Optional[str] = None, months: int = 12) -> Dict:
    """SalesHistory tablosundan satis verisi ceker. PK=warehouse_id, SK=date_sku (format: 2024-06-15#SKU001)"""
    try:
        from boto3.dynamodb.conditions import Key, Attr
        table = dynamodb.Table("SalesHistory")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=months * 30)
        start_str = start_date.strftime("%Y-%m-%d")

        sales_data = []

        if warehouse_id:
            # Query tek depo
            resp = table.query(
                KeyConditionExpression=Key("warehouse_id").eq(warehouse_id) & Key("date_sku").gte(f"{start_str}#"),
                FilterExpression=Attr("sku").eq(sku)
            )
            sales_data.extend(resp.get("Items", []))
            while "LastEvaluatedKey" in resp:
                resp = table.query(
                    KeyConditionExpression=Key("warehouse_id").eq(warehouse_id) & Key("date_sku").gte(f"{start_str}#"),
                    FilterExpression=Attr("sku").eq(sku),
                    ExclusiveStartKey=resp["LastEvaluatedKey"]
                )
                sales_data.extend(resp.get("Items", []))
        else:
            # Tum depolar icin scan (warehouse listesinden query)
            wh_table = dynamodb.Table("Warehouses")
            wh_resp = wh_table.scan(ProjectionExpression="warehouse_id")
            for wh in wh_resp.get("Items", []):
                wid = wh["warehouse_id"]
                resp = table.query(
                    KeyConditionExpression=Key("warehouse_id").eq(wid) & Key("date_sku").gte(f"{start_str}#"),
                    FilterExpression=Attr("sku").eq(sku)
                )
                sales_data.extend(resp.get("Items", []))

        return {"success": True, "sku": sku, "warehouse_id": warehouse_id, "months": months,
                "data_points": len(sales_data), "data": sales_data}
    except Exception as e:
        return {"success": False, "error": str(e), "data": []}


def calculate_sales_potential(sku: str, warehouse_id: str) -> Dict:
    try:
        history = get_sales_history(sku, warehouse_id, months=3)
        if not history["success"] or not history["data"]:
            return {"success": False, "error": "No sales history", "score": 0}

        total_sales = sum(float(r.get("quantity_sold", 0)) for r in history["data"])
        avg_daily = total_sales / 90

        wh_table = dynamodb.Table("Warehouses")
        wh_resp = wh_table.get_item(Key={"warehouse_id": warehouse_id})
        region = wh_resp["Item"].get("region", "") if "Item" in wh_resp else ""
        mult = get_regional_sales_multiplier(region)["multiplier"]

        base = min(avg_daily * 10, 100)
        score = base * mult
        return {"success": True, "sku": sku, "warehouse_id": warehouse_id,
                "score": round(score, 2), "avg_daily_sales": round(avg_daily, 2),
                "regional_multiplier": mult, "region": region}
    except Exception as e:
        return {"success": False, "error": str(e), "score": 0}


def get_aging_data(warehouse_id: str, sku: str) -> Dict:
    try:
        inv_table = dynamodb.Table("Inventory")
        resp = inv_table.get_item(Key={"warehouse_id": warehouse_id, "sku": sku})
        if "Item" not in resp:
            return {"success": False, "error": "Inventory item not found", "data": None}

        item = resp["Item"]
        received = item.get("received_date")
        if received:
            rd = datetime.fromisoformat(received.replace("Z", "+00:00"))
            aging_days = (datetime.now(rd.tzinfo) - rd).days
        else:
            aging_days = 0

        prod_table = dynamodb.Table("Products")
        prod_resp = prod_table.get_item(Key={"sku": sku})
        category = prod_resp["Item"].get("category", "") if "Item" in prod_resp else ""
        threshold = get_category_threshold(category)["threshold_days"]
        pct = (aging_days / threshold * 100) if threshold > 0 else 0

        return {"success": True, "data": {
            "warehouse_id": warehouse_id, "sku": sku, "aging_days": aging_days,
            "aging_threshold": threshold, "aging_percentage": round(pct, 2),
            "is_critical": aging_days >= threshold, "category": category, "received_date": received
        }}
    except Exception as e:
        return {"success": False, "error": str(e), "data": None}


def get_category_threshold(category: str) -> Dict:
    thresholds = {
        "Elektronik": 90, "Giyim": 180, "Gıda": 30, "Mobilya": 365,
        "Kitap": 730, "Oyuncak": 180, "Spor Malzemeleri": 365,
        "Ev Aletleri": 180, "Kozmetik": 365, "Otomotiv": 730
    }
    return {"success": True, "category": category, "threshold_days": thresholds.get(category, 180)}


def prioritize_aged_stock(warehouse_id: Optional[str] = None, category: Optional[str] = None) -> Dict:
    try:
        from boto3.dynamodb.conditions import Key
        inv_table = dynamodb.Table("Inventory")
        if warehouse_id:
            resp = inv_table.query(KeyConditionExpression=Key("warehouse_id").eq(warehouse_id))
            items = resp.get("Items", [])
        else:
            resp = inv_table.scan()
            items = resp.get("Items", [])
            while "LastEvaluatedKey" in resp:
                resp = inv_table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
                items.extend(resp.get("Items", []))

        aged = []
        for item in items:
            ad = get_aging_data(item["warehouse_id"], item["sku"])
            if not ad["success"]:
                continue
            info = ad["data"]
            if category and info.get("category") != category:
                continue
            if info["aging_percentage"] > 50:
                aged.append({
                    "warehouse_id": item["warehouse_id"], "sku": item["sku"],
                    "quantity": item.get("quantity", 0), "aging_days": info["aging_days"],
                    "aging_percentage": info["aging_percentage"], "is_critical": info["is_critical"],
                    "category": info["category"]
                })
        aged.sort(key=lambda x: x["aging_percentage"], reverse=True)
        return {"success": True, "count": len(aged), "data": aged}
    except Exception as e:
        return {"success": False, "error": str(e), "data": []}


def predict_demand(sku: str, warehouse_id: str, forecast_days: int = 30) -> Dict:
    try:
        history = get_sales_history(sku, warehouse_id, months=6)
        if not history["success"] or not history["data"]:
            return {"success": False, "error": "Insufficient sales history", "predicted_demand": 0}

        total = sum(float(r.get("quantity_sold", 0)) for r in history["data"])
        days = len(history["data"])
        avg_daily = total / days if days > 0 else 0
        predicted = avg_daily * forecast_days

        month = datetime.now().month
        prod_table = dynamodb.Table("Products")
        prod_resp = prod_table.get_item(Key={"sku": sku})
        if "Item" in prod_resp:
            cat = prod_resp["Item"].get("category", "")
            sm = get_seasonal_multiplier(cat, month)
            predicted *= sm.get("multiplier", 1.0)

        return {"success": True, "sku": sku, "warehouse_id": warehouse_id,
                "forecast_days": forecast_days, "predicted_demand": round(predicted, 2),
                "avg_daily_sales": round(avg_daily, 2), "confidence": "medium"}
    except Exception as e:
        return {"success": False, "error": str(e), "predicted_demand": 0}


def get_regional_sales_multiplier(region: str) -> Dict:
    mults = {"Marmara": 1.5, "İç Anadolu": 1.2, "Ege": 1.3, "Akdeniz": 1.1, "Karadeniz": 1.0}
    return {"success": True, "region": region, "multiplier": mults.get(region, 1.0)}


def calculate_transfer_priority(sku: str, source_wh: str, target_wh: str, quantity: int) -> Dict:
    try:
        sp = calculate_sales_potential(sku, target_wh)
        sales_score = sp.get("score", 0)

        ad = get_aging_data(source_wh, sku)
        aging_score = min(ad["data"]["aging_percentage"], 100) if ad["success"] else 0

        inv_table = dynamodb.Table("Inventory")
        tgt = inv_table.get_item(Key={"warehouse_id": target_wh, "sku": sku})
        if "Item" in tgt:
            cur = tgt["Item"].get("quantity", 0)
            mn = tgt["Item"].get("min_threshold", 0)
            deficit = max(0, mn - cur) if isinstance(mn, (int, float)) and isinstance(cur, (int, float)) else 0
            urgency = min((deficit / mn * 100) if mn > 0 else 0, 100)
        else:
            urgency = 100

        priority = sales_score * 0.4 + aging_score * 0.3 + urgency * 0.3
        rec = "high" if priority > 70 else "medium" if priority > 40 else "low"
        return {"success": True, "priority_score": round(priority, 2),
                "factors": {"sales_potential": round(sales_score, 2), "aging": round(aging_score, 2), "urgency": round(urgency, 2)},
                "recommendation": rec}
    except Exception as e:
        return {"success": False, "error": str(e), "priority_score": 0}


def get_seasonal_multiplier(category: str, month: int) -> Dict:
    patterns = {
        "Elektronik": {"high_season": [11, 12, 1], "multiplier": 2.5},
        "Giyim": {"high_season": [9, 10, 11], "multiplier": 2.0},
        "Gıda": {"high_season": [6, 7, 8], "multiplier": 1.5},
    }
    p = patterns.get(category, {"high_season": [], "multiplier": 1.0})
    m = p["multiplier"] if month in p["high_season"] else 1.0
    return {"success": True, "category": category, "month": month, "multiplier": m, "is_high_season": month in p["high_season"]}


if __name__ == "__main__":
    import asyncio
    from mcp.server.stdio import stdio_server

    async def run():
        async with stdio_server() as (read, write):
            await app.run(read, write, app.create_initialization_options())

    asyncio.run(run())

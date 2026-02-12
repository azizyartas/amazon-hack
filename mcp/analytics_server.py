"""
Analytics MCP Server

Provides tools for sales history analysis, aging calculations, and predictive analytics.
Accesses S3 for historical data and performs calculations for agent decision-making.
"""

import json
import boto3
import csv
from io import StringIO
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from mcp.server import Server
from mcp.types import Tool, TextContent

# Initialize MCP Server
app = Server("analytics")

# Initialize AWS clients
s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

# Configuration
S3_BUCKET = 'warehouse-stock-management'


@app.list_tools()
async def list_tools() -> List[Tool]:
    """List all available tools in this MCP server"""
    return [
        Tool(
            name="get_sales_history",
            description="Get historical sales data for a SKU and warehouse",
            inputSchema={
                "type": "object",
                "properties": {
                    "sku": {"type": "string"},
                    "warehouse_id": {"type": "string", "description": "Optional: Filter by warehouse"},
                    "months": {"type": "integer", "default": 12, "description": "Number of months to retrieve"}
                },
                "required": ["sku"]
            }
        ),
        Tool(
            name="calculate_sales_potential",
            description="Calculate sales potential score for a warehouse and SKU",
            inputSchema={
                "type": "object",
                "properties": {
                    "sku": {"type": "string"},
                    "warehouse_id": {"type": "string"}
                },
                "required": ["sku", "warehouse_id"]
            }
        ),
        Tool(
            name="get_aging_data",
            description="Get product aging information for a warehouse and SKU",
            inputSchema={
                "type": "object",
                "properties": {
                    "warehouse_id": {"type": "string"},
                    "sku": {"type": "string"}
                },
                "required": ["warehouse_id", "sku"]
            }
        ),
        Tool(
            name="get_category_threshold",
            description="Get aging threshold for a product category",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {"type": "string"}
                },
                "required": ["category"]
            }
        ),
        Tool(
            name="prioritize_aged_stock",
            description="Get list of aged stock items prioritized by aging severity",
            inputSchema={
                "type": "object",
                "properties": {
                    "warehouse_id": {"type": "string", "description": "Optional: Filter by warehouse"},
                    "category": {"type": "string", "description": "Optional: Filter by category"}
                }
            }
        ),
        Tool(
            name="predict_demand",
            description="Predict future demand for a SKU based on historical data",
            inputSchema={
                "type": "object",
                "properties": {
                    "sku": {"type": "string"},
                    "warehouse_id": {"type": "string"},
                    "forecast_days": {"type": "integer", "default": 30}
                },
                "required": ["sku", "warehouse_id"]
            }
        ),
        Tool(
            name="get_regional_sales_multiplier",
            description="Get sales multiplier for a region",
            inputSchema={
                "type": "object",
                "properties": {
                    "region": {"type": "string"}
                },
                "required": ["region"]
            }
        ),
        Tool(
            name="calculate_transfer_priority",
            description="Calculate priority score for a transfer based on multiple factors",
            inputSchema={
                "type": "object",
                "properties": {
                    "sku": {"type": "string"},
                    "source_warehouse_id": {"type": "string"},
                    "target_warehouse_id": {"type": "string"},
                    "quantity": {"type": "integer"}
                },
                "required": ["sku", "source_warehouse_id", "target_warehouse_id", "quantity"]
            }
        ),
        Tool(
            name="get_seasonal_multiplier",
            description="Get seasonal sales multiplier for a category and month",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "month": {"type": "integer", "minimum": 1, "maximum": 12}
                },
                "required": ["category", "month"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> List[TextContent]:
    """Handle tool calls"""
    
    if name == "get_sales_history":
        result = get_sales_history(
            arguments["sku"],
            arguments.get("warehouse_id"),
            arguments.get("months", 12)
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "calculate_sales_potential":
        result = calculate_sales_potential(
            arguments["sku"],
            arguments["warehouse_id"]
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_aging_data":
        result = get_aging_data(
            arguments["warehouse_id"],
            arguments["sku"]
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_category_threshold":
        result = get_category_threshold(arguments["category"])
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "prioritize_aged_stock":
        result = prioritize_aged_stock(
            arguments.get("warehouse_id"),
            arguments.get("category")
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "predict_demand":
        result = predict_demand(
            arguments["sku"],
            arguments["warehouse_id"],
            arguments.get("forecast_days", 30)
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_regional_sales_multiplier":
        result = get_regional_sales_multiplier(arguments["region"])
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "calculate_transfer_priority":
        result = calculate_transfer_priority(
            arguments["sku"],
            arguments["source_warehouse_id"],
            arguments["target_warehouse_id"],
            arguments["quantity"]
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_seasonal_multiplier":
        result = get_seasonal_multiplier(
            arguments["category"],
            arguments["month"]
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    else:
        raise ValueError(f"Unknown tool: {name}")


# Tool Implementation Functions

def get_sales_history(sku: str, warehouse_id: Optional[str] = None, months: int = 12) -> Dict:
    """Get historical sales data from S3"""
    try:
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=months * 30)
        
        sales_data = []
        
        # Iterate through months
        current_date = start_date
        while current_date <= end_date:
            year = current_date.year
            month = current_date.month
            
            # Construct S3 key
            s3_key = f"sales-history/{year}/{month:02d}/sales-{year}-{month:02d}.csv"
            
            try:
                # Get file from S3
                response = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
                csv_content = response['Body'].read().decode('utf-8')
                
                # Parse CSV
                csv_reader = csv.DictReader(StringIO(csv_content))
                for row in csv_reader:
                    if row['sku'] == sku:
                        if warehouse_id is None or row['warehouse_id'] == warehouse_id:
                            sales_data.append(row)
            except s3.exceptions.NoSuchKey:
                # File doesn't exist for this month, skip
                pass
            
            # Move to next month
            current_date = current_date + timedelta(days=32)
            current_date = current_date.replace(day=1)
        
        return {
            "success": True,
            "sku": sku,
            "warehouse_id": warehouse_id,
            "months": months,
            "data_points": len(sales_data),
            "data": sales_data
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": []
        }


def calculate_sales_potential(sku: str, warehouse_id: str) -> Dict:
    """Calculate sales potential score based on historical data and regional factors"""
    try:
        # Get sales history
        sales_history = get_sales_history(sku, warehouse_id, months=3)
        
        if not sales_history["success"] or len(sales_history["data"]) == 0:
            return {
                "success": False,
                "error": "No sales history available",
                "score": 0
            }
        
        # Calculate average daily sales
        total_sales = sum(float(row.get('quantity', 0)) for row in sales_history["data"])
        avg_daily_sales = total_sales / (3 * 30)  # 3 months
        
        # Get warehouse info for regional multiplier
        warehouse_table = dynamodb.Table('Warehouses')
        warehouse_response = warehouse_table.get_item(
            Key={'warehouse_id': warehouse_id}
        )
        
        if 'Item' not in warehouse_response:
            return {
                "success": False,
                "error": "Warehouse not found",
                "score": 0
            }
        
        region = warehouse_response['Item'].get('region', '')
        regional_multiplier = get_regional_sales_multiplier(region)["multiplier"]
        
        # Calculate potential score (0-100)
        base_score = min(avg_daily_sales * 10, 100)  # Scale to 0-100
        adjusted_score = base_score * regional_multiplier
        
        return {
            "success": True,
            "sku": sku,
            "warehouse_id": warehouse_id,
            "score": round(adjusted_score, 2),
            "avg_daily_sales": round(avg_daily_sales, 2),
            "regional_multiplier": regional_multiplier,
            "region": region
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "score": 0
        }


def get_aging_data(warehouse_id: str, sku: str) -> Dict:
    """Get product aging information"""
    try:
        # Get inventory data
        inventory_table = dynamodb.Table('Inventory')
        response = inventory_table.get_item(
            Key={
                'warehouse_id': warehouse_id,
                'sku': sku
            }
        )
        
        if 'Item' not in response:
            return {
                "success": False,
                "error": "Inventory item not found",
                "data": None
            }
        
        item = response['Item']
        
        # Calculate aging
        last_received = item.get('last_received_date')
        if last_received:
            last_received_date = datetime.fromisoformat(last_received.replace('Z', '+00:00'))
            aging_days = (datetime.now(last_received_date.tzinfo) - last_received_date).days
        else:
            aging_days = 0
        
        # Get product category threshold
        product_table = dynamodb.Table('Products')
        product_response = product_table.get_item(
            Key={'sku': sku}
        )
        
        category = product_response['Item'].get('category', '') if 'Item' in product_response else ''
        threshold_data = get_category_threshold(category)
        aging_threshold = threshold_data.get("threshold_days", 180)
        
        # Calculate aging percentage
        aging_percentage = (aging_days / aging_threshold * 100) if aging_threshold > 0 else 0
        
        return {
            "success": True,
            "data": {
                "warehouse_id": warehouse_id,
                "sku": sku,
                "aging_days": aging_days,
                "aging_threshold": aging_threshold,
                "aging_percentage": round(aging_percentage, 2),
                "is_critical": aging_days >= aging_threshold,
                "category": category,
                "last_received_date": last_received
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": None
        }


def get_category_threshold(category: str) -> Dict:
    """Get aging threshold for a product category"""
    
    # Category thresholds (from design document)
    category_thresholds = {
        "Elektronik": 90,
        "Giyim": 180,
        "Gıda": 30,
        "Mobilya": 365,
        "Kitap": 730,
        "Oyuncak": 180,
        "Spor Malzemeleri": 365,
        "Ev Aletleri": 180,
        "Kozmetik": 365,
        "Otomotiv": 730
    }
    
    threshold = category_thresholds.get(category, 180)  # Default 180 days
    
    return {
        "success": True,
        "category": category,
        "threshold_days": threshold
    }


def prioritize_aged_stock(warehouse_id: Optional[str] = None, category: Optional[str] = None) -> Dict:
    """Get list of aged stock items prioritized by aging severity"""
    try:
        inventory_table = dynamodb.Table('Inventory')
        
        # Get inventory items
        if warehouse_id:
            response = inventory_table.query(
                KeyConditionExpression='warehouse_id = :wh_id',
                ExpressionAttributeValues={
                    ':wh_id': warehouse_id
                }
            )
        else:
            response = inventory_table.scan()
        
        items = response.get('Items', [])
        
        # Calculate aging for each item
        aged_items = []
        for item in items:
            aging_data = get_aging_data(item['warehouse_id'], item['sku'])
            
            if aging_data["success"]:
                aging_info = aging_data["data"]
                
                # Filter by category if specified
                if category and aging_info.get("category") != category:
                    continue
                
                # Only include items that are aging
                if aging_info["aging_percentage"] > 50:  # More than 50% of threshold
                    aged_items.append({
                        "warehouse_id": item['warehouse_id'],
                        "sku": item['sku'],
                        "quantity": item.get('quantity', 0),
                        "aging_days": aging_info["aging_days"],
                        "aging_percentage": aging_info["aging_percentage"],
                        "is_critical": aging_info["is_critical"],
                        "category": aging_info["category"]
                    })
        
        # Sort by aging percentage (most critical first)
        aged_items.sort(key=lambda x: x["aging_percentage"], reverse=True)
        
        return {
            "success": True,
            "count": len(aged_items),
            "data": aged_items
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": []
        }


def predict_demand(sku: str, warehouse_id: str, forecast_days: int = 30) -> Dict:
    """Predict future demand based on historical data"""
    try:
        # Get sales history
        sales_history = get_sales_history(sku, warehouse_id, months=6)
        
        if not sales_history["success"] or len(sales_history["data"]) == 0:
            return {
                "success": False,
                "error": "Insufficient sales history for prediction",
                "predicted_demand": 0
            }
        
        # Simple moving average prediction
        total_sales = sum(float(row.get('quantity', 0)) for row in sales_history["data"])
        days_of_data = len(sales_history["data"])
        avg_daily_sales = total_sales / days_of_data if days_of_data > 0 else 0
        
        # Predict for forecast period
        predicted_demand = avg_daily_sales * forecast_days
        
        # Get seasonal adjustment
        current_month = datetime.now().month
        product_table = dynamodb.Table('Products')
        product_response = product_table.get_item(Key={'sku': sku})
        
        if 'Item' in product_response:
            category = product_response['Item'].get('category', '')
            seasonal_data = get_seasonal_multiplier(category, current_month)
            seasonal_multiplier = seasonal_data.get("multiplier", 1.0)
            predicted_demand *= seasonal_multiplier
        
        return {
            "success": True,
            "sku": sku,
            "warehouse_id": warehouse_id,
            "forecast_days": forecast_days,
            "predicted_demand": round(predicted_demand, 2),
            "avg_daily_sales": round(avg_daily_sales, 2),
            "confidence": "medium"  # Simple model = medium confidence
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "predicted_demand": 0
        }


def get_regional_sales_multiplier(region: str) -> Dict:
    """Get sales multiplier for a region"""
    
    # Regional multipliers (from design document)
    regional_multipliers = {
        "Marmara": 1.5,
        "İç Anadolu": 1.2,
        "Ege": 1.3,
        "Akdeniz": 1.1,
        "Karadeniz": 1.0
    }
    
    multiplier = regional_multipliers.get(region, 1.0)
    
    return {
        "success": True,
        "region": region,
        "multiplier": multiplier
    }


def calculate_transfer_priority(sku: str, source_warehouse_id: str,
                               target_warehouse_id: str, quantity: int) -> Dict:
    """Calculate priority score for a transfer based on multiple factors"""
    try:
        # Factor 1: Target warehouse sales potential
        sales_potential = calculate_sales_potential(sku, target_warehouse_id)
        sales_score = sales_potential.get("score", 0)
        
        # Factor 2: Source warehouse aging
        aging_data = get_aging_data(source_warehouse_id, sku)
        aging_percentage = aging_data["data"]["aging_percentage"] if aging_data["success"] else 0
        aging_score = min(aging_percentage, 100)
        
        # Factor 3: Target warehouse stock level
        inventory_table = dynamodb.Table('Inventory')
        target_inventory = inventory_table.get_item(
            Key={'warehouse_id': target_warehouse_id, 'sku': sku}
        )
        
        if 'Item' in target_inventory:
            current_stock = target_inventory['Item'].get('quantity', 0)
            min_threshold = target_inventory['Item'].get('min_threshold', 0)
            stock_deficit = max(0, min_threshold - current_stock)
            urgency_score = min((stock_deficit / min_threshold * 100) if min_threshold > 0 else 0, 100)
        else:
            urgency_score = 100  # No stock at all = highest urgency
        
        # Calculate weighted priority score
        priority_score = (
            sales_score * 0.4 +      # 40% weight on sales potential
            aging_score * 0.3 +       # 30% weight on aging
            urgency_score * 0.3       # 30% weight on urgency
        )
        
        return {
            "success": True,
            "priority_score": round(priority_score, 2),
            "factors": {
                "sales_potential_score": round(sales_score, 2),
                "aging_score": round(aging_score, 2),
                "urgency_score": round(urgency_score, 2)
            },
            "recommendation": "high" if priority_score > 70 else "medium" if priority_score > 40 else "low"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "priority_score": 0
        }


def get_seasonal_multiplier(category: str, month: int) -> Dict:
    """Get seasonal sales multiplier for a category and month"""
    
    # Seasonal multipliers (from design document)
    seasonal_patterns = {
        "Elektronik": {
            "high_season": [11, 12, 1],
            "multiplier": 2.5
        },
        "Giyim": {
            "high_season": [9, 10, 11],
            "multiplier": 2.0
        },
        "Gıda": {
            "high_season": [6, 7, 8],
            "multiplier": 1.5
        }
    }
    
    pattern = seasonal_patterns.get(category, {"high_season": [], "multiplier": 1.0})
    
    if month in pattern["high_season"]:
        multiplier = pattern["multiplier"]
    else:
        multiplier = 1.0
    
    return {
        "success": True,
        "category": category,
        "month": month,
        "multiplier": multiplier,
        "is_high_season": month in pattern["high_season"]
    }


if __name__ == "__main__":
    import asyncio
    asyncio.run(app.run())

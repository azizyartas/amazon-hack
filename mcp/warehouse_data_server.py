"""
Warehouse Data MCP Server

Provides tools for accessing warehouse, inventory, and product data from DynamoDB.
This server acts as the data access layer for all agents.
"""

import json
import boto3
from datetime import datetime
from typing import Dict, List, Optional
from mcp.server import Server
from mcp.types import Tool, TextContent

# Initialize MCP Server
app = Server("warehouse-data")

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
dynamodb_client = boto3.client('dynamodb')


@app.list_tools()
async def list_tools() -> List[Tool]:
    """List all available tools in this MCP server"""
    return [
        Tool(
            name="get_inventory",
            description="Get current inventory level for a specific warehouse and SKU",
            inputSchema={
                "type": "object",
                "properties": {
                    "warehouse_id": {"type": "string", "description": "Warehouse ID (e.g., WH001)"},
                    "sku": {"type": "string", "description": "Product SKU"}
                },
                "required": ["warehouse_id", "sku"]
            }
        ),
        Tool(
            name="get_warehouse_info",
            description="Get warehouse information including capacity and location",
            inputSchema={
                "type": "object",
                "properties": {
                    "warehouse_id": {"type": "string", "description": "Warehouse ID"}
                },
                "required": ["warehouse_id"]
            }
        ),
        Tool(
            name="list_low_stock_items",
            description="List all items below their minimum threshold across all warehouses",
            inputSchema={
                "type": "object",
                "properties": {
                    "warehouse_id": {"type": "string", "description": "Optional: Filter by warehouse ID"}
                }
            }
        ),
        Tool(
            name="get_product_info",
            description="Get product information including category and aging threshold",
            inputSchema={
                "type": "object",
                "properties": {
                    "sku": {"type": "string", "description": "Product SKU"}
                },
                "required": ["sku"]
            }
        ),
        Tool(
            name="get_threshold",
            description="Get minimum stock threshold for a warehouse and SKU",
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
            name="set_threshold",
            description="Set minimum stock threshold for a warehouse and SKU",
            inputSchema={
                "type": "object",
                "properties": {
                    "warehouse_id": {"type": "string"},
                    "sku": {"type": "string"},
                    "threshold": {"type": "integer", "minimum": 0}
                },
                "required": ["warehouse_id", "sku", "threshold"]
            }
        ),
        Tool(
            name="get_regional_data",
            description="Get all warehouses in a specific region",
            inputSchema={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Region name (e.g., Marmara)"}
                },
                "required": ["region"]
            }
        ),
        Tool(
            name="get_products_by_category",
            description="Get all products in a specific category",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Product category"}
                },
                "required": ["category"]
            }
        ),
        Tool(
            name="validate_transfer",
            description="Validate if a transfer is possible (sufficient stock, valid warehouses)",
            inputSchema={
                "type": "object",
                "properties": {
                    "source_warehouse_id": {"type": "string"},
                    "target_warehouse_id": {"type": "string"},
                    "sku": {"type": "string"},
                    "quantity": {"type": "integer", "minimum": 1}
                },
                "required": ["source_warehouse_id", "target_warehouse_id", "sku", "quantity"]
            }
        ),
        Tool(
            name="get_warehouse_capacity",
            description="Get current capacity usage for a warehouse",
            inputSchema={
                "type": "object",
                "properties": {
                    "warehouse_id": {"type": "string"}
                },
                "required": ["warehouse_id"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> List[TextContent]:
    """Handle tool calls"""
    
    if name == "get_inventory":
        result = get_inventory(arguments["warehouse_id"], arguments["sku"])
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_warehouse_info":
        result = get_warehouse_info(arguments["warehouse_id"])
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "list_low_stock_items":
        warehouse_id = arguments.get("warehouse_id")
        result = list_low_stock_items(warehouse_id)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_product_info":
        result = get_product_info(arguments["sku"])
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_threshold":
        result = get_threshold(arguments["warehouse_id"], arguments["sku"])
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "set_threshold":
        result = set_threshold(
            arguments["warehouse_id"],
            arguments["sku"],
            arguments["threshold"]
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_regional_data":
        result = get_regional_data(arguments["region"])
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_products_by_category":
        result = get_products_by_category(arguments["category"])
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "validate_transfer":
        result = validate_transfer(
            arguments["source_warehouse_id"],
            arguments["target_warehouse_id"],
            arguments["sku"],
            arguments["quantity"]
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_warehouse_capacity":
        result = get_warehouse_capacity(arguments["warehouse_id"])
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    else:
        raise ValueError(f"Unknown tool: {name}")


# Tool Implementation Functions

def get_inventory(warehouse_id: str, sku: str) -> Dict:
    """Get current inventory for a warehouse and SKU"""
    try:
        table = dynamodb.Table('Inventory')
        response = table.get_item(
            Key={
                'warehouse_id': warehouse_id,
                'sku': sku
            }
        )
        
        if 'Item' in response:
            return {
                "success": True,
                "data": response['Item']
            }
        else:
            return {
                "success": False,
                "error": "Item not found",
                "data": None
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": None
        }


def get_warehouse_info(warehouse_id: str) -> Dict:
    """Get warehouse information"""
    try:
        table = dynamodb.Table('Warehouses')
        response = table.get_item(
            Key={'warehouse_id': warehouse_id}
        )
        
        if 'Item' in response:
            return {
                "success": True,
                "data": response['Item']
            }
        else:
            return {
                "success": False,
                "error": "Warehouse not found",
                "data": None
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": None
        }


def list_low_stock_items(warehouse_id: Optional[str] = None) -> Dict:
    """List all items below their minimum threshold"""
    try:
        table = dynamodb.Table('Inventory')
        
        if warehouse_id:
            # Query specific warehouse
            response = table.query(
                KeyConditionExpression='warehouse_id = :wh_id',
                ExpressionAttributeValues={
                    ':wh_id': warehouse_id
                }
            )
        else:
            # Scan all warehouses
            response = table.scan()
        
        items = response.get('Items', [])
        
        # Filter items below threshold
        low_stock_items = []
        for item in items:
            if item.get('quantity', 0) < item.get('min_threshold', 0):
                low_stock_items.append(item)
        
        return {
            "success": True,
            "count": len(low_stock_items),
            "data": low_stock_items
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": []
        }


def get_product_info(sku: str) -> Dict:
    """Get product information"""
    try:
        table = dynamodb.Table('Products')
        response = table.get_item(
            Key={'sku': sku}
        )
        
        if 'Item' in response:
            return {
                "success": True,
                "data": response['Item']
            }
        else:
            return {
                "success": False,
                "error": "Product not found",
                "data": None
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": None
        }


def get_threshold(warehouse_id: str, sku: str) -> Dict:
    """Get minimum stock threshold"""
    try:
        table = dynamodb.Table('Inventory')
        response = table.get_item(
            Key={
                'warehouse_id': warehouse_id,
                'sku': sku
            }
        )
        
        if 'Item' in response:
            threshold = response['Item'].get('min_threshold', 0)
            return {
                "success": True,
                "data": {
                    "warehouse_id": warehouse_id,
                    "sku": sku,
                    "threshold": threshold
                }
            }
        else:
            return {
                "success": False,
                "error": "Item not found",
                "data": None
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": None
        }


def set_threshold(warehouse_id: str, sku: str, threshold: int) -> Dict:
    """Set minimum stock threshold"""
    try:
        table = dynamodb.Table('Inventory')
        response = table.update_item(
            Key={
                'warehouse_id': warehouse_id,
                'sku': sku
            },
            UpdateExpression='SET min_threshold = :threshold',
            ExpressionAttributeValues={
                ':threshold': threshold
            },
            ReturnValues='ALL_NEW'
        )
        
        return {
            "success": True,
            "data": response.get('Attributes', {})
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": None
        }


def get_regional_data(region: str) -> Dict:
    """Get all warehouses in a region"""
    try:
        table = dynamodb.Table('Warehouses')
        response = table.query(
            IndexName='RegionIndex',
            KeyConditionExpression='region = :region',
            ExpressionAttributeValues={
                ':region': region
            }
        )
        
        return {
            "success": True,
            "count": len(response.get('Items', [])),
            "data": response.get('Items', [])
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": []
        }


def get_products_by_category(category: str) -> Dict:
    """Get all products in a category"""
    try:
        table = dynamodb.Table('Products')
        response = table.query(
            IndexName='CategoryIndex',
            KeyConditionExpression='category = :category',
            ExpressionAttributeValues={
                ':category': category
            }
        )
        
        return {
            "success": True,
            "count": len(response.get('Items', [])),
            "data": response.get('Items', [])
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": []
        }


def validate_transfer(source_warehouse_id: str, target_warehouse_id: str, 
                     sku: str, quantity: int) -> Dict:
    """Validate if a transfer is possible"""
    try:
        # Check source warehouse has sufficient stock
        source_inventory = get_inventory(source_warehouse_id, sku)
        if not source_inventory["success"]:
            return {
                "valid": False,
                "reason": "Source inventory not found"
            }
        
        source_quantity = source_inventory["data"].get("quantity", 0)
        if source_quantity < quantity:
            return {
                "valid": False,
                "reason": f"Insufficient stock at source. Available: {source_quantity}, Requested: {quantity}"
            }
        
        # Check target warehouse exists
        target_warehouse = get_warehouse_info(target_warehouse_id)
        if not target_warehouse["success"]:
            return {
                "valid": False,
                "reason": "Target warehouse not found"
            }
        
        # Check warehouses are different
        if source_warehouse_id == target_warehouse_id:
            return {
                "valid": False,
                "reason": "Source and target warehouses must be different"
            }
        
        return {
            "valid": True,
            "reason": "Transfer is valid",
            "source_available": source_quantity,
            "transfer_quantity": quantity
        }
    except Exception as e:
        return {
            "valid": False,
            "reason": f"Validation error: {str(e)}"
        }


def get_warehouse_capacity(warehouse_id: str) -> Dict:
    """Get current capacity usage for a warehouse"""
    try:
        # Get warehouse info
        warehouse = get_warehouse_info(warehouse_id)
        if not warehouse["success"]:
            return {
                "success": False,
                "error": "Warehouse not found",
                "data": None
            }
        
        max_capacity = warehouse["data"].get("capacity", 0)
        
        # Get all inventory for this warehouse
        table = dynamodb.Table('Inventory')
        response = table.query(
            KeyConditionExpression='warehouse_id = :wh_id',
            ExpressionAttributeValues={
                ':wh_id': warehouse_id
            }
        )
        
        # Calculate current usage
        current_usage = sum(item.get('quantity', 0) for item in response.get('Items', []))
        
        return {
            "success": True,
            "data": {
                "warehouse_id": warehouse_id,
                "max_capacity": max_capacity,
                "current_usage": current_usage,
                "available_capacity": max_capacity - current_usage,
                "usage_percentage": (current_usage / max_capacity * 100) if max_capacity > 0 else 0
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": None
        }


if __name__ == "__main__":
    import asyncio
    asyncio.run(app.run())

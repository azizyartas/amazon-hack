"""
Transfer Operations MCP Server

Provides tools for executing transfers, managing approvals, and logging agent decisions.
Handles atomic DynamoDB transactions for stock transfers.
"""

import json
import boto3
import uuid
from datetime import datetime
from typing import Dict, List
from mcp.server import Server
from mcp.types import Tool, TextContent

# Initialize MCP Server
app = Server("transfer-ops")

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
dynamodb_client = boto3.client('dynamodb')


@app.list_tools()
async def list_tools() -> List[Tool]:
    """List all available tools in this MCP server"""
    return [
        Tool(
            name="execute_transfer",
            description="Execute an atomic stock transfer between warehouses",
            inputSchema={
                "type": "object",
                "properties": {
                    "source_warehouse_id": {"type": "string"},
                    "target_warehouse_id": {"type": "string"},
                    "sku": {"type": "string"},
                    "quantity": {"type": "integer", "minimum": 1},
                    "reason": {"type": "string"},
                    "requires_approval": {"type": "boolean", "default": False}
                },
                "required": ["source_warehouse_id", "target_warehouse_id", "sku", "quantity"]
            }
        ),
        Tool(
            name="get_transfer_history",
            description="Get transfer history for a warehouse or SKU",
            inputSchema={
                "type": "object",
                "properties": {
                    "warehouse_id": {"type": "string", "description": "Filter by warehouse (source or target)"},
                    "sku": {"type": "string", "description": "Filter by SKU"},
                    "limit": {"type": "integer", "default": 50}
                }
            }
        ),
        Tool(
            name="get_transfer_status",
            description="Get status of a specific transfer",
            inputSchema={
                "type": "object",
                "properties": {
                    "transfer_id": {"type": "string"}
                },
                "required": ["transfer_id"]
            }
        ),
        Tool(
            name="create_approval_request",
            description="Create a transfer approval request for human review",
            inputSchema={
                "type": "object",
                "properties": {
                    "transfer_data": {"type": "object"},
                    "estimated_value": {"type": "number"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high"]}
                },
                "required": ["transfer_data"]
            }
        ),
        Tool(
            name="approve_transfer",
            description="Approve a pending transfer request",
            inputSchema={
                "type": "object",
                "properties": {
                    "approval_id": {"type": "string"},
                    "approver": {"type": "string"}
                },
                "required": ["approval_id", "approver"]
            }
        ),
        Tool(
            name="reject_transfer",
            description="Reject a pending transfer request",
            inputSchema={
                "type": "object",
                "properties": {
                    "approval_id": {"type": "string"},
                    "approver": {"type": "string"},
                    "reason": {"type": "string"}
                },
                "required": ["approval_id", "approver", "reason"]
            }
        ),
        Tool(
            name="log_decision",
            description="Log an agent decision for audit trail",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_name": {"type": "string"},
                    "decision_type": {"type": "string"},
                    "input_data": {"type": "object"},
                    "output_data": {"type": "object"},
                    "reasoning": {"type": "string"}
                },
                "required": ["agent_name", "decision_type"]
            }
        ),
        Tool(
            name="get_agent_decisions",
            description="Get decision history for an agent",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_name": {"type": "string"},
                    "limit": {"type": "integer", "default": 50}
                },
                "required": ["agent_name"]
            }
        ),
        Tool(
            name="rollback_transfer",
            description="Rollback a completed transfer (emergency use)",
            inputSchema={
                "type": "object",
                "properties": {
                    "transfer_id": {"type": "string"},
                    "reason": {"type": "string"}
                },
                "required": ["transfer_id", "reason"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> List[TextContent]:
    """Handle tool calls"""
    
    if name == "execute_transfer":
        result = execute_transfer(
            arguments["source_warehouse_id"],
            arguments["target_warehouse_id"],
            arguments["sku"],
            arguments["quantity"],
            arguments.get("reason", ""),
            arguments.get("requires_approval", False)
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_transfer_history":
        result = get_transfer_history(
            arguments.get("warehouse_id"),
            arguments.get("sku"),
            arguments.get("limit", 50)
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_transfer_status":
        result = get_transfer_status(arguments["transfer_id"])
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "create_approval_request":
        result = create_approval_request(
            arguments["transfer_data"],
            arguments.get("estimated_value"),
            arguments.get("priority", "medium")
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "approve_transfer":
        result = approve_transfer(
            arguments["approval_id"],
            arguments["approver"]
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "reject_transfer":
        result = reject_transfer(
            arguments["approval_id"],
            arguments["approver"],
            arguments["reason"]
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "log_decision":
        result = log_decision(
            arguments["agent_name"],
            arguments["decision_type"],
            arguments.get("input_data", {}),
            arguments.get("output_data", {}),
            arguments.get("reasoning", "")
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_agent_decisions":
        result = get_agent_decisions(
            arguments["agent_name"],
            arguments.get("limit", 50)
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "rollback_transfer":
        result = rollback_transfer(
            arguments["transfer_id"],
            arguments["reason"]
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    else:
        raise ValueError(f"Unknown tool: {name}")


# Tool Implementation Functions

def execute_transfer(source_warehouse_id: str, target_warehouse_id: str,
                    sku: str, quantity: int, reason: str = "",
                    requires_approval: bool = False) -> Dict:
    """Execute an atomic stock transfer using DynamoDB transactions"""
    
    transfer_id = f"TRF-{uuid.uuid4().hex[:8].upper()}"
    timestamp = datetime.utcnow().isoformat() + "Z"
    
    try:
        # If approval required, create approval request instead
        if requires_approval:
            return create_approval_request(
                transfer_data={
                    "source_warehouse_id": source_warehouse_id,
                    "target_warehouse_id": target_warehouse_id,
                    "sku": sku,
                    "quantity": quantity,
                    "reason": reason
                },
                priority="high"
            )
        
        # Execute atomic transaction
        response = dynamodb_client.transact_write_items(
            TransactItems=[
                {
                    # Decrement source warehouse
                    'Update': {
                        'TableName': 'Inventory',
                        'Key': {
                            'warehouse_id': {'S': source_warehouse_id},
                            'sku': {'S': sku}
                        },
                        'UpdateExpression': 'SET quantity = quantity - :qty, last_updated = :timestamp',
                        'ConditionExpression': 'quantity >= :qty',
                        'ExpressionAttributeValues': {
                            ':qty': {'N': str(quantity)},
                            ':timestamp': {'S': timestamp}
                        }
                    }
                },
                {
                    # Increment target warehouse
                    'Update': {
                        'TableName': 'Inventory',
                        'Key': {
                            'warehouse_id': {'S': target_warehouse_id},
                            'sku': {'S': sku}
                        },
                        'UpdateExpression': 'SET quantity = quantity + :qty, last_updated = :timestamp',
                        'ExpressionAttributeValues': {
                            ':qty': {'N': str(quantity)},
                            ':timestamp': {'S': timestamp}
                        }
                    }
                },
                {
                    # Log transfer
                    'Put': {
                        'TableName': 'Transfers',
                        'Item': {
                            'transfer_id': {'S': transfer_id},
                            'source_warehouse_id': {'S': source_warehouse_id},
                            'target_warehouse_id': {'S': target_warehouse_id},
                            'sku': {'S': sku},
                            'quantity': {'N': str(quantity)},
                            'status': {'S': 'completed'},
                            'reason': {'S': reason},
                            'requires_approval': {'BOOL': requires_approval},
                            'created_at': {'S': timestamp},
                            'completed_at': {'S': timestamp}
                        }
                    }
                }
            ]
        )
        
        return {
            "success": True,
            "transfer_id": transfer_id,
            "status": "completed",
            "timestamp": timestamp,
            "details": {
                "source_warehouse_id": source_warehouse_id,
                "target_warehouse_id": target_warehouse_id,
                "sku": sku,
                "quantity": quantity,
                "reason": reason
            }
        }
        
    except dynamodb_client.exceptions.TransactionCanceledException as e:
        # Transaction failed - likely insufficient stock
        return {
            "success": False,
            "error": "Transaction failed",
            "reason": "Insufficient stock at source warehouse or condition not met",
            "details": str(e)
        }
    except Exception as e:
        return {
            "success": False,
            "error": "Transfer execution failed",
            "reason": str(e)
        }


def get_transfer_history(warehouse_id: str = None, sku: str = None, limit: int = 50) -> Dict:
    """Get transfer history with optional filters"""
    try:
        table = dynamodb.Table('Transfers')
        
        if warehouse_id:
            # Query by warehouse (using GSI)
            response = table.query(
                IndexName='WarehouseIndex',
                KeyConditionExpression='source_warehouse_id = :wh_id OR target_warehouse_id = :wh_id',
                ExpressionAttributeValues={
                    ':wh_id': warehouse_id
                },
                Limit=limit,
                ScanIndexForward=False  # Most recent first
            )
        elif sku:
            # Query by SKU (using GSI)
            response = table.query(
                IndexName='SKUIndex',
                KeyConditionExpression='sku = :sku',
                ExpressionAttributeValues={
                    ':sku': sku
                },
                Limit=limit,
                ScanIndexForward=False
            )
        else:
            # Scan all transfers
            response = table.scan(Limit=limit)
        
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


def get_transfer_status(transfer_id: str) -> Dict:
    """Get status of a specific transfer"""
    try:
        table = dynamodb.Table('Transfers')
        response = table.get_item(
            Key={'transfer_id': transfer_id}
        )
        
        if 'Item' in response:
            return {
                "success": True,
                "data": response['Item']
            }
        else:
            return {
                "success": False,
                "error": "Transfer not found",
                "data": None
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": None
        }


def create_approval_request(transfer_data: Dict, estimated_value: float = None,
                           priority: str = "medium") -> Dict:
    """Create a transfer approval request"""
    
    approval_id = f"APR-{uuid.uuid4().hex[:8].upper()}"
    timestamp = datetime.utcnow().isoformat() + "Z"
    
    try:
        table = dynamodb.Table('ApprovalQueue')
        table.put_item(
            Item={
                'approval_id': approval_id,
                'transfer_data': transfer_data,
                'estimated_value': estimated_value,
                'priority': priority,
                'status': 'pending',
                'created_at': timestamp,
                'updated_at': timestamp
            }
        )
        
        return {
            "success": True,
            "approval_id": approval_id,
            "status": "pending",
            "message": "Approval request created. Waiting for human review."
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def approve_transfer(approval_id: str, approver: str) -> Dict:
    """Approve a pending transfer and execute it"""
    try:
        # Get approval request
        table = dynamodb.Table('ApprovalQueue')
        response = table.get_item(
            Key={'approval_id': approval_id}
        )
        
        if 'Item' not in response:
            return {
                "success": False,
                "error": "Approval request not found"
            }
        
        approval = response['Item']
        
        if approval['status'] != 'pending':
            return {
                "success": False,
                "error": f"Approval already {approval['status']}"
            }
        
        # Execute the transfer
        transfer_data = approval['transfer_data']
        transfer_result = execute_transfer(
            source_warehouse_id=transfer_data['source_warehouse_id'],
            target_warehouse_id=transfer_data['target_warehouse_id'],
            sku=transfer_data['sku'],
            quantity=transfer_data['quantity'],
            reason=transfer_data.get('reason', ''),
            requires_approval=False  # Already approved
        )
        
        # Update approval status
        timestamp = datetime.utcnow().isoformat() + "Z"
        table.update_item(
            Key={'approval_id': approval_id},
            UpdateExpression='SET #status = :status, approver = :approver, updated_at = :timestamp',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'approved',
                ':approver': approver,
                ':timestamp': timestamp
            }
        )
        
        return {
            "success": True,
            "approval_id": approval_id,
            "status": "approved",
            "transfer_result": transfer_result
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def reject_transfer(approval_id: str, approver: str, reason: str) -> Dict:
    """Reject a pending transfer"""
    try:
        table = dynamodb.Table('ApprovalQueue')
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        response = table.update_item(
            Key={'approval_id': approval_id},
            UpdateExpression='SET #status = :status, approver = :approver, rejection_reason = :reason, updated_at = :timestamp',
            ConditionExpression='#status = :pending',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'rejected',
                ':approver': approver,
                ':reason': reason,
                ':timestamp': timestamp,
                ':pending': 'pending'
            },
            ReturnValues='ALL_NEW'
        )
        
        return {
            "success": True,
            "approval_id": approval_id,
            "status": "rejected",
            "reason": reason
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def log_decision(agent_name: str, decision_type: str, input_data: Dict = None,
                output_data: Dict = None, reasoning: str = "") -> Dict:
    """Log an agent decision for audit trail"""
    
    decision_id = f"DEC-{uuid.uuid4().hex[:8].upper()}"
    timestamp = datetime.utcnow().isoformat() + "Z"
    
    try:
        table = dynamodb.Table('AgentDecisions')
        table.put_item(
            Item={
                'decision_id': decision_id,
                'agent_name': agent_name,
                'decision_type': decision_type,
                'input_data': input_data or {},
                'output_data': output_data or {},
                'reasoning': reasoning,
                'timestamp': timestamp
            }
        )
        
        return {
            "success": True,
            "decision_id": decision_id,
            "timestamp": timestamp
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def get_agent_decisions(agent_name: str, limit: int = 50) -> Dict:
    """Get decision history for an agent"""
    try:
        table = dynamodb.Table('AgentDecisions')
        response = table.query(
            IndexName='AgentTimeIndex',
            KeyConditionExpression='agent_name = :agent',
            ExpressionAttributeValues={
                ':agent': agent_name
            },
            Limit=limit,
            ScanIndexForward=False  # Most recent first
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


def rollback_transfer(transfer_id: str, reason: str) -> Dict:
    """Rollback a completed transfer (emergency use)"""
    try:
        # Get original transfer
        table = dynamodb.Table('Transfers')
        response = table.get_item(
            Key={'transfer_id': transfer_id}
        )
        
        if 'Item' not in response:
            return {
                "success": False,
                "error": "Transfer not found"
            }
        
        transfer = response['Item']
        
        if transfer['status'] != 'completed':
            return {
                "success": False,
                "error": f"Cannot rollback transfer with status: {transfer['status']}"
            }
        
        # Execute reverse transfer
        rollback_result = execute_transfer(
            source_warehouse_id=transfer['target_warehouse_id'],  # Reversed
            target_warehouse_id=transfer['source_warehouse_id'],  # Reversed
            sku=transfer['sku'],
            quantity=transfer['quantity'],
            reason=f"ROLLBACK: {reason}",
            requires_approval=False
        )
        
        # Mark original transfer as rolled back
        timestamp = datetime.utcnow().isoformat() + "Z"
        table.update_item(
            Key={'transfer_id': transfer_id},
            UpdateExpression='SET #status = :status, rollback_reason = :reason, rollback_at = :timestamp',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'rolled_back',
                ':reason': reason,
                ':timestamp': timestamp
            }
        )
        
        return {
            "success": True,
            "transfer_id": transfer_id,
            "status": "rolled_back",
            "rollback_transfer": rollback_result
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


if __name__ == "__main__":
    import asyncio
    asyncio.run(app.run())

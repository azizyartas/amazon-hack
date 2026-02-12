"""Depo ve stok yönetimi veri modelleri."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class TransferStatus(str, Enum):
    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class AlertSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class OperationMode(str, Enum):
    AUTONOMOUS = "autonomous"
    SUPERVISED = "supervised"


@dataclass
class Warehouse:
    warehouse_id: str
    name: str
    location: str
    region: str
    capacity: int


@dataclass
class Product:
    sku: str
    name: str
    category: str
    price: float
    aging_threshold_days: int


@dataclass
class InventoryItem:
    warehouse_id: str
    sku: str
    quantity: int
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    entry_date: Optional[str] = None


@dataclass
class StockAlert:
    alert_id: str
    warehouse_id: str
    sku: str
    current_quantity: int
    threshold: int
    severity: AlertSeverity
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    resolved: bool = False


@dataclass
class TransferRequest:
    transfer_id: str
    source_warehouse_id: str
    target_warehouse_id: str
    sku: str
    quantity: int
    status: TransferStatus = TransferStatus.PENDING
    reason: str = ""
    priority_score: float = 0.0
    requires_approval: bool = False
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: Optional[str] = None


@dataclass
class SalesPrediction:
    warehouse_id: str
    sku: str
    predicted_daily_sales: float
    sales_potential_score: float
    seasonal_factor: float
    regional_factor: float
    confidence: float


@dataclass
class AgingInfo:
    warehouse_id: str
    sku: str
    entry_date: str
    days_in_warehouse: int
    aging_threshold_days: int
    is_critical: bool
    category: str


@dataclass
class AgentDecision:
    decision_id: str
    agent_name: str
    decision_type: str
    input_data: dict
    output_data: dict
    reasoning: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class ApprovalConfig:
    high_value_threshold: float = 10000.0
    high_quantity_threshold: int = 500
    mode: OperationMode = OperationMode.SUPERVISED

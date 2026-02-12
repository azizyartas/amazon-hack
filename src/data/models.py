"""Veri modelleri - tüm entity tanımları."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Warehouse:
    warehouse_id: str
    name: str
    location: str
    region: str
    capacity: int
    is_trade_hub: bool = False  # Ticaret merkezi mi?


@dataclass
class Category:
    name: str
    aging_threshold_days: int
    min_stock_multiplier: float


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
    min_threshold: int
    max_threshold: int
    received_date: str  # ISO 8601
    last_updated: str  # ISO 8601


@dataclass
class SalesRecord:
    warehouse_id: str
    sku: str
    date: str  # YYYY-MM-DD
    quantity_sold: int
    revenue: float

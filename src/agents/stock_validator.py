"""Stok Tutarlılığı ve Validasyon - Veri bütünlüğü garantileri.

Gereksinim 6: Stok Tutarlılığı ve Veri Bütünlüğü
- Atomik transfer işlem validasyonu
- Negatif stok kontrolü
- Eşzamanlı transfer tutarlılık kontrolü
- Günlük stok toplam doğrulama
- Audit log mekanizması
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class AuditLogEntry:
    entry_id: str
    operation_type: str
    warehouse_id: str
    sku: str
    quantity_before: int
    quantity_after: int
    change_amount: int
    triggered_by: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    transfer_id: Optional[str] = None
    details: Optional[dict] = None


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class StockValidator:
    """Stok tutarlılığı ve validasyon yöneticisi."""

    def __init__(self) -> None:
        self._audit_log: list[AuditLogEntry] = []
        # Stok snapshot'ları: {(warehouse_id, sku): quantity}
        self._stock_snapshot: dict[tuple[str, str], int] = {}
        # Toplam stok kayıtları: {sku: total}
        self._total_stock_registry: dict[str, int] = {}

    # --- Gereksinim 6.1: Atomik transfer validasyonu ---

    def validate_atomic_transfer(
        self,
        source_warehouse_id: str,
        target_warehouse_id: str,
        sku: str,
        quantity: int,
        stock_data: dict[tuple[str, str], int],
    ) -> ValidationResult:
        """Transfer işleminin atomik olarak gerçekleştirilebileceğini doğrular."""
        errors = []
        warnings = []

        if quantity <= 0:
            errors.append(f"Transfer miktarı pozitif olmalı: {quantity}")

        if source_warehouse_id == target_warehouse_id:
            errors.append("Kaynak ve hedef depo aynı olamaz")

        source_stock = stock_data.get((source_warehouse_id, sku), 0)
        if source_stock < quantity:
            errors.append(
                f"Yetersiz stok: {source_warehouse_id}/{sku} "
                f"mevcut={source_stock}, istenen={quantity}"
            )

        # Transfer sonrası negatif stok kontrolü
        if source_stock - quantity < 0:
            errors.append("Transfer sonrası kaynak depoda negatif stok oluşur")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)

    # --- Gereksinim 6.3: Negatif stok kontrolü ---

    def check_no_negative_stock(
        self, stock_data: dict[tuple[str, str], int]
    ) -> ValidationResult:
        """Tüm stok seviyelerinin negatif olmadığını doğrular (Invariant)."""
        errors = []
        for (warehouse_id, sku), quantity in stock_data.items():
            if quantity < 0:
                errors.append(
                    f"Negatif stok tespit edildi: {warehouse_id}/{sku} = {quantity}"
                )
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

    # --- Gereksinim 6.4: Eşzamanlı transfer tutarlılık kontrolü ---

    def verify_stock_conservation(
        self,
        sku: str,
        stock_before: dict[tuple[str, str], int],
        stock_after: dict[tuple[str, str], int],
    ) -> ValidationResult:
        """Transfer öncesi ve sonrası toplam stok korunumunu doğrular."""
        total_before = sum(
            qty for (_, s), qty in stock_before.items() if s == sku
        )
        total_after = sum(
            qty for (_, s), qty in stock_after.items() if s == sku
        )

        errors = []
        if total_before != total_after:
            errors.append(
                f"Stok korunumu ihlali: {sku} "
                f"önceki toplam={total_before}, sonraki toplam={total_after}"
            )

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

    # --- Gereksinim 6.6: Günlük stok toplam doğrulama ---

    def register_total_stock(self, sku: str, total: int) -> None:
        """Bir SKU'nun beklenen toplam stok miktarını kaydeder."""
        self._total_stock_registry[sku] = total

    def daily_stock_verification(
        self, stock_data: dict[tuple[str, str], int]
    ) -> dict:
        """Günlük stok toplam doğrulama job'ı.

        Tüm depolardaki stok toplamlarını kayıtlı toplamlarla karşılaştırır.
        """
        results: dict[str, dict] = {}

        # SKU bazında toplam hesapla
        actual_totals: dict[str, int] = {}
        for (_, sku), qty in stock_data.items():
            actual_totals[sku] = actual_totals.get(sku, 0) + qty

        discrepancies = []
        for sku, expected_total in self._total_stock_registry.items():
            actual = actual_totals.get(sku, 0)
            is_match = actual == expected_total
            results[sku] = {
                "expected": expected_total,
                "actual": actual,
                "match": is_match,
            }
            if not is_match:
                discrepancies.append({
                    "sku": sku,
                    "expected": expected_total,
                    "actual": actual,
                    "difference": actual - expected_total,
                })

        return {
            "verification_date": datetime.utcnow().isoformat(),
            "total_skus_checked": len(self._total_stock_registry),
            "discrepancies_found": len(discrepancies),
            "discrepancies": discrepancies,
            "all_valid": len(discrepancies) == 0,
            "details": results,
        }

    # --- Gereksinim 6.5: Audit log mekanizması ---

    def log_stock_change(
        self,
        operation_type: str,
        warehouse_id: str,
        sku: str,
        quantity_before: int,
        quantity_after: int,
        triggered_by: str,
        transfer_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> AuditLogEntry:
        """Stok değişikliğini audit log'a kaydeder."""
        entry = AuditLogEntry(
            entry_id=str(uuid.uuid4()),
            operation_type=operation_type,
            warehouse_id=warehouse_id,
            sku=sku,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            change_amount=quantity_after - quantity_before,
            triggered_by=triggered_by,
            transfer_id=transfer_id,
            details=details,
        )
        self._audit_log.append(entry)
        return entry

    def get_audit_log(
        self,
        warehouse_id: Optional[str] = None,
        sku: Optional[str] = None,
    ) -> list[AuditLogEntry]:
        """Audit log'u filtreli olarak döndürür."""
        entries = self._audit_log
        if warehouse_id:
            entries = [e for e in entries if e.warehouse_id == warehouse_id]
        if sku:
            entries = [e for e in entries if e.sku == sku]
        return entries

    def take_snapshot(self, stock_data: dict[tuple[str, str], int]) -> None:
        """Mevcut stok durumunun snapshot'ını alır."""
        self._stock_snapshot = dict(stock_data)

    def get_snapshot(self) -> dict[tuple[str, str], int]:
        """Son snapshot'ı döndürür."""
        return dict(self._stock_snapshot)

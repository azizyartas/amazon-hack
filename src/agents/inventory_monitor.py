"""Inventory Monitor Agent - Stok seviyelerini izler ve kritik durumları tespit eder.

Gereksinim 1: Stok Seviyesi İzleme
- Tüm depolardaki stok seviyelerini sürekli izler
- Kritik stok eşiğinin altına düşen SKU'lar için uyarı oluşturur
- Her depo için minimum stok eşiklerini saklar
- Nova model ile stok trend analizi yapar
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from boto3.dynamodb.conditions import Key

from src.agents.base_agent import BaseAgent
from src.models.warehouse import AlertSeverity, InventoryItem, StockAlert

logger = logging.getLogger(__name__)


class InventoryMonitorAgent(BaseAgent):
    """Stok seviyelerini izleyen ve kritik durumları tespit eden agent."""

    def __init__(self, region_name: str = "us-east-1", **kwargs: Any):
        super().__init__(
            agent_name="InventoryMonitorAgent",
            model_id="us.amazon.nova-lite-v1:0",
            region_name=region_name,
            **kwargs,
        )
        # Depo/SKU bazında minimum stok eşikleri: {(warehouse_id, sku): threshold}
        self._thresholds: dict[tuple[str, str], int] = {}
        # Mevcut stok verileri: {(warehouse_id, sku): InventoryItem}
        self._inventory: dict[tuple[str, str], InventoryItem] = {}

    # --- Gereksinim 1.3: Minimum stok eşiklerini saklama ---

    def set_threshold(self, warehouse_id: str, sku: str, threshold: int) -> None:
        """Bir depo-SKU çifti için minimum stok eşiğini ayarlar."""
        if threshold < 0:
            raise ValueError("Eşik değeri negatif olamaz")
        self._thresholds[(warehouse_id, sku)] = threshold

    def get_threshold(self, warehouse_id: str, sku: str) -> Optional[int]:
        """Bir depo-SKU çifti için minimum stok eşiğini döndürür."""
        return self._thresholds.get((warehouse_id, sku))

    # --- Gereksinim 1.1: Stok seviyesi izleme ---

    def update_stock(self, warehouse_id: str, sku: str, quantity: int) -> InventoryItem:
        """Bir depo-SKU çifti için stok seviyesini günceller."""
        item = InventoryItem(warehouse_id=warehouse_id, sku=sku, quantity=quantity)
        self._inventory[(warehouse_id, sku)] = item
        return item

    def get_stock(self, warehouse_id: str, sku: str) -> Optional[InventoryItem]:
        """Bir depo-SKU çifti için mevcut stok bilgisini döndürür."""
        return self._inventory.get((warehouse_id, sku))

    def get_all_inventory(self) -> list[InventoryItem]:
        """Tüm stok verilerini döndürür."""
        return list(self._inventory.values())

    def get_warehouse_inventory(self, warehouse_id: str) -> list[InventoryItem]:
        """Belirli bir deponun tüm stok verilerini döndürür."""
        return [
            item
            for key, item in self._inventory.items()
            if key[0] == warehouse_id
        ]

    # --- Gereksinim 1.2: Kritik stok tespiti ve uyarı ---

    def detect_critical_stock(self, default_threshold: int = 20) -> list[StockAlert]:
        """Kritik stok seviyelerini tespit eder ve uyarı listesi döndürür.

        Her depo-SKU çifti için:
        - Özel eşik tanımlıysa onu kullanır
        - Tanımlı değilse default_threshold kullanır
        - Stok < eşik ise uyarı oluşturur
        """
        alerts: list[StockAlert] = []

        for (warehouse_id, sku), item in self._inventory.items():
            threshold = self._thresholds.get((warehouse_id, sku), default_threshold)
            if item.quantity < threshold:
                severity = self._calculate_severity(item.quantity, threshold)
                alert = StockAlert(
                    alert_id=str(uuid.uuid4()),
                    warehouse_id=warehouse_id,
                    sku=sku,
                    current_quantity=item.quantity,
                    threshold=threshold,
                    severity=severity,
                )
                alerts.append(alert)

        if alerts:
            self.log_decision(
                decision_type="critical_stock_detection",
                input_data={"inventory_count": len(self._inventory), "default_threshold": default_threshold},
                output_data={"alert_count": len(alerts), "alert_skus": [a.sku for a in alerts]},
                reasoning=f"{len(alerts)} SKU kritik stok seviyesinin altında tespit edildi.",
            )

        return alerts

    def _calculate_severity(self, quantity: int, threshold: int) -> AlertSeverity:
        """Stok seviyesine göre uyarı şiddetini hesaplar."""
        if quantity == 0:
            return AlertSeverity.CRITICAL
        ratio = quantity / threshold
        if ratio < 0.25:
            return AlertSeverity.HIGH
        if ratio < 0.5:
            return AlertSeverity.MEDIUM
        return AlertSeverity.LOW

    # --- Görev 4.4: Stok geçmişi sorgulama ---

    def query_stock_history(self, warehouse_id: str, sku: str) -> list[dict]:
        """DynamoDB'den stok geçmişini sorgular."""
        try:
            response = self.inventory_table.query(
                KeyConditionExpression=Key("warehouse_id").eq(warehouse_id) & Key("sku").eq(sku)
            )
            return response.get("Items", [])
        except Exception as e:
            logger.error("Stok geçmişi sorgulama hatası: %s", e)
            return []

    # --- Görev 4.5: Düşük stok bildirimi ---

    def notify_low_stock(self, alerts: list[StockAlert]) -> list[dict]:
        """Düşük stok uyarılarını bildirim olarak hazırlar.

        Transfer Coordinator Agent'a iletilmek üzere bildirim listesi döndürür.
        """
        notifications = []
        for alert in alerts:
            notifications.append(
                {
                    "type": "low_stock_notification",
                    "warehouse_id": alert.warehouse_id,
                    "sku": alert.sku,
                    "current_quantity": alert.current_quantity,
                    "threshold": alert.threshold,
                    "severity": alert.severity.value,
                    "requires_transfer": True,
                }
            )
        return notifications

    # --- Görev 4.6: Nova model ile stok trend analizi ---

    def analyze_stock_trends(self, warehouse_id: str, sku: str) -> dict:
        """Nova model kullanarak stok trendlerini analiz eder."""
        item = self._inventory.get((warehouse_id, sku))
        if not item:
            return {"error": "Stok verisi bulunamadı"}

        threshold = self._thresholds.get((warehouse_id, sku), 20)

        prompt = (
            f"Depo {warehouse_id}, SKU {sku} için stok analizi yap.\n"
            f"Mevcut stok: {item.quantity}, Minimum eşik: {threshold}\n"
            f"Stok durumunu değerlendir ve trend tahmini yap. "
            f"JSON formatında yanıt ver: "
            f'{{"trend": "increasing|decreasing|stable", "risk_level": "low|medium|high", "recommendation": "..."}}'
        )

        try:
            response_text = self.invoke_model(prompt, max_tokens=500, temperature=0.3)
            self.log_decision(
                decision_type="stock_trend_analysis",
                input_data={"warehouse_id": warehouse_id, "sku": sku, "quantity": item.quantity},
                output_data={"model_response": response_text},
                reasoning="Nova model ile stok trend analizi yapıldı.",
            )
            return {"warehouse_id": warehouse_id, "sku": sku, "analysis": response_text}
        except Exception as e:
            logger.error("Trend analizi hatası: %s", e)
            return {"error": str(e)}

    # --- BaseAgent.process implementasyonu ---

    def process(self, default_threshold: int = 20) -> dict:
        """Ana işlem döngüsü: stok izle, kritik durumları tespit et, bildirim oluştur."""
        alerts = self.detect_critical_stock(default_threshold)
        notifications = self.notify_low_stock(alerts)

        return {
            "agent": self.agent_name,
            "total_inventory_items": len(self._inventory),
            "alerts": len(alerts),
            "notifications": notifications,
        }

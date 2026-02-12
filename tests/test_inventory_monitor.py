"""Inventory Monitor Agent unit testleri."""

import pytest
from unittest.mock import MagicMock

from src.agents.inventory_monitor import InventoryMonitorAgent
from src.models.warehouse import AlertSeverity


def _create_agent() -> InventoryMonitorAgent:
    """Test için mock'lanmış agent oluşturur."""
    return InventoryMonitorAgent(
        bedrock_runtime_client=MagicMock(),
        dynamodb_resource=MagicMock(),
        s3_client=MagicMock(),
    )


class TestThresholdManagement:
    """Gereksinim 1.3: Minimum stok eşiklerini saklama."""

    def test_set_and_get_threshold(self):
        agent = _create_agent()
        agent.set_threshold("WH001", "SKU001", 20)
        assert agent.get_threshold("WH001", "SKU001") == 20

    def test_threshold_round_trip(self):
        """Özellik 2: Eşik kaydedilip geri okunabilmeli."""
        agent = _create_agent()
        agent.set_threshold("WH001", "SKU001", 50)
        assert agent.get_threshold("WH001", "SKU001") == 50

    def test_threshold_not_set_returns_none(self):
        agent = _create_agent()
        assert agent.get_threshold("WH001", "SKU001") is None

    def test_negative_threshold_raises(self):
        agent = _create_agent()
        with pytest.raises(ValueError):
            agent.set_threshold("WH001", "SKU001", -5)


class TestStockMonitoring:
    """Gereksinim 1.1, 1.2: Stok izleme ve kritik stok tespiti."""

    def test_update_and_get_stock(self):
        agent = _create_agent()
        agent.update_stock("WH001", "SKU001", 100)
        item = agent.get_stock("WH001", "SKU001")
        assert item is not None
        assert item.quantity == 100

    def test_detect_low_stock(self):
        """Özellik 1: Stok < eşik olduğunda uyarı oluşturulmalı."""
        agent = _create_agent()
        agent.set_threshold("WH001", "SKU001", 20)
        agent.update_stock("WH001", "SKU001", 10)
        alerts = agent.detect_critical_stock()
        assert len(alerts) == 1
        assert alerts[0].sku == "SKU001"
        assert alerts[0].warehouse_id == "WH001"

    def test_no_alert_when_stock_sufficient(self):
        agent = _create_agent()
        agent.set_threshold("WH001", "SKU001", 20)
        agent.update_stock("WH001", "SKU001", 30)
        alerts = agent.detect_critical_stock()
        assert len(alerts) == 0

    def test_zero_stock_critical_severity(self):
        agent = _create_agent()
        agent.update_stock("WH001", "SKU001", 0)
        alerts = agent.detect_critical_stock(default_threshold=10)
        assert len(alerts) == 1
        assert alerts[0].severity == AlertSeverity.CRITICAL

    def test_multiple_warehouses_alerts(self):
        agent = _create_agent()
        agent.update_stock("WH001", "SKU001", 5)
        agent.update_stock("WH002", "SKU001", 3)
        agent.update_stock("WH003", "SKU001", 50)
        alerts = agent.detect_critical_stock(default_threshold=10)
        assert len(alerts) == 2

    def test_get_warehouse_inventory(self):
        agent = _create_agent()
        agent.update_stock("WH001", "SKU001", 10)
        agent.update_stock("WH001", "SKU002", 20)
        agent.update_stock("WH002", "SKU001", 30)
        items = agent.get_warehouse_inventory("WH001")
        assert len(items) == 2

    def test_notify_low_stock(self):
        agent = _create_agent()
        agent.update_stock("WH001", "SKU001", 5)
        alerts = agent.detect_critical_stock(default_threshold=20)
        notifications = agent.notify_low_stock(alerts)
        assert len(notifications) == 1
        assert notifications[0]["requires_transfer"] is True

    def test_process_returns_summary(self):
        agent = _create_agent()
        agent.update_stock("WH001", "SKU001", 5)
        result = agent.process(default_threshold=20)
        assert result["alerts"] == 1
        assert len(result["notifications"]) == 1

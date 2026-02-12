"""Stock Aging Analyzer Agent unit testleri."""

import pytest
from unittest.mock import MagicMock

from src.agents.stock_aging_analyzer import StockAgingAnalyzerAgent


def _create_agent() -> StockAgingAnalyzerAgent:
    return StockAgingAnalyzerAgent(
        bedrock_runtime_client=MagicMock(),
        dynamodb_resource=MagicMock(),
        s3_client=MagicMock(),
    )


class TestAgingCalculation:
    """Gereksinim 4.1: Yaşlandırma süresi hesaplama."""

    def test_calculate_aging_days(self):
        """Özellik 9: Sistem ürünün depoda kalma süresini hesaplayabilmeli."""
        agent = _create_agent()
        agent.set_entry_date("WH001", "SKU001", "2025-01-01T00:00:00")
        agent.set_product_category("SKU001", "Elektronik")

        aging = agent.calculate_aging("WH001", "SKU001", reference_date="2025-04-01T00:00:00")
        assert aging.days_in_warehouse == 90
        assert aging.warehouse_id == "WH001"
        assert aging.sku == "SKU001"

    def test_critical_aging_detection(self):
        """Özellik 10: Kritik eşiği aşan ürünler tespit edilmeli."""
        agent = _create_agent()
        agent.set_entry_date("WH001", "SKU001", "2025-01-01T00:00:00")
        agent.set_product_category("SKU001", "Elektronik")  # 90 gün eşik

        aging = agent.calculate_aging("WH001", "SKU001", reference_date="2025-05-01T00:00:00")
        assert aging.is_critical is True  # 120 gün > 90 gün eşik

    def test_not_critical_aging(self):
        agent = _create_agent()
        agent.set_entry_date("WH001", "SKU001", "2025-01-01T00:00:00")
        agent.set_product_category("SKU001", "Elektronik")

        aging = agent.calculate_aging("WH001", "SKU001", reference_date="2025-02-01T00:00:00")
        assert aging.is_critical is False  # 31 gün < 90 gün eşik

    def test_missing_entry_date_raises(self):
        agent = _create_agent()
        with pytest.raises(ValueError):
            agent.calculate_aging("WH001", "SKU001")


class TestCategoryThresholds:
    """Gereksinim 4.3: Kategori bazlı yaşlandırma eşikleri."""

    def test_food_category_threshold(self):
        """Özellik 11: Kategori bazlı eşik uygulanmalı."""
        agent = _create_agent()
        agent.set_product_category("SKU001", "Gıda")
        assert agent.get_aging_threshold("SKU001") == 30

    def test_furniture_category_threshold(self):
        agent = _create_agent()
        agent.set_product_category("SKU001", "Mobilya")
        assert agent.get_aging_threshold("SKU001") == 365

    def test_custom_threshold_override(self):
        agent = _create_agent()
        agent.set_product_category("SKU001", "Gıda")
        agent.set_custom_threshold("Gıda", 15)
        assert agent.get_aging_threshold("SKU001") == 15

    def test_negative_threshold_raises(self):
        agent = _create_agent()
        with pytest.raises(ValueError):
            agent.set_custom_threshold("Gıda", -10)


class TestAgingPrioritization:
    """Gereksinim 4.4: Yaşlı stok önceliklendirme."""

    def test_critical_items_first(self):
        """Özellik 10: Yaşlı stoklar daha yeni stoklardan önce transfer edilmeli."""
        agent = _create_agent()
        agent.set_product_category("SKU001", "Elektronik")  # 90 gün
        agent.set_product_category("SKU002", "Elektronik")

        agent.set_entry_date("WH001", "SKU001", "2024-01-01T00:00:00")  # çok eski
        agent.set_entry_date("WH001", "SKU002", "2025-03-01T00:00:00")  # yeni

        recommendations = agent.prioritize_aging_transfers(reference_date="2025-04-01T00:00:00")
        assert len(recommendations) == 2
        assert recommendations[0]["sku"] == "SKU001"  # Daha eski olan önce
        assert recommendations[0]["priority_score"] > recommendations[1]["priority_score"]

    def test_detect_critical_aging(self):
        agent = _create_agent()
        agent.set_product_category("SKU001", "Gıda")  # 30 gün eşik
        agent.set_entry_date("WH001", "SKU001", "2025-01-01T00:00:00")

        critical = agent.detect_critical_aging(reference_date="2025-03-01T00:00:00")
        assert len(critical) == 1
        assert critical[0].is_critical is True

    def test_daily_report(self):
        agent = _create_agent()
        agent.set_product_category("SKU001", "Gıda")
        agent.set_entry_date("WH001", "SKU001", "2025-01-01T00:00:00")

        report = agent.get_daily_aging_report(reference_date="2025-03-01T00:00:00")
        assert report["total_tracked_items"] == 1
        assert report["critical_items_count"] == 1

"""Sales Predictor Agent unit testleri."""

from unittest.mock import MagicMock

from src.agents.sales_predictor import SalesPredictorAgent


def _create_agent() -> SalesPredictorAgent:
    return SalesPredictorAgent(
        bedrock_runtime_client=MagicMock(),
        dynamodb_resource=MagicMock(),
        s3_client=MagicMock(),
    )


class TestSalesPotentialCalculation:
    """Gereksinim 3.1: Satış potansiyeli hesaplama."""

    def test_calculate_sales_potential(self):
        """Özellik 7: Sistem bir satış potansiyeli skoru hesaplayabilmeli."""
        agent = _create_agent()
        agent.set_sales_history("WH001", "SKU001", [100, 120, 110, 130, 140, 150, 160, 170, 180, 190, 200, 210])
        agent.set_warehouse_region("WH001", "Marmara")
        agent.set_product_category("SKU001", "Elektronik")

        prediction = agent.calculate_sales_potential("WH001", "SKU001")
        assert prediction.sales_potential_score >= 0
        assert prediction.warehouse_id == "WH001"
        assert prediction.sku == "SKU001"

    def test_zero_sales_history(self):
        agent = _create_agent()
        prediction = agent.calculate_sales_potential("WH001", "SKU001")
        assert prediction.sales_potential_score == 0.0
        assert prediction.predicted_daily_sales == 0.0


class TestSeasonalFactors:
    """Gereksinim 3.4: Mevsimsel trend tespiti."""

    def test_electronics_high_season(self):
        agent = _create_agent()
        agent.set_product_category("SKU001", "Elektronik")
        factor = agent.calculate_seasonal_factor("SKU001", month=12)
        assert factor == 2.5

    def test_electronics_low_season(self):
        agent = _create_agent()
        agent.set_product_category("SKU001", "Elektronik")
        factor = agent.calculate_seasonal_factor("SKU001", month=6)
        assert factor == 1.0

    def test_unknown_category(self):
        agent = _create_agent()
        factor = agent.calculate_seasonal_factor("SKU_UNKNOWN", month=12)
        assert factor == 1.0


class TestRegionalFactors:
    """Gereksinim 3.5: Bölgesel faktör hesaplama."""

    def test_marmara_region(self):
        agent = _create_agent()
        agent.set_warehouse_region("WH001", "Marmara")
        assert agent.calculate_regional_factor("WH001") == 1.5

    def test_karadeniz_region(self):
        agent = _create_agent()
        agent.set_warehouse_region("WH002", "Karadeniz")
        assert agent.calculate_regional_factor("WH002") == 1.0

    def test_unknown_region(self):
        agent = _create_agent()
        assert agent.calculate_regional_factor("WH_UNKNOWN") == 1.0


class TestWarehouseRanking:
    """Gereksinim 3.2, 3.5: Depo sıralama ve en iyi depo seçimi."""

    def test_rank_by_potential(self):
        """Özellik 8: En yüksek satış potansiyeline sahip depo seçilmeli."""
        agent = _create_agent()
        agent.set_sales_history("WH001", "SKU001", [100] * 12)
        agent.set_sales_history("WH002", "SKU001", [200] * 12)
        agent.set_warehouse_region("WH001", "Karadeniz")
        agent.set_warehouse_region("WH002", "Marmara")
        agent.set_product_category("SKU001", "Elektronik")

        ranked = agent.rank_warehouses_by_potential("SKU001", ["WH001", "WH002"])
        assert ranked[0].warehouse_id == "WH002"

    def test_get_best_warehouse(self):
        agent = _create_agent()
        agent.set_sales_history("WH001", "SKU001", [50] * 12)
        agent.set_sales_history("WH002", "SKU001", [150] * 12)
        agent.set_warehouse_region("WH001", "Ege")
        agent.set_warehouse_region("WH002", "Marmara")
        agent.set_product_category("SKU001", "Giyim")

        best = agent.get_best_warehouse("SKU001", ["WH001", "WH002"])
        assert best is not None
        assert best.warehouse_id == "WH002"


class TestSalesHistoryAnalysis:
    """Gereksinim 3.3: Geçmiş satış verisi analizi."""

    def test_increasing_trend(self):
        agent = _create_agent()
        agent.set_sales_history("WH001", "SKU001", [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120])
        analysis = agent.analyze_sales_history("WH001", "SKU001")
        assert analysis["trend"] == "increasing"

    def test_decreasing_trend(self):
        agent = _create_agent()
        agent.set_sales_history("WH001", "SKU001", [120, 110, 100, 90, 80, 70, 60, 50, 40, 30, 20, 10])
        analysis = agent.analyze_sales_history("WH001", "SKU001")
        assert analysis["trend"] == "decreasing"

    def test_no_history(self):
        agent = _create_agent()
        analysis = agent.analyze_sales_history("WH001", "SKU001")
        assert analysis["avg_monthly_sales"] == 0.0
        assert analysis["trend"] == "unknown"

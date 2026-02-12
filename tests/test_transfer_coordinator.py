"""Transfer Coordinator Agent unit testleri."""

import pytest
from unittest.mock import MagicMock

from src.agents.transfer_coordinator import (
    TransferCoordinatorAgent,
    ValidationError,
    InsufficientStockError,
)
from src.models.warehouse import (
    ApprovalConfig,
    OperationMode,
    SalesPrediction,
    TransferStatus,
)


def _create_agent() -> TransferCoordinatorAgent:
    return TransferCoordinatorAgent(
        bedrock_runtime_client=MagicMock(),
        dynamodb_resource=MagicMock(),
        s3_client=MagicMock(),
    )


class TestTransferValidation:
    """Gereksinim 2.4, 6.2: Transfer öncesi validasyon."""

    def test_valid_transfer(self):
        agent = _create_agent()
        agent.set_stock("WH001", "SKU001", 100)
        assert agent.validate_transfer("WH001", "WH002", "SKU001", 50) is True

    def test_insufficient_stock_raises(self):
        agent = _create_agent()
        agent.set_stock("WH001", "SKU001", 10)
        with pytest.raises(InsufficientStockError):
            agent.validate_transfer("WH001", "WH002", "SKU001", 50)

    def test_zero_quantity_raises(self):
        agent = _create_agent()
        with pytest.raises(ValidationError):
            agent.validate_transfer("WH001", "WH002", "SKU001", 0)

    def test_same_warehouse_raises(self):
        agent = _create_agent()
        agent.set_stock("WH001", "SKU001", 100)
        with pytest.raises(ValidationError):
            agent.validate_transfer("WH001", "WH001", "SKU001", 10)


class TestTransferExecution:
    """Gereksinim 2.5, 6.1: Atomik transfer işlemi."""

    def test_stock_conservation(self):
        """Özellik 6: Transfer sonrası toplam stok korunmalı."""
        agent = _create_agent()
        agent.set_stock("WH001", "SKU001", 100)
        agent.set_stock("WH002", "SKU001", 50)
        total_before = agent.get_total_stock("SKU001")

        agent.execute_transfer("WH001", "WH002", "SKU001", 30)

        total_after = agent.get_total_stock("SKU001")
        assert total_before == total_after

    def test_source_decreases_target_increases(self):
        agent = _create_agent()
        agent.set_stock("WH001", "SKU001", 100)
        agent.set_stock("WH002", "SKU001", 50)

        agent.execute_transfer("WH001", "WH002", "SKU001", 30)

        assert agent.get_stock("WH001", "SKU001") == 70
        assert agent.get_stock("WH002", "SKU001") == 80

    def test_no_negative_stock_after_transfer(self):
        """Özellik 17: Negatif stok yasağı."""
        agent = _create_agent()
        agent.set_stock("WH001", "SKU001", 10)
        with pytest.raises(InsufficientStockError):
            agent.execute_transfer("WH001", "WH002", "SKU001", 20)

    def test_transfer_status_completed(self):
        agent = _create_agent()
        agent.set_stock("WH001", "SKU001", 100)
        transfer = agent.execute_transfer("WH001", "WH002", "SKU001", 30)
        assert transfer.status == TransferStatus.COMPLETED


class TestSourceWarehouseSelection:
    """Gereksinim 2.2: Kaynak depo seçimi."""

    def test_select_source_with_most_stock(self):
        """Özellik 3: Kaynak depo yeterli stok seviyesine sahip olmalı."""
        agent = _create_agent()
        agent.set_stock("WH001", "SKU001", 200)
        agent.set_stock("WH002", "SKU001", 100)
        agent.set_stock("WH003", "SKU001", 50)

        source = agent.select_source_warehouse("SKU001", "WH003", 30)
        assert source == "WH001"  # En fazla stok olan

    def test_no_source_when_insufficient(self):
        agent = _create_agent()
        agent.set_stock("WH001", "SKU001", 5)
        source = agent.select_source_warehouse("SKU001", "WH002", 50)
        assert source is None

    def test_excludes_target_warehouse(self):
        agent = _create_agent()
        agent.set_stock("WH001", "SKU001", 100)
        source = agent.select_source_warehouse("SKU001", "WH001", 30)
        assert source is None


class TestTransferQuantityCalculation:
    """Gereksinim 2.3: Transfer miktarı hesaplama."""

    def test_quantity_does_not_exceed_source(self):
        """Özellik 4: Transfer miktarı kaynak stokunu aşmamalı."""
        agent = _create_agent()
        agent.set_stock("WH001", "SKU001", 50)
        qty = agent.calculate_transfer_quantity("WH001", "WH002", "SKU001", 100)
        assert qty <= 50

    def test_zero_source_stock(self):
        agent = _create_agent()
        agent.set_stock("WH001", "SKU001", 0)
        qty = agent.calculate_transfer_quantity("WH001", "WH002", "SKU001", 10)
        assert qty == 0


class TestApprovalMechanism:
    """Gereksinim 10: İnsan onayı mekanizması."""

    def test_high_value_requires_approval(self):
        """Özellik 27: Yüksek değerli transfer onay gerektirmeli."""
        agent = _create_agent()
        agent.set_product_price("SKU001", 500.0)
        config = ApprovalConfig(high_value_threshold=5000.0, mode=OperationMode.SUPERVISED)
        agent.set_approval_config(config)
        assert agent.requires_approval("SKU001", 20) is True  # 500*20 = 10000 > 5000

    def test_autonomous_mode_no_approval(self):
        """Özellik 32: Otonom modda onay gerekmemeli."""
        agent = _create_agent()
        agent.set_product_price("SKU001", 500.0)
        config = ApprovalConfig(mode=OperationMode.AUTONOMOUS)
        agent.set_approval_config(config)
        assert agent.requires_approval("SKU001", 100) is False

    def test_approval_queue(self):
        """Özellik 28: Onay bekleyen işlem kuyrukta tutulmalı."""
        agent = _create_agent()
        agent.set_stock("WH001", "SKU001", 100)
        agent.set_product_price("SKU001", 1000.0)
        config = ApprovalConfig(high_value_threshold=5000.0, mode=OperationMode.SUPERVISED)
        agent.set_approval_config(config)

        transfer = agent.execute_transfer("WH001", "WH002", "SKU001", 10)
        assert transfer.status == TransferStatus.AWAITING_APPROVAL
        assert len(agent.get_pending_approvals()) == 1

    def test_approve_completes_transfer(self):
        """Özellik 29: Onay sonrası transfer tamamlanmalı."""
        agent = _create_agent()
        agent.set_stock("WH001", "SKU001", 100)
        agent.set_product_price("SKU001", 1000.0)
        config = ApprovalConfig(high_value_threshold=5000.0, mode=OperationMode.SUPERVISED)
        agent.set_approval_config(config)

        transfer = agent.execute_transfer("WH001", "WH002", "SKU001", 10)
        completed = agent.approve_transfer(transfer.transfer_id)
        assert completed.status == TransferStatus.COMPLETED

    def test_reject_offers_alternatives(self):
        """Özellik 30: Red sonrası alternatif öneriler."""
        agent = _create_agent()
        agent.set_stock("WH001", "SKU001", 100)
        agent.set_stock("WH003", "SKU001", 200)
        agent.set_product_price("SKU001", 1000.0)
        config = ApprovalConfig(high_value_threshold=5000.0, mode=OperationMode.SUPERVISED)
        agent.set_approval_config(config)

        transfer = agent.execute_transfer("WH001", "WH002", "SKU001", 10)
        alternatives = agent.reject_transfer(transfer.transfer_id)
        assert len(alternatives) > 0

    def test_target_selection_by_sales_potential(self):
        """Özellik 8: En yüksek satış potansiyeline sahip depo seçilmeli."""
        agent = _create_agent()
        predictions = [
            SalesPrediction("WH002", "SKU001", 5.0, 80.0, 1.5, 1.2, 0.9),
            SalesPrediction("WH003", "SKU001", 3.0, 60.0, 1.0, 1.0, 0.8),
            SalesPrediction("WH004", "SKU001", 7.0, 95.0, 2.0, 1.5, 0.95),
        ]
        target = agent.select_target_warehouse("SKU001", "WH001", predictions)
        assert target == "WH004"  # En yüksek skor

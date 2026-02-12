"""Stock Validator unit testleri."""

from src.agents.stock_validator import StockValidator


class TestAtomicTransferValidation:
    """Gereksinim 6.1: Atomik transfer validasyonu."""

    def test_valid_transfer(self):
        validator = StockValidator()
        stock = {("WH001", "SKU001"): 100, ("WH002", "SKU001"): 50}
        result = validator.validate_atomic_transfer("WH001", "WH002", "SKU001", 30, stock)
        assert result.is_valid is True

    def test_insufficient_stock(self):
        validator = StockValidator()
        stock = {("WH001", "SKU001"): 10}
        result = validator.validate_atomic_transfer("WH001", "WH002", "SKU001", 50, stock)
        assert result.is_valid is False

    def test_same_warehouse(self):
        validator = StockValidator()
        stock = {("WH001", "SKU001"): 100}
        result = validator.validate_atomic_transfer("WH001", "WH001", "SKU001", 10, stock)
        assert result.is_valid is False

    def test_zero_quantity(self):
        validator = StockValidator()
        stock = {("WH001", "SKU001"): 100}
        result = validator.validate_atomic_transfer("WH001", "WH002", "SKU001", 0, stock)
        assert result.is_valid is False


class TestNegativeStockCheck:
    """Gereksinim 6.3: Negatif stok kontrolü."""

    def test_no_negative_stock(self):
        """Özellik 17: Negatif stok yasağı."""
        validator = StockValidator()
        stock = {("WH001", "SKU001"): 100, ("WH002", "SKU001"): 50}
        result = validator.check_no_negative_stock(stock)
        assert result.is_valid is True

    def test_negative_stock_detected(self):
        validator = StockValidator()
        stock = {("WH001", "SKU001"): -5, ("WH002", "SKU001"): 50}
        result = validator.check_no_negative_stock(stock)
        assert result.is_valid is False


class TestStockConservation:
    """Gereksinim 6.4: Stok korunumu."""

    def test_conservation_holds(self):
        """Özellik 6: Transfer sonrası toplam stok korunmalı."""
        validator = StockValidator()
        before = {("WH001", "SKU001"): 100, ("WH002", "SKU001"): 50}
        after = {("WH001", "SKU001"): 70, ("WH002", "SKU001"): 80}
        result = validator.verify_stock_conservation("SKU001", before, after)
        assert result.is_valid is True

    def test_conservation_violated(self):
        validator = StockValidator()
        before = {("WH001", "SKU001"): 100, ("WH002", "SKU001"): 50}
        after = {("WH001", "SKU001"): 70, ("WH002", "SKU001"): 70}  # 10 fazla
        result = validator.verify_stock_conservation("SKU001", before, after)
        assert result.is_valid is False


class TestDailyVerification:
    """Gereksinim 6.6: Günlük stok toplam doğrulama."""

    def test_daily_verification_pass(self):
        """Özellik 19: Stok toplamları kayıtlarla eşleşmeli."""
        validator = StockValidator()
        validator.register_total_stock("SKU001", 150)
        stock = {("WH001", "SKU001"): 100, ("WH002", "SKU001"): 50}
        result = validator.daily_stock_verification(stock)
        assert result["all_valid"] is True

    def test_daily_verification_fail(self):
        validator = StockValidator()
        validator.register_total_stock("SKU001", 200)
        stock = {("WH001", "SKU001"): 100, ("WH002", "SKU001"): 50}
        result = validator.daily_stock_verification(stock)
        assert result["all_valid"] is False
        assert result["discrepancies_found"] == 1


class TestAuditLog:
    """Gereksinim 6.5: Audit log mekanizması."""

    def test_log_stock_change(self):
        """Özellik 14: Stok değişiklikleri loglanmalı."""
        validator = StockValidator()
        entry = validator.log_stock_change(
            operation_type="transfer",
            warehouse_id="WH001",
            sku="SKU001",
            quantity_before=100,
            quantity_after=70,
            triggered_by="TransferCoordinatorAgent",
            transfer_id="TRF001",
        )
        assert entry.change_amount == -30
        assert len(validator.get_audit_log()) == 1

    def test_filter_audit_log(self):
        validator = StockValidator()
        validator.log_stock_change("transfer", "WH001", "SKU001", 100, 70, "agent1")
        validator.log_stock_change("transfer", "WH002", "SKU001", 50, 80, "agent1")
        validator.log_stock_change("transfer", "WH001", "SKU002", 200, 180, "agent1")

        wh1_logs = validator.get_audit_log(warehouse_id="WH001")
        assert len(wh1_logs) == 2

        sku1_logs = validator.get_audit_log(sku="SKU001")
        assert len(sku1_logs) == 2

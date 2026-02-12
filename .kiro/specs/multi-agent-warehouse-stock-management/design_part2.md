## Hata Yönetimi

### Agent Hataları

**Hata Tipleri:**
1. **Bedrock API Hataları**: Rate limiting, timeout, model unavailable
2. **Veri Tutarsızlığı**: Stok negatif, transfer validasyon hatası
3. **Agent İletişim Hataları**: Agent yanıt vermiyor, timeout
4. **DynamoDB Hataları**: Throttling, connection errors

**Hata Yönetim Stratejisi:**

```python
class AgentErrorHandler:
    def handle_bedrock_error(self, error: Exception) -> RetryDecision:
        """
        Bedrock API hatalarını yönetir
        - Rate limit: Exponential backoff ile retry
        - Timeout: 3 kez retry
        - Model unavailable: Alternatif model kullan
        """
        if isinstance(error, RateLimitError):
            return RetryDecision(
                should_retry=True,
                backoff_seconds=calculate_exponential_backoff(),
                max_retries=5
            )
        elif isinstance(error, TimeoutError):
            return RetryDecision(
                should_retry=True,
                backoff_seconds=2,
                max_retries=3
            )
        else:
            return RetryDecision(should_retry=False)
    
    def handle_data_inconsistency(self, error: DataError) -> RecoveryAction:
        """
        Veri tutarsızlığı hatalarını yönetir
        - Negatif stok: İşlemi geri al, alarm oluştur
        - Transfer validasyon: İşlemi reddet, alternatif öner
        """
        if error.type == "negative_stock":
            self.rollback_transaction(error.transaction_id)
            self.create_alert(error)
            return RecoveryAction.ROLLBACK
        elif error.type == "validation_failed":
            self.reject_transfer(error.transfer_id)
            self.suggest_alternatives(error)
            return RecoveryAction.REJECT
    
    def handle_agent_communication_error(self, error: CommunicationError) -> FallbackAction:
        """
        Agent iletişim hatalarını yönetir
        - Agent timeout: Cached data kullan
        - Agent unavailable: Fallback agent kullan
        """
        if error.type == "timeout":
            return FallbackAction.USE_CACHED_DATA
        elif error.type == "unavailable":
            return FallbackAction.USE_FALLBACK_AGENT
```

### Hata Loglama

**Log Formatı:**
```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "error_id": "ERR001",
  "agent_name": "TransferCoordinatorAgent",
  "error_type": "ValidationError",
  "error_message": "Insufficient stock at source warehouse",
  "context": {
    "transfer_id": "TRF001",
    "source_warehouse": "WH002",
    "sku": "SKU001",
    "requested_quantity": 50,
    "available_quantity": 30
  },
  "recovery_action": "REJECT",
  "severity": "WARNING"
}
```

### Circuit Breaker Pattern

Bedrock API çağrıları için circuit breaker:

```python
class BedrockCircuitBreaker:
    def __init__(self):
        self.failure_threshold = 5
        self.timeout_seconds = 60
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.failure_count = 0
        self.last_failure_time = None
    
    def call_bedrock(self, func, *args, **kwargs):
        if self.state == "OPEN":
            if self._should_attempt_reset():
                self.state = "HALF_OPEN"
            else:
                raise CircuitBreakerOpenError()
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e
    
    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
    
    def _on_success(self):
        self.failure_count = 0
        self.state = "CLOSED"
```

## Test Stratejisi

### İkili Test Yaklaşımı

Sistem hem **unit testler** hem de **property-based testler** kullanarak kapsamlı test edilecektir:

- **Unit testler**: Spesifik örnekler, edge case'ler ve hata durumları
- **Property testler**: Tüm girdiler üzerinde evrensel özellikler

### Property-Based Testing

**Test Kütüphanesi**: Hypothesis (Python için)

**Konfigürasyon**:
- Her property test minimum 100 iterasyon çalıştırılacak
- Her test tasarım dokümanındaki özelliğe referans verecek
- Tag formatı: `Feature: multi-agent-warehouse-stock-management, Property {numara}: {özellik_metni}`

**Örnek Property Test:**

```python
from hypothesis import given, strategies as st
import pytest

@given(
    warehouse_id=st.text(min_size=1, max_size=10),
    sku=st.text(min_size=1, max_size=10),
    quantity=st.integers(min_value=0, max_value=1000),
    threshold=st.integers(min_value=1, max_value=100)
)
@pytest.mark.property_test
@pytest.mark.tag("Feature: multi-agent-warehouse-stock-management, Property 1: Düşük Stok Tespiti")
def test_low_stock_detection_property(warehouse_id, sku, quantity, threshold):
    """
    Özellik 1: Düşük Stok Tespiti ve Transfer İhtiyacı
    Herhangi bir depo ve SKU için, stok seviyesi minimum eşiğin altına 
    düştüğünde, sistem bir uyarı oluşturmalı ve transfer ihtiyacını tespit etmelidir.
    """
    # Arrange
    inventory_monitor = InventoryMonitorAgent()
    inventory_monitor.set_threshold(warehouse_id, sku, threshold)
    inventory_monitor.update_stock(warehouse_id, sku, quantity)
    
    # Act
    alerts = inventory_monitor.detect_critical_stock(threshold)
    
    # Assert
    if quantity < threshold:
        assert len(alerts) > 0
        assert any(a.sku == sku and a.warehouse_id == warehouse_id for a in alerts)
    else:
        assert not any(a.sku == sku and a.warehouse_id == warehouse_id for a in alerts)
```

### Unit Testing

**Test Kategorileri:**

1. **Agent Davranış Testleri**
```python
def test_inventory_monitor_detects_low_stock():
    """Spesifik örnek: Stok 10, eşik 20 olduğunda uyarı oluşturulmalı"""
    monitor = InventoryMonitorAgent()
    monitor.set_threshold("WH001", "SKU001", 20)
    monitor.update_stock("WH001", "SKU001", 10)
    
    alerts = monitor.detect_critical_stock(20)
    
    assert len(alerts) == 1
    assert alerts[0].sku == "SKU001"
```

2. **Entegrasyon Testleri**
```python
def test_transfer_coordinator_integration():
    """Agent'lar arası iletişim testi"""
    monitor = InventoryMonitorAgent()
    coordinator = TransferCoordinatorAgent()
    predictor = SalesPredictorAgent()
    
    # Düşük stok oluştur
    monitor.update_stock("WH001", "SKU001", 5)
    alert = monitor.detect_critical_stock(20)[0]
    
    # Transfer koordinasyonu
    decision = coordinator.evaluate_transfer_need(alert)
    
    assert decision.should_transfer == True
    assert decision.target_warehouse is not None
```

3. **Edge Case Testleri**
```python
def test_transfer_with_zero_stock():
    """Edge case: Sıfır stokla transfer denemesi"""
    coordinator = TransferCoordinatorAgent()
    
    with pytest.raises(ValidationError):
        coordinator.execute_transfer(
            source="WH001",
            target="WH002",
            sku="SKU001",
            quantity=10
        )

def test_concurrent_transfers_same_sku():
    """Edge case: Aynı SKU için eşzamanlı transferler"""
    coordinator = TransferCoordinatorAgent()
    
    # İki transfer paralel başlat
    transfer1 = coordinator.execute_transfer_async(
        source="WH001", target="WH002", sku="SKU001", quantity=10
    )
    transfer2 = coordinator.execute_transfer_async(
        source="WH001", target="WH003", sku="SKU001", quantity=10
    )
    
    # Her iki transfer de tamamlanmalı ve stok tutarlı olmalı
    results = [transfer1.result(), transfer2.result()]
    assert all(r.status == "completed" for r in results)
    
    # Toplam stok korunmalı
    total_stock = get_total_stock("SKU001")
    assert total_stock == initial_stock
```

4. **Hata Durumu Testleri**
```python
def test_bedrock_api_retry_on_rate_limit():
    """Bedrock rate limit durumunda retry"""
    with patch('boto3.client') as mock_client:
        mock_client.return_value.invoke_model.side_effect = [
            RateLimitError(),
            RateLimitError(),
            {"body": json.dumps({"result": "success"})}
        ]
        
        agent = TransferCoordinatorAgent()
        result = agent.make_decision(transfer_data)
        
        assert result is not None
        assert mock_client.return_value.invoke_model.call_count == 3
```

### Simülasyon Testleri

**Senaryo Tabanlı Testler:**

```python
def test_full_transfer_simulation():
    """
    Tam simülasyon: 5 depo, 100 SKU, 30 gün
    - Günlük satışlar simüle edilir
    - Agentlar otomatik kararlar alır
    - Tüm özellikler doğrulanır
    """
    # Setup
    simulation = WarehouseSimulation(
        num_warehouses=5,
        num_skus=100,
        duration_days=30
    )
    
    # Run
    simulation.run()
    
    # Verify properties
    assert simulation.verify_property("no_negative_stock")
    assert simulation.verify_property("stock_conservation")
    assert simulation.verify_property("all_decisions_logged")
    
    # Metrics
    metrics = simulation.get_metrics()
    assert metrics["total_transfers"] > 0
    assert metrics["avg_transfer_time"] < 10  # seconds
    assert metrics["stock_out_events"] < 5
```

### Test Veri Üretimi

**Hypothesis Stratejileri:**

```python
# Depo stratejisi
warehouse_strategy = st.builds(
    Warehouse,
    warehouse_id=st.text(min_size=5, max_size=10, alphabet=st.characters(whitelist_categories=('Lu', 'Nd'))),
    name=st.text(min_size=5, max_size=50),
    region=st.sampled_from(["Marmara", "İç Anadolu", "Ege", "Akdeniz", "Karadeniz"]),
    capacity=st.integers(min_value=1000, max_value=20000)
)

# SKU stratejisi
sku_strategy = st.builds(
    Product,
    sku=st.text(min_size=6, max_size=10, alphabet=st.characters(whitelist_categories=('Lu', 'Nd'))),
    name=st.text(min_size=10, max_size=100),
    category=st.sampled_from(["Elektronik", "Giyim", "Gıda", "Mobilya", "Kitap"]),
    price=st.floats(min_value=10.0, max_value=100000.0),
    aging_threshold_days=st.integers(min_value=30, max_value=730)
)

# Transfer stratejisi
transfer_strategy = st.builds(
    Transfer,
    source_warehouse=warehouse_strategy,
    target_warehouse=warehouse_strategy,
    sku=sku_strategy,
    quantity=st.integers(min_value=1, max_value=100)
).filter(lambda t: t.source_warehouse.warehouse_id != t.target_warehouse.warehouse_id)
```

### Test Kapsamı Hedefleri

- **Kod kapsamı**: Minimum %80
- **Property test kapsamı**: Tüm 32 özellik test edilmeli
- **Agent kapsamı**: Her agent için minimum 20 unit test
- **Entegrasyon test kapsamı**: Tüm agent iletişim senaryoları
- **Simülasyon test kapsamı**: Minimum 3 farklı senaryo (düşük yük, normal yük, yüksek yük)

### CI/CD Entegrasyonu

```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest hypothesis pytest-cov
      
      - name: Run unit tests
        run: pytest tests/unit/ -v --cov=src --cov-report=xml
      
      - name: Run property tests
        run: pytest tests/property/ -v --hypothesis-show-statistics
      
      - name: Run integration tests
        run: pytest tests/integration/ -v
      
      - name: Run simulation tests
        run: pytest tests/simulation/ -v --timeout=300
      
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

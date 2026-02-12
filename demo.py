"""
Gerçek AWS Bedrock ile Agent Katmanı Demo/Test Script'i.

Kullanım:
    export AWS_DEFAULT_REGION="us-west-2"
    export AWS_ACCESS_KEY_ID="..."
    export AWS_SECRET_ACCESS_KEY="..."
    export AWS_SESSION_TOKEN="..."
    python demo.py
"""

import json
import os
import sys

import env_loader
import boto3

# Region'ı creds'ten al
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")


def check_credentials():
    """AWS credential'larının ayarlı olduğunu kontrol eder."""
    required = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print("❌ Eksik environment variable'lar:", ", ".join(missing))
        print("\nÖnce credential'ları export et:")
        print('  export AWS_DEFAULT_REGION="us-west-2"')
        print('  export AWS_ACCESS_KEY_ID="..."')
        print('  export AWS_SECRET_ACCESS_KEY="..."')
        print('  export AWS_SESSION_TOKEN="..."')
        sys.exit(1)
    print("✅ AWS credential'ları ayarlı")
    print(f"   Region: {REGION}")


def test_bedrock_connection():
    """Bedrock'a bağlantıyı test eder."""
    print("\n--- Bedrock Bağlantı Testi ---")
    try:
        client = boto3.client("bedrock", region_name=REGION)
        profiles = client.list_inference_profiles()
        nova_profiles = [
            p["inferenceProfileId"]
            for p in profiles.get("inferenceProfileSummaries", [])
            if "nova" in p.get("inferenceProfileId", "").lower()
        ]
        print(f"✅ Bedrock bağlantısı başarılı")
        print(f"   Kullanılabilir Nova profilleri: {nova_profiles}")
        return True
    except Exception as e:
        print(f"❌ Bedrock bağlantı hatası: {e}")
        return False


def test_nova_model_invoke():
    """Nova modelini doğrudan çağırarak test eder."""
    print("\n--- Nova Model Çağrı Testi ---")
    client = boto3.client("bedrock-runtime", region_name=REGION)

    # Nova Lite dene
    for model_id in ["us.amazon.nova-lite-v1:0", "us.amazon.nova-pro-v1:0"]:
        try:
            response = client.invoke_model(
                modelId=model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps({
                    "messages": [
                        {
                            "role": "user",
                            "content": [{"text": "Merhaba, sen bir depo stok yönetim asistanısın. Kısaca kendini tanıt."}],
                        }
                    ],
                    "inferenceConfig": {"max_new_tokens": 200, "temperature": 0.7},
                }),
            )
            result = json.loads(response["body"].read())
            text = result.get("output", {}).get("message", {}).get("content", [{}])[0].get("text", "")
            print(f"✅ {model_id} çalışıyor")
            print(f"   Yanıt: {text[:150]}...")
        except Exception as e:
            print(f"❌ {model_id} hatası: {e}")


def test_inventory_monitor_agent():
    """Inventory Monitor Agent'ı gerçek Bedrock ile test eder."""
    print("\n--- Inventory Monitor Agent Testi ---")
    from src.agents.inventory_monitor import InventoryMonitorAgent
    from unittest.mock import MagicMock

    # Gerçek Bedrock client, mock DynamoDB/S3
    bedrock_client = boto3.client("bedrock-runtime", region_name=REGION)
    agent = InventoryMonitorAgent(
        region_name=REGION,
        bedrock_runtime_client=bedrock_client,
        dynamodb_resource=MagicMock(),
        s3_client=MagicMock(),
    )

    # Stok verisi ekle
    agent.update_stock("WH001", "SKU001", 5)
    agent.update_stock("WH001", "SKU002", 50)
    agent.update_stock("WH002", "SKU001", 200)
    agent.set_threshold("WH001", "SKU001", 20)

    # Kritik stok tespiti
    alerts = agent.detect_critical_stock(default_threshold=30)
    print(f"✅ Kritik stok tespiti: {len(alerts)} uyarı")
    for a in alerts:
        print(f"   ⚠️  {a.warehouse_id}/{a.sku}: stok={a.current_quantity}, eşik={a.threshold}, şiddet={a.severity.value}")

    # Nova ile trend analizi
    print("\n   Nova model ile stok trend analizi yapılıyor...")
    try:
        trend = agent.analyze_stock_trends("WH001", "SKU001")
        print(f"✅ Trend analizi tamamlandı")
        print(f"   Sonuç: {json.dumps(trend, ensure_ascii=False, indent=2)[:300]}")
    except Exception as e:
        print(f"❌ Trend analizi hatası: {e}")


def test_sales_predictor_agent():
    """Sales Predictor Agent'ı gerçek Bedrock ile test eder."""
    print("\n--- Sales Predictor Agent Testi ---")
    from src.agents.sales_predictor import SalesPredictorAgent
    from unittest.mock import MagicMock

    bedrock_client = boto3.client("bedrock-runtime", region_name=REGION)
    agent = SalesPredictorAgent(
        region_name=REGION,
        bedrock_runtime_client=bedrock_client,
        dynamodb_resource=MagicMock(),
        s3_client=MagicMock(),
    )

    # Veri ayarla
    agent.set_sales_history("WH001", "SKU001", [100, 120, 110, 130, 140, 150, 160, 170, 180, 190, 200, 210])
    agent.set_sales_history("WH002", "SKU001", [50, 60, 55, 70, 65, 80, 75, 90, 85, 100, 95, 110])
    agent.set_warehouse_region("WH001", "Marmara")
    agent.set_warehouse_region("WH002", "Karadeniz")
    agent.set_product_category("SKU001", "Elektronik")

    # Satış potansiyeli hesapla
    p1 = agent.calculate_sales_potential("WH001", "SKU001")
    p2 = agent.calculate_sales_potential("WH002", "SKU001")
    print(f"✅ Satış potansiyeli hesaplandı")
    print(f"   WH001 (Marmara): skor={p1.sales_potential_score}, günlük={p1.predicted_daily_sales}")
    print(f"   WH002 (Karadeniz): skor={p2.sales_potential_score}, günlük={p2.predicted_daily_sales}")

    # En iyi depo
    best = agent.get_best_warehouse("SKU001", ["WH001", "WH002"])
    print(f"   🏆 En iyi depo: {best.warehouse_id} (skor: {best.sales_potential_score})")

    # Nova ile tahmin
    print("\n   Nova model ile satış tahmini yapılıyor...")
    try:
        prediction = agent.predict_with_model("WH001", "SKU001")
        print(f"✅ Model tahmini tamamlandı")
        print(f"   Sonuç: {json.dumps(prediction, ensure_ascii=False, indent=2)[:300]}")
    except Exception as e:
        print(f"❌ Model tahmin hatası: {e}")


def test_transfer_coordinator_agent():
    """Transfer Coordinator Agent'ı test eder."""
    print("\n--- Transfer Coordinator Agent Testi ---")
    from src.agents.transfer_coordinator import TransferCoordinatorAgent
    from src.models.warehouse import ApprovalConfig, OperationMode
    from unittest.mock import MagicMock

    bedrock_client = boto3.client("bedrock-runtime", region_name=REGION)
    agent = TransferCoordinatorAgent(
        region_name=REGION,
        bedrock_runtime_client=bedrock_client,
        dynamodb_resource=MagicMock(),
        s3_client=MagicMock(),
    )

    # Stok ayarla
    agent.set_stock("WH001", "SKU001", 5)    # Düşük stok
    agent.set_stock("WH002", "SKU001", 200)   # Yüksek stok
    agent.set_stock("WH003", "SKU001", 150)   # Orta stok
    agent.set_product_price("SKU001", 100.0)

    print(f"   Başlangıç toplam stok: {agent.get_total_stock('SKU001')}")

    # Otomatik transfer
    result = agent.process("WH001", "SKU001", threshold=50)
    print(f"✅ Transfer sonucu: {result}")
    print(f"   Transfer sonrası toplam stok: {agent.get_total_stock('SKU001')}")

    # Onay mekanizması testi
    print("\n   İnsan onayı mekanizması testi...")
    agent.set_stock("WH004", "SKU002", 10)
    agent.set_stock("WH005", "SKU002", 500)
    agent.set_product_price("SKU002", 2000.0)
    config = ApprovalConfig(high_value_threshold=5000.0, mode=OperationMode.SUPERVISED)
    agent.set_approval_config(config)

    transfer = agent.execute_transfer("WH005", "WH004", "SKU002", 50, reason="yüksek değerli transfer")
    print(f"   Transfer durumu: {transfer.status.value}")
    print(f"   Onay bekleyenler: {len(agent.get_pending_approvals())}")

    # Onay ver
    completed = agent.approve_transfer(transfer.transfer_id)
    print(f"   Onay sonrası durum: {completed.status.value}")
    print(f"   WH005 stok: {agent.get_stock('WH005', 'SKU002')}, WH004 stok: {agent.get_stock('WH004', 'SKU002')}")

    # Nova ile karar
    print("\n   Nova model ile transfer kararı alınıyor...")
    try:
        decision = agent.decide_with_model(
            "WH001", "SKU001", 5, 50,
            [{"warehouse_id": "WH002", "quantity": 200}, {"warehouse_id": "WH003", "quantity": 150}]
        )
        print(f"✅ Model kararı: {json.dumps(decision, ensure_ascii=False, indent=2)[:300]}")
    except Exception as e:
        print(f"❌ Model karar hatası: {e}")


def test_full_workflow():
    """Tüm agentların birlikte çalıştığı end-to-end senaryo."""
    print("\n" + "=" * 60)
    print("--- FULL WORKFLOW: Tüm Agentlar Birlikte ---")
    print("=" * 60)

    from src.agents.inventory_monitor import InventoryMonitorAgent
    from src.agents.sales_predictor import SalesPredictorAgent
    from src.agents.stock_aging_analyzer import StockAgingAnalyzerAgent
    from src.agents.transfer_coordinator import TransferCoordinatorAgent
    from src.agents.communication import MessageBus, AgentMessage, MessageType
    from src.agents.stock_validator import StockValidator
    from unittest.mock import MagicMock
    import uuid

    mock_dynamo = MagicMock()
    mock_s3 = MagicMock()
    bedrock_client = boto3.client("bedrock-runtime", region_name=REGION)

    # 1. Agentları oluştur
    monitor = InventoryMonitorAgent(region_name=REGION, bedrock_runtime_client=bedrock_client, dynamodb_resource=mock_dynamo, s3_client=mock_s3)
    predictor = SalesPredictorAgent(region_name=REGION, bedrock_runtime_client=bedrock_client, dynamodb_resource=mock_dynamo, s3_client=mock_s3)
    aging = StockAgingAnalyzerAgent(region_name=REGION, bedrock_runtime_client=bedrock_client, dynamodb_resource=mock_dynamo, s3_client=mock_s3)
    coordinator = TransferCoordinatorAgent(region_name=REGION, bedrock_runtime_client=bedrock_client, dynamodb_resource=mock_dynamo, s3_client=mock_s3)
    validator = StockValidator()

    # 2. Veri ayarla
    warehouses = {
        "WH001": {"name": "İstanbul", "region": "Marmara"},
        "WH002": {"name": "Ankara", "region": "İç Anadolu"},
        "WH003": {"name": "İzmir", "region": "Ege"},
    }
    stock_data = {
        ("WH001", "SKU001"): 5,    # Kritik düşük
        ("WH001", "SKU002"): 100,
        ("WH002", "SKU001"): 200,
        ("WH002", "SKU002"): 50,
        ("WH003", "SKU001"): 150,
        ("WH003", "SKU002"): 30,   # Düşük
    }

    for (wh, sku), qty in stock_data.items():
        monitor.update_stock(wh, sku, qty)
        coordinator.set_stock(wh, sku, qty)

    for wh_id, info in warehouses.items():
        predictor.set_warehouse_region(wh_id, info["region"])

    predictor.set_product_category("SKU001", "Elektronik")
    predictor.set_product_category("SKU002", "Gıda")
    predictor.set_sales_history("WH001", "SKU001", [80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180, 190])
    predictor.set_sales_history("WH002", "SKU001", [40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95])
    predictor.set_sales_history("WH003", "SKU001", [60, 65, 70, 75, 80, 85, 90, 95, 100, 105, 110, 115])

    aging.set_product_category("SKU001", "Elektronik")
    aging.set_product_category("SKU002", "Gıda")
    aging.set_entry_date("WH001", "SKU001", "2025-10-01T00:00:00")
    aging.set_entry_date("WH002", "SKU001", "2026-01-15T00:00:00")
    aging.set_entry_date("WH003", "SKU002", "2025-12-01T00:00:00")

    # Snapshot al
    validator.take_snapshot(stock_data)
    for sku in ["SKU001", "SKU002"]:
        total = sum(qty for (_, s), qty in stock_data.items() if s == sku)
        validator.register_total_stock(sku, total)

    print("\n📊 Başlangıç Durumu:")
    for (wh, sku), qty in sorted(stock_data.items()):
        print(f"   {wh}/{sku}: {qty}")
    print(f"   Toplam SKU001: {coordinator.get_total_stock('SKU001')}")
    print(f"   Toplam SKU002: {coordinator.get_total_stock('SKU002')}")

    # 3. Inventory Monitor: Kritik stok tespiti
    print("\n🔍 Adım 1: Stok İzleme")
    alerts = monitor.detect_critical_stock(default_threshold=40)
    print(f"   {len(alerts)} kritik stok uyarısı:")
    for a in alerts:
        print(f"   ⚠️  {a.warehouse_id}/{a.sku}: {a.current_quantity} < {a.threshold} ({a.severity.value})")

    # 4. Aging Analyzer: Yaşlandırma analizi
    print("\n📅 Adım 2: Yaşlandırma Analizi")
    aging_report = aging.get_daily_aging_report(reference_date="2026-02-12T00:00:00")
    print(f"   Kritik yaşlanan ürün: {aging_report['critical_items_count']}")
    for item in aging_report.get("urgent_transfers_needed", []):
        print(f"   🕐 {item['warehouse_id']}/{item['sku']}: {item['days_in_warehouse']} gün (eşik: {item['aging_threshold_days']})")

    # 5. Sales Predictor: En iyi hedef depo
    print("\n📈 Adım 3: Satış Potansiyeli Analizi")
    for alert in alerts:
        if alert.sku == "SKU001":
            best = predictor.get_best_warehouse(alert.sku, ["WH001", "WH002", "WH003"])
            if best:
                print(f"   SKU001 için en iyi depo: {best.warehouse_id} (skor: {best.sales_potential_score})")

    # 6. Transfer Coordinator: Transfer yap
    print("\n🚚 Adım 4: Transfer İşlemleri")
    for alert in alerts:
        source = coordinator.select_source_warehouse(alert.sku, alert.warehouse_id, alert.threshold - alert.current_quantity)
        if source:
            deficit = alert.threshold - alert.current_quantity
            qty = coordinator.calculate_transfer_quantity(source, alert.warehouse_id, alert.sku, deficit)
            if qty > 0:
                transfer = coordinator.execute_transfer(source, alert.warehouse_id, alert.sku, qty, reason="auto_low_stock")
                print(f"   ✅ {source} -> {alert.warehouse_id}: {alert.sku} x{qty} ({transfer.status.value})")

                # Audit log
                validator.log_stock_change("transfer_out", source, alert.sku, stock_data.get((source, alert.sku), 0), coordinator.get_stock(source, alert.sku), "TransferCoordinator", transfer.transfer_id)
                validator.log_stock_change("transfer_in", alert.warehouse_id, alert.sku, stock_data.get((alert.warehouse_id, alert.sku), 0), coordinator.get_stock(alert.warehouse_id, alert.sku), "TransferCoordinator", transfer.transfer_id)

    # 7. Validasyon
    print("\n✅ Adım 5: Stok Tutarlılığı Doğrulama")
    current_stock = {k: coordinator.get_stock(k[0], k[1]) for k in stock_data}
    neg_check = validator.check_no_negative_stock(current_stock)
    print(f"   Negatif stok kontrolü: {'✅ Geçti' if neg_check.is_valid else '❌ Başarısız'}")

    for sku in ["SKU001", "SKU002"]:
        conservation = validator.verify_stock_conservation(sku, stock_data, current_stock)
        print(f"   Stok korunumu ({sku}): {'✅ Geçti' if conservation.is_valid else '❌ Başarısız'}")

    print(f"\n📊 Son Durum:")
    for (wh, sku) in sorted(stock_data.keys()):
        print(f"   {wh}/{sku}: {coordinator.get_stock(wh, sku)}")
    print(f"   Toplam SKU001: {coordinator.get_total_stock('SKU001')}")
    print(f"   Toplam SKU002: {coordinator.get_total_stock('SKU002')}")
    print(f"   Audit log kayıtları: {len(validator.get_audit_log())}")


if __name__ == "__main__":
    print("🏭 Multi-Agent Warehouse Stock Management - Demo")
    print("=" * 60)

    check_credentials()
    
    if test_bedrock_connection():
        test_nova_model_invoke()
        test_inventory_monitor_agent()
        test_sales_predictor_agent()
        test_transfer_coordinator_agent()
        test_full_workflow()
    
    print("\n" + "=" * 60)
    print("🎉 Demo tamamlandı!")

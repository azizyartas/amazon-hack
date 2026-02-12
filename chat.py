"""
Agentlarla interaktif sohbet arayüzü.

Kullanım:
    export AWS_DEFAULT_REGION="us-west-2"
    export AWS_ACCESS_KEY_ID="..."
    export AWS_SECRET_ACCESS_KEY="..."
    export AWS_SESSION_TOKEN="..."
    python chat.py
"""

import json
import os
import sys
from unittest.mock import MagicMock

import boto3

from src.agents.inventory_monitor import InventoryMonitorAgent
from src.agents.sales_predictor import SalesPredictorAgent
from src.agents.stock_aging_analyzer import StockAgingAnalyzerAgent
from src.agents.transfer_coordinator import TransferCoordinatorAgent
from src.agents.stock_validator import StockValidator
from src.models.warehouse import ApprovalConfig, OperationMode

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")


def setup_agents():
    """Tüm agentları gerçek Bedrock + simülasyon verisiyle başlatır."""
    bedrock = boto3.client("bedrock-runtime", region_name=REGION)
    mock_db = MagicMock()
    mock_s3 = MagicMock()

    monitor = InventoryMonitorAgent(region_name=REGION, bedrock_runtime_client=bedrock, dynamodb_resource=mock_db, s3_client=mock_s3)
    predictor = SalesPredictorAgent(region_name=REGION, bedrock_runtime_client=bedrock, dynamodb_resource=mock_db, s3_client=mock_s3)
    aging = StockAgingAnalyzerAgent(region_name=REGION, bedrock_runtime_client=bedrock, dynamodb_resource=mock_db, s3_client=mock_s3)
    coordinator = TransferCoordinatorAgent(region_name=REGION, bedrock_runtime_client=bedrock, dynamodb_resource=mock_db, s3_client=mock_s3)
    validator = StockValidator()

    # Simülasyon verisi yükle
    warehouses = {
        "WH001": {"name": "İstanbul Merkez", "region": "Marmara"},
        "WH002": {"name": "Ankara Depo", "region": "İç Anadolu"},
        "WH003": {"name": "İzmir Depo", "region": "Ege"},
        "WH004": {"name": "Antalya Depo", "region": "Akdeniz"},
        "WH005": {"name": "Bursa Depo", "region": "Marmara"},
        "WH006": {"name": "Trabzon Depo", "region": "Karadeniz"},
    }
    stock = {
        ("WH001", "SKU001"): 5,   ("WH001", "SKU002"): 120, ("WH001", "SKU003"): 8,
        ("WH002", "SKU001"): 200, ("WH002", "SKU002"): 15,  ("WH002", "SKU003"): 90,
        ("WH003", "SKU001"): 150, ("WH003", "SKU002"): 60,  ("WH003", "SKU003"): 45,
        ("WH004", "SKU001"): 80,  ("WH004", "SKU002"): 200, ("WH004", "SKU003"): 10,
        ("WH005", "SKU001"): 30,  ("WH005", "SKU002"): 40,  ("WH005", "SKU003"): 300,
        ("WH006", "SKU001"): 10,  ("WH006", "SKU002"): 25,  ("WH006", "SKU003"): 55,
    }
    categories = {"SKU001": "Elektronik", "SKU002": "Gıda", "SKU003": "Giyim"}
    prices = {"SKU001": 1500.0, "SKU002": 25.0, "SKU003": 200.0}
    sales = {
        ("WH001", "SKU001"): [80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180, 190],
        ("WH002", "SKU001"): [40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95],
        ("WH003", "SKU001"): [60, 65, 70, 75, 80, 85, 90, 95, 100, 105, 110, 115],
        ("WH001", "SKU002"): [200, 210, 220, 230, 240, 250, 260, 270, 280, 290, 300, 310],
        ("WH002", "SKU002"): [30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85],
        ("WH004", "SKU002"): [150, 160, 170, 180, 190, 200, 210, 220, 230, 240, 250, 260],
    }
    entry_dates = {
        ("WH001", "SKU001"): "2025-10-01T00:00:00",
        ("WH001", "SKU003"): "2025-08-15T00:00:00",
        ("WH002", "SKU002"): "2026-01-20T00:00:00",
        ("WH004", "SKU003"): "2025-06-01T00:00:00",
        ("WH006", "SKU001"): "2025-11-01T00:00:00",
    }

    for (wh, sku), qty in stock.items():
        monitor.update_stock(wh, sku, qty)
        coordinator.set_stock(wh, sku, qty)
    for wh_id, info in warehouses.items():
        predictor.set_warehouse_region(wh_id, info["region"])
    for sku, cat in categories.items():
        predictor.set_product_category(sku, cat)
        aging.set_product_category(sku, cat)
    for sku, price in prices.items():
        coordinator.set_product_price(sku, price)
    for (wh, sku), history in sales.items():
        predictor.set_sales_history(wh, sku, history)
    for (wh, sku), date in entry_dates.items():
        aging.set_entry_date(wh, sku, date)

    config = ApprovalConfig(high_value_threshold=10000.0, mode=OperationMode.SUPERVISED)
    coordinator.set_approval_config(config)

    return {
        "monitor": monitor,
        "predictor": predictor,
        "aging": aging,
        "coordinator": coordinator,
        "validator": validator,
        "warehouses": warehouses,
        "categories": categories,
        "bedrock": bedrock,
    }


SYSTEM_PROMPT = """Sen bir Çok-Agentlı Depo Stok Yönetim Sistemi'nin ana koordinatör agentısın.
Kullanıcıyla Türkçe konuş. Sana sorulan sorulara göre uygun agent'ı çağır ve sonuçları raporla.

Elindeki agentlar:
1. Inventory Monitor Agent - Stok seviyelerini izler, kritik stokları tespit eder
2. Sales Predictor Agent - Satış potansiyeli hesaplar, tahmin yapar
3. Stock Aging Analyzer Agent - Ürün yaşlandırmasını analiz eder
4. Transfer Coordinator Agent - Depolar arası transfer koordine eder

Mevcut depolar: WH001 (İstanbul), WH002 (Ankara), WH003 (İzmir), WH004 (Antalya), WH005 (Bursa), WH006 (Trabzon)
Mevcut SKU'lar: SKU001 (Elektronik), SKU002 (Gıda), SKU003 (Giyim)

Kullanıcının sorusuna göre hangi agent'ın ne yapması gerektiğini belirle ve sonuçları açıkla.
Kısa ve öz yanıtlar ver. Verileri tablo formatında göster.
Kullanıcı "kritik stokları göster" dediğinde SADECE kritik stok listesini göster, transfer önerisi ekleme. Transfer önerisi ancak kullanıcı açıkça istediğinde yapılmalı.

ÖNEMLİ KURALLAR:
1. Kullanıcı sadece "öner", "ne önerirsin", "önerebileceğin transferler" gibi sorular sorduğunda SADECE öneri yap, [EXECUTE_TRANSFER] komutu EKLEME.
2. Kullanıcı açıkça "transfer et", "uygula", "yap", "gerçekleştir", "onayla" gibi eylem kelimeleri kullandığında [EXECUTE_TRANSFER] komutlarını ekle.
3. Transfer önerirken kaynak depodaki stok miktarını MUTLAKA kontrol et. Kaynak depo transfer sonrası 40 birimin altına düşmemeli. Güvenli fazlalık = mevcut stok - 40. Sadece güvenli fazlalık kadar transfer öner.
4. Eğer hiçbir depodan tam miktar karşılanamıyorsa, mümkün olan max miktarı öner ve eksik kalan için "Dış tedarik gerekli: X adet" notu ekle.
5. Onay bekleyen transferleri onaylamak için [EXECUTE_TRANSFER] KULLANMA. Kullanıcıya "onayla <id>" komutunu kullanmasını söyle.
6. SADECE kritik stok uyarısı olan depo/SKU çiftleri için transfer öner. Stok seviyesi eşiğin üstünde olan depolara transfer önerme.
7. Kaynak depo seçerken satış potansiyelini dikkate al. Aynı SKU için birden fazla kaynak aday varsa, ürünün AZ satıldığı depodan transfer öncelikli olmalı. Örneğin İstanbul'da çok satılan bir ürün Bursa'da az satılıyorsa, Bursa'dan İstanbul'a transfer öncelikli.

Transfer komutu formatı (SADECE kullanıcı açıkça istediğinde):
[EXECUTE_TRANSFER: kaynak_depo hedef_depo sku miktar]"""


def build_context(agents: dict) -> str:
    """Mevcut sistem durumunu context olarak hazırlar."""
    monitor = agents["monitor"]
    coordinator = agents["coordinator"]
    predictor = agents["predictor"]

    lines = ["Mevcut Stok Durumu:"]
    for item in sorted(monitor.get_all_inventory(), key=lambda x: (x.warehouse_id, x.sku)):
        lines.append(f"  {item.warehouse_id}/{item.sku}: {item.quantity}")

    alerts = monitor.detect_critical_stock(default_threshold=40)
    if alerts:
        lines.append(f"\nKritik Stok Uyarıları ({len(alerts)} adet):")
        for a in alerts:
            lines.append(f"  ⚠️ {a.warehouse_id}/{a.sku}: {a.current_quantity} (eşik: {a.threshold}, şiddet: {a.severity.value})")

    # Satış potansiyeli bilgisi (AI'ın doğru kaynak depo seçmesi için)
    all_warehouses = list(agents["warehouses"].keys())
    all_skus = list(agents["categories"].keys())
    lines.append("\nSatış Potansiyeli (günlük tahmini satış):")
    for sku in sorted(all_skus):
        for wh_id in sorted(all_warehouses):
            p = predictor.calculate_sales_potential(wh_id, sku)
            if p.predicted_daily_sales > 0:
                lines.append(f"  {wh_id}/{sku}: günlük={p.predicted_daily_sales}, skor={p.sales_potential_score}")

    transfers = coordinator.get_all_transfers()
    if transfers:
        lines.append(f"\nSon Transferler ({len(transfers)} adet):")
        for t in transfers[-5:]:
            lines.append(f"  {t.source_warehouse_id} -> {t.target_warehouse_id}: {t.sku} x{t.quantity} ({t.status.value})")

    pending = coordinator.get_pending_approvals()
    if pending:
        lines.append(f"\nOnay Bekleyen Transferler ({len(pending)} adet):")
        for t in pending:
            lines.append(f"  [{t.transfer_id[:8]}] {t.source_warehouse_id} -> {t.target_warehouse_id}: {t.sku} x{t.quantity}")
    else:
        lines.append("\nOnay bekleyen transfer yok.")

    return "\n".join(lines)


def chat_with_orchestrator(user_message: str, agents: dict, history: list) -> str:
    """Kullanıcı mesajını orchestrator agent'a gönderir."""
    bedrock = agents["bedrock"]
    context = build_context(agents)

    # Önceki konuşma geçmişini ekle
    messages = []
    for msg in history[-6:]:  # Son 6 mesaj
        messages.append(msg)

    messages.append({
        "role": "user",
        "content": [{"text": f"{user_message}\n\n--- Sistem Durumu ---\n{context}"}],
    })

    try:
        response = bedrock.invoke_model(
            modelId="us.amazon.nova-pro-v1:0",
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "system": [{"text": SYSTEM_PROMPT}],
                "messages": messages,
                "inferenceConfig": {"max_new_tokens": 1500, "temperature": 0.7},
            }),
        )
        result = json.loads(response["body"].read())
        reply = result.get("output", {}).get("message", {}).get("content", [{}])[0].get("text", "")

        # AI yanıtından transfer komutlarını çıkar ve çalıştır
        reply, executed = execute_transfers_from_reply(reply, agents)
        return reply
    except Exception as e:
        return f"Hata: {e}"


def execute_transfers_from_reply(reply: str, agents: dict) -> tuple[str, list]:
    """AI yanıtındaki [EXECUTE_TRANSFER: ...] komutlarını parse edip gerçekten çalıştırır."""
    import re
    pattern = r'\[EXECUTE_TRANSFER:\s*(WH\d+)\s+(WH\d+)\s+(SKU\d+)\s+(\d+)\]'
    matches = re.findall(pattern, reply)

    if not matches:
        return reply, []

    # Komut satırlarını yanıttan temizle
    clean_reply = re.sub(r'\[EXECUTE_TRANSFER:.*?\]', '', reply).strip()
    # Boş satırları temizle
    clean_reply = re.sub(r'\n{3,}', '\n\n', clean_reply)

    SAFETY_THRESHOLD = 40  # Kaynak depo bu seviyenin altına düşmemeli

    executed = []
    transfer_results = []
    external_supply_needed = []
    actual_affected_warehouses = set()  # Gerçekten etkilenen depolar

    # Her SKU için satış potansiyel skorlarını hesapla (düşük satış = öncelikli kaynak)
    all_warehouses = list(agents["warehouses"].keys())
    sales_scores_cache: dict[str, dict[str, float]] = {}

    for src, tgt, sku, qty_str in matches:
        if sku not in sales_scores_cache:
            scores = {}
            for wh_id in all_warehouses:
                prediction = agents["predictor"].calculate_sales_potential(wh_id, sku)
                scores[wh_id] = prediction.sales_potential_score
            sales_scores_cache[sku] = scores

    for src, tgt, sku, qty_str in matches:
        qty = int(qty_str)
        sales_scores = sales_scores_cache.get(sku, {})

        # Güvenli transfer miktarını hesapla (kaynak depo eşik altına düşmesin)
        safe_qty = agents["coordinator"].get_safe_transfer_amount(src, sku, qty, SAFETY_THRESHOLD)

        if safe_qty == 0:
            # Bu kaynaktan hiç güvenli transfer yapılamaz, alternatif ara
            alt_src = agents["coordinator"].select_source_warehouse(sku, tgt, qty, SAFETY_THRESHOLD, sales_scores)
            if alt_src and alt_src != src:
                alt_safe_qty = agents["coordinator"].get_safe_transfer_amount(alt_src, sku, qty, SAFETY_THRESHOLD)
                if alt_safe_qty >= qty:
                    transfer_results.append(f"  🔄 {src} güvenli seviyede, alternatif {alt_src} kullanılıyor")
                    src = alt_src
                    safe_qty = qty
                elif alt_safe_qty > 0:
                    transfer_results.append(f"  🔄 {src} güvenli seviyede, alternatif {alt_src} kısmi transfer x{alt_safe_qty}")
                    src = alt_src
                    safe_qty = alt_safe_qty
                else:
                    external_supply_needed.append((tgt, sku, qty))
                    transfer_results.append(f"  ❌ {sku} x{qty} → {tgt}: Hiçbir depoda güvenli fazlalık yok")
                    continue
            else:
                external_supply_needed.append((tgt, sku, qty))
                transfer_results.append(f"  ❌ {sku} x{qty} → {tgt}: Hiçbir depoda güvenli fazlalık yok")
                continue
        elif safe_qty < qty:
            # Kısmi transfer + eksik kalan için dış tedarik
            remaining = qty - safe_qty
            transfer_results.append(f"  🔄 {src} → {tgt}: {sku} güvenli max x{safe_qty} (istenen: {qty})")
            external_supply_needed.append((tgt, sku, remaining))
            qty = safe_qty

        try:
            t = agents["coordinator"].execute_transfer(src, tgt, sku, qty, reason="ai_orchestrated")
            # Monitor'daki stokları da güncelle
            agents["monitor"].update_stock(src, sku, agents["coordinator"].get_stock(src, sku))
            agents["monitor"].update_stock(tgt, sku, agents["coordinator"].get_stock(tgt, sku))
            actual_affected_warehouses.add(src)
            actual_affected_warehouses.add(tgt)
            status_icon = "✅" if t.status.value == "completed" else "⏳" if t.status.value == "awaiting_approval" else "❌"
            transfer_results.append(f"  {status_icon} {src} → {tgt}: {sku} x{qty} ({t.status.value})")
            executed.append(t)
        except Exception as e:
            transfer_results.append(f"  ❌ {src} → {tgt}: {sku} x{qty} — Hata: {e}")

    if transfer_results:
        clean_reply += "\n\n🚚 **Gerçekleştirilen Transferler:**\n" + "\n".join(transfer_results)

        # Güncel stok özeti ekle
        clean_reply += "\n\n📦 **Güncel Stok (etkilenen depolar):**"
        for wh in sorted(actual_affected_warehouses):
            items = agents["monitor"].get_warehouse_inventory(wh)
            for item in sorted(items, key=lambda x: x.sku):
                clean_reply += f"\n  {wh}/{item.sku}: {item.quantity}"

    if external_supply_needed:
        clean_reply += "\n\n📋 **Dış Tedarik Gerekli:**"
        for tgt, sku, remaining in external_supply_needed:
            clean_reply += f"\n  📦 {tgt}/{sku}: {remaining} adet dışarıdan temin edilmeli"

    return clean_reply, executed


def handle_command(cmd: str, agents: dict) -> str:
    """Doğrudan agent komutlarını çalıştırır."""
    parts = cmd.strip().split()
    if not parts:
        return ""

    action = parts[0].lower()

    if action == "stok":
        monitor = agents["monitor"]
        lines = ["📦 Stok Durumu:"]
        for item in sorted(monitor.get_all_inventory(), key=lambda x: (x.warehouse_id, x.sku)):
            lines.append(f"  {item.warehouse_id}/{item.sku}: {item.quantity}")
        return "\n".join(lines)

    elif action == "uyarılar" or action == "uyarilar":
        alerts = agents["monitor"].detect_critical_stock(default_threshold=40)
        if not alerts:
            return "✅ Kritik stok uyarısı yok."
        lines = [f"⚠️ {len(alerts)} Kritik Stok Uyarısı:"]
        for a in alerts:
            lines.append(f"  {a.warehouse_id}/{a.sku}: {a.current_quantity} < {a.threshold} ({a.severity.value})")
        return "\n".join(lines)

    elif action == "yaşlandırma" or action == "yaslandirma":
        report = agents["aging"].get_daily_aging_report(reference_date="2026-02-12T00:00:00")
        lines = [f"📅 Yaşlandırma Raporu:"]
        lines.append(f"  Takip edilen: {report['total_tracked_items']}")
        lines.append(f"  Kritik: {report['critical_items_count']}")
        for item in report.get("urgent_transfers_needed", []):
            lines.append(f"  🕐 {item['warehouse_id']}/{item['sku']}: {item['days_in_warehouse']} gün (eşik: {item['aging_threshold_days']})")
        return "\n".join(lines)

    elif action == "transfer" and len(parts) >= 5:
        # transfer WH002 WH001 SKU001 30
        src, tgt, sku, qty = parts[1], parts[2], parts[3], int(parts[4])
        try:
            t = agents["coordinator"].execute_transfer(src, tgt, sku, qty, reason="manual")
            agents["monitor"].update_stock(src, sku, agents["coordinator"].get_stock(src, sku))
            agents["monitor"].update_stock(tgt, sku, agents["coordinator"].get_stock(tgt, sku))
            return f"✅ Transfer: {src} -> {tgt}: {sku} x{qty} ({t.status.value})"
        except Exception as e:
            return f"❌ Transfer hatası: {e}"

    elif action == "potansiyel" and len(parts) >= 2:
        sku = parts[1]
        wh_ids = list(agents["warehouses"].keys())
        ranked = agents["predictor"].rank_warehouses_by_potential(sku, wh_ids)
        lines = [f"📈 {sku} Satış Potansiyeli:"]
        for p in ranked:
            name = agents["warehouses"].get(p.warehouse_id, {}).get("name", "?")
            lines.append(f"  {p.warehouse_id} ({name}): skor={p.sales_potential_score}, günlük={p.predicted_daily_sales}")
        return "\n".join(lines)

    elif action == "onay":
        pending = agents["coordinator"].get_pending_approvals()
        if not pending:
            return "✅ Onay bekleyen transfer yok."
        lines = [f"⏳ {len(pending)} Onay Bekleyen Transfer:"]
        for t in pending:
            lines.append(f"  [{t.transfer_id[:8]}] {t.source_warehouse_id} -> {t.target_warehouse_id}: {t.sku} x{t.quantity}")
        lines.append("\nOnaylamak için: onayla <transfer_id_ilk_8_karakter>")
        return "\n".join(lines)

    elif action == "onayla" and len(parts) >= 2:
        tid_prefix = parts[1]
        pending = agents["coordinator"].get_pending_approvals()
        match = [t for t in pending if t.transfer_id.startswith(tid_prefix)]
        if not match:
            return f"❌ Transfer bulunamadı: {tid_prefix}"
        try:
            t = agents["coordinator"].approve_transfer(match[0].transfer_id)
            agents["monitor"].update_stock(t.source_warehouse_id, t.sku, agents["coordinator"].get_stock(t.source_warehouse_id, t.sku))
            agents["monitor"].update_stock(t.target_warehouse_id, t.sku, agents["coordinator"].get_stock(t.target_warehouse_id, t.sku))
            return f"✅ Onaylandı: {t.source_warehouse_id} -> {t.target_warehouse_id}: {t.sku} x{t.quantity}"
        except Exception as e:
            return f"❌ Onay hatası: {e}"

    return None  # Komut değil, AI'a gönder


HELP_TEXT = """
╔══════════════════════════════════════════════════════════╗
║  🏭 Depo Stok Yönetim Sistemi - Komutlar               ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  Hızlı Komutlar:                                         ║
║    stok              - Tüm stok durumunu göster          ║
║    uyarılar          - Kritik stok uyarılarını göster    ║
║    yaşlandırma       - Yaşlandırma raporunu göster       ║
║    potansiyel SKU001 - SKU satış potansiyelini göster    ║
║    onay              - Onay bekleyen transferleri göster  ║
║    onayla <id>       - Bir transferi onayla              ║
║    transfer WH002 WH001 SKU001 30 - Manuel transfer      ║
║                                                          ║
║  Serbest Sohbet:                                         ║
║    Herhangi bir soruyu Türkçe yaz, AI agent yanıtlar.    ║
║    Örnek: "WH001'deki stok durumu nasıl?"                ║
║    Örnek: "SKU001 için en iyi depo hangisi?"             ║
║    Örnek: "Yaşlanan ürünler için ne önerirsin?"          ║
║                                                          ║
║  yardım / help  - Bu menüyü göster                       ║
║  çıkış / exit   - Çıkış                                  ║
╚══════════════════════════════════════════════════════════╝
"""


def main():
    print("🏭 Depo Stok Yönetim Sistemi - İnteraktif Chat")
    print("=" * 58)

    # Credential kontrolü
    if not os.environ.get("AWS_ACCESS_KEY_ID"):
        print("❌ AWS credential'ları ayarlanmamış.")
        print("Önce creds.txt'deki değerleri export et:")
        print('  export AWS_DEFAULT_REGION="us-west-2"')
        print('  export AWS_ACCESS_KEY_ID="..."')
        print('  export AWS_SECRET_ACCESS_KEY="..."')
        print('  export AWS_SESSION_TOKEN="..."')
        sys.exit(1)

    print("⏳ Agentlar başlatılıyor...")
    agents = setup_agents()
    print("✅ Agentlar hazır!")
    print(HELP_TEXT)

    history = []

    while True:
        try:
            user_input = input("\n🧑 Sen: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Görüşürüz!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("çıkış", "cikis", "exit", "quit", "q"):
            print("👋 Görüşürüz!")
            break

        if user_input.lower() in ("yardım", "yardim", "help", "h"):
            print(HELP_TEXT)
            continue

        # Önce hızlı komut mu kontrol et
        cmd_result = handle_command(user_input, agents)
        if cmd_result is not None:
            print(f"\n🤖 Agent: {cmd_result}")
            continue

        # AI orchestrator'a gönder
        print("🤖 Agent: düşünüyorum...")
        reply = chat_with_orchestrator(user_input, agents, history)
        print(f"\n🤖 Agent: {reply}")

        # Geçmişe ekle
        history.append({"role": "user", "content": [{"text": user_input}]})
        history.append({"role": "assistant", "content": [{"text": reply}]})


if __name__ == "__main__":
    main()

"""
AgentCore Runtime Entrypoint - Depo Stok Yonetim Sistemi.

Mevcut multi-agent orchestrator mantigi BedrockAgentCoreApp ile sarmalanmistir.
MCP server'lar yerine dogrudan DynamoDB/S3 erisimi kullanilir (AgentCore Runtime'da
subprocess MCP server calistirmak mumkun degildir).

Deploy:
    agentcore configure -e agentcore_app.py -r us-west-2
    agentcore deploy
"""

import json
import os
import re
import logging
import uuid
from collections import defaultdict
from decimal import Decimal
from datetime import datetime

import env_loader
import boto3
from boto3.dynamodb.conditions import Key

from bedrock_agentcore import BedrockAgentCoreApp

from src.agents.inventory_monitor import InventoryMonitorAgent
from src.agents.sales_predictor import SalesPredictorAgent
from src.agents.stock_aging_analyzer import StockAgingAnalyzerAgent
from src.agents.transfer_coordinator import TransferCoordinatorAgent
from src.agents.stock_validator import StockValidator
from src.models.warehouse import ApprovalConfig, OperationMode

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("agentcore_app")

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")

app = BedrockAgentCoreApp()

# Global agent state - ilk invoke'da lazy init edilir
_agents = None


def _decimal_to_native(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj == int(obj) else float(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_native(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_native(i) for i in obj]
    return obj


# ============================================================
# Dogrudan DynamoDB/S3 veri yukleme (MCP yerine)
# ============================================================

def load_warehouses_direct(dynamodb) -> dict:
    table = dynamodb.Table("Warehouses")
    resp = table.scan()
    warehouses = {}
    for item in resp.get("Items", []):
        item = _decimal_to_native(item)
        wid = item["warehouse_id"]
        warehouses[wid] = {
            "name": item.get("name", wid),
            "region": item.get("region", ""),
            "capacity": item.get("capacity", 0),
            "is_trade_hub": item.get("is_trade_hub", False),
        }
    logger.info("%d depo yuklendi", len(warehouses))
    return warehouses


def load_products_direct(dynamodb) -> tuple:
    categories_list = [
        "Elektronik", "Giyim", "Gıda", "Mobilya", "Kitap",
        "Oyuncak", "Spor Malzemeleri", "Ev Aletleri", "Kozmetik", "Otomotiv",
    ]
    categories = {}
    prices = {}
    aging_thresholds = {}
    table = dynamodb.Table("Products")
    for cat in categories_list:
        resp = table.query(
            IndexName="CategoryIndex",
            KeyConditionExpression=Key("category").eq(cat),
        )
        for item in resp.get("Items", []):
            item = _decimal_to_native(item)
            sku = item["sku"]
            categories[sku] = item.get("category", "")
            prices[sku] = item.get("price", 0.0)
            aging_thresholds[sku] = item.get("aging_threshold_days", 180)
    logger.info("%d urun yuklendi", len(categories))
    return categories, prices, aging_thresholds


def load_inventory_direct(dynamodb, warehouse_ids: list) -> tuple:
    stock = {}
    entry_dates = {}
    thresholds = {}
    table = dynamodb.Table("Inventory")
    for wid in warehouse_ids:
        resp = table.query(KeyConditionExpression=Key("warehouse_id").eq(wid))
        for item in resp.get("Items", []):
            item = _decimal_to_native(item)
            sku = item["sku"]
            stock[(wid, sku)] = item.get("quantity", 0)
            if item.get("received_date"):
                entry_dates[(wid, sku)] = item["received_date"]
            if item.get("min_threshold"):
                thresholds[(wid, sku)] = item["min_threshold"]
    logger.info("%d stok kaydi yuklendi", len(stock))
    return stock, entry_dates, thresholds


def load_sales_direct(dynamodb, warehouse_ids: list) -> dict:
    sales = defaultdict(lambda: defaultdict(float))
    table = dynamodb.Table("SalesHistory")
    for wid in warehouse_ids:
        resp = table.query(
            KeyConditionExpression=Key("warehouse_id").eq(wid),
            Limit=365,
            ScanIndexForward=False,
        )
        for item in resp.get("Items", []):
            item = _decimal_to_native(item)
            sku = item.get("sku", "")
            qty = item.get("quantity_sold", 0)
            date_str = item.get("date", "")
            if date_str and sku:
                month_key = date_str[:7]
                sales[(wid, sku)][month_key] += qty
    result = {}
    for (wid, sku), monthly in sales.items():
        sorted_months = sorted(monthly.keys())[-12:]
        result[(wid, sku)] = [monthly[m] for m in sorted_months]
    logger.info("%d depo-SKU satis gecmisi yuklendi", len(result))
    return result


# ============================================================
# Agent setup - dogrudan AWS erisimi ile
# ============================================================

def init_agents():
    """Tum agentlari DynamoDB'den yuklenen veriyle baslatir. Lazy init."""
    global _agents
    if _agents is not None:
        return _agents

    logger.info("Agentlar baslatiliyor (region=%s)...", REGION)
    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    bedrock = boto3.client("bedrock-runtime", region_name=REGION)
    s3 = boto3.client("s3", region_name=REGION)

    warehouses = load_warehouses_direct(dynamodb)
    categories, prices, aging_thresholds = load_products_direct(dynamodb)
    warehouse_ids = list(warehouses.keys())
    skus = list(categories.keys())
    stock, entry_dates, inv_thresholds = load_inventory_direct(dynamodb, warehouse_ids)
    sales = load_sales_direct(dynamodb, warehouse_ids)

    monitor = InventoryMonitorAgent(
        region_name=REGION, bedrock_runtime_client=bedrock,
        dynamodb_resource=dynamodb, s3_client=s3,
    )
    predictor = SalesPredictorAgent(
        region_name=REGION, bedrock_runtime_client=bedrock,
        dynamodb_resource=dynamodb, s3_client=s3,
    )
    aging = StockAgingAnalyzerAgent(
        region_name=REGION, bedrock_runtime_client=bedrock,
        dynamodb_resource=dynamodb, s3_client=s3,
    )
    coordinator = TransferCoordinatorAgent(
        region_name=REGION, bedrock_runtime_client=bedrock,
        dynamodb_resource=dynamodb, s3_client=s3,
    )
    validator = StockValidator()

    for (wh, sku), qty in stock.items():
        monitor.update_stock(wh, sku, qty)
        coordinator.set_stock(wh, sku, qty)
    for (wh, sku), threshold in inv_thresholds.items():
        monitor.set_threshold(wh, sku, threshold)
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

    _agents = {
        "monitor": monitor,
        "predictor": predictor,
        "aging": aging,
        "coordinator": coordinator,
        "validator": validator,
        "warehouses": warehouses,
        "categories": categories,
        "bedrock": bedrock,
        "dynamodb": dynamodb,
        "s3": s3,
    }
    logger.info(
        "Agentlar hazir: %d depo, %d SKU, %d stok kaydi",
        len(warehouses), len(skus), len(stock),
    )
    return _agents


# ============================================================
# Orchestrator - Bedrock Nova ile konusma
# ============================================================

SYSTEM_PROMPT = """Sen bir Cok-Agentli Depo Stok Yonetim Sistemi'nin ana koordinator agentisin.
Kullaniciyla Turkce konus. Sana sorulan sorulara gore uygun agent'i cagir ve sonuclari raporla.

Elindeki agentlar:
1. Inventory Monitor Agent - Stok seviyelerini izler, kritik stoklari tespit eder
2. Sales Predictor Agent - Satis potansiyeli hesaplar, tahmin yapar
3. Stock Aging Analyzer Agent - Urun yaslandirmasini analiz eder
4. Transfer Coordinator Agent - Depolar arasi transfer koordine eder

Kullanicinin sorusuna gore hangi agent'in ne yapmasi gerektigini belirle ve sonuclari acikla.
Kisa ve oz yanitlar ver. Verileri tablo formatinda goster.
Kullanici "kritik stoklari goster" dediginde SADECE kritik stok listesini goster, transfer onerisi ekleme.
Transfer onerisi ancak kullanici acikca istediginde yapilmali.

ONEMLI KURALLAR:
1. Kullanici sadece "oner" gibi sorular sordugunda SADECE oneri yap, [EXECUTE_TRANSFER] komutu EKLEME.
2. Kullanici acikca "transfer et", "uygula", "yap" gibi eylem kelimeleri kullandiginda [EXECUTE_TRANSFER] komutlarini ekle.
3. Transfer onerirken kaynak depodaki stok miktarini MUTLAKA kontrol et.

Transfer komutu formati (SADECE kullanici acikca istediginde):
[EXECUTE_TRANSFER: kaynak_depo hedef_depo sku miktar]"""


def build_context(agents):
    monitor = agents["monitor"]
    coordinator = agents["coordinator"]
    lines = ["Mevcut Stok Durumu (ozet):"]
    alerts = monitor.detect_critical_stock(default_threshold=40)
    if alerts:
        lines.append(f"\nKritik Stok Uyarilari ({len(alerts)} adet):")
        for a in sorted(alerts, key=lambda x: x.current_quantity):
            lines.append(
                f"  {a.warehouse_id}/{a.sku}: {a.current_quantity} "
                f"(esik: {a.threshold}, siddet: {a.severity.value})"
            )
    else:
        lines.append("  Kritik stok uyarisi yok.")
    transfers = coordinator.get_all_transfers()
    if transfers:
        lines.append(f"\nSon Transferler ({len(transfers)} adet):")
        for t in transfers[-5:]:
            lines.append(
                f"  {t.source_warehouse_id} -> {t.target_warehouse_id}: "
                f"{t.sku} x{t.quantity} ({t.status.value})"
            )
    pending = coordinator.get_pending_approvals()
    if pending:
        lines.append(f"\nOnay Bekleyen Transferler ({len(pending)} adet):")
        for t in pending:
            lines.append(
                f"  [{t.transfer_id[:8]}] {t.source_warehouse_id} -> "
                f"{t.target_warehouse_id}: {t.sku} x{t.quantity}"
            )
    return "\n".join(lines)


def execute_transfers_from_reply(reply: str, agents: dict) -> tuple:
    """AI yanitindaki [EXECUTE_TRANSFER: ...] komutlarini parse edip calistirir."""
    pattern = r'\[EXECUTE_TRANSFER:\s*(WH\d+)\s+(WH\d+)\s+(SKU\d+)\s+(\d+)\]'
    matches = re.findall(pattern, reply)
    if not matches:
        return reply, []

    clean_reply = re.sub(r'\[EXECUTE_TRANSFER:.*?\]', '', reply).strip()
    clean_reply = re.sub(r'\n{3,}', '\n\n', clean_reply)

    SAFETY_THRESHOLD = 40
    executed = []
    transfer_results = []

    for src, tgt, sku, qty_str in matches:
        qty = int(qty_str)
        safe_qty = agents["coordinator"].get_safe_transfer_amount(src, sku, qty, SAFETY_THRESHOLD)
        if safe_qty == 0:
            transfer_results.append(f"  X {sku} x{qty} -> {tgt}: Kaynak depoda guvenli fazlalik yok")
            continue
        if safe_qty < qty:
            transfer_results.append(f"  ~ {src} -> {tgt}: {sku} kismi x{safe_qty} (istenen: {qty})")
            qty = safe_qty
        try:
            t = agents["coordinator"].execute_transfer(src, tgt, sku, qty, reason="ai_orchestrated")
            agents["monitor"].update_stock(src, sku, agents["coordinator"].get_stock(src, sku))
            agents["monitor"].update_stock(tgt, sku, agents["coordinator"].get_stock(tgt, sku))

            # DynamoDB'ye atomik transfer yaz (completed ise)
            if t.status.value == "completed":
                _write_transfer_to_db(agents, src, tgt, sku, qty)

            status_icon = "OK" if t.status.value == "completed" else "PENDING"
            transfer_results.append(
                f"  {status_icon} {src} -> {tgt}: {sku} x{qty} ({t.status.value})"
            )
            executed.append(t)
        except Exception as e:
            transfer_results.append(f"  FAIL {src} -> {tgt}: {sku} x{qty} - {e}")

    if transfer_results:
        clean_reply += "\n\nGerceklestirilen Transferler:\n" + "\n".join(transfer_results)
    return clean_reply, executed


def _write_transfer_to_db(agents, src, tgt, sku, qty):
    """Transfer sonucunu DynamoDB'ye yazar."""
    try:
        dynamodb_client = boto3.client("dynamodb", region_name=REGION)
        ts = datetime.utcnow().isoformat() + "Z"
        transfer_id = f"TRF-{uuid.uuid4().hex[:8].upper()}"
        dynamodb_client.transact_write_items(TransactItems=[
            {"Update": {
                "TableName": "Inventory",
                "Key": {"warehouse_id": {"S": src}, "sku": {"S": sku}},
                "UpdateExpression": "SET quantity = quantity - :qty, last_updated = :ts",
                "ConditionExpression": "quantity >= :qty",
                "ExpressionAttributeValues": {":qty": {"N": str(qty)}, ":ts": {"S": ts}},
            }},
            {"Update": {
                "TableName": "Inventory",
                "Key": {"warehouse_id": {"S": tgt}, "sku": {"S": sku}},
                "UpdateExpression": "SET quantity = quantity + :qty, last_updated = :ts",
                "ExpressionAttributeValues": {":qty": {"N": str(qty)}, ":ts": {"S": ts}},
            }},
            {"Put": {
                "TableName": "Transfers",
                "Item": {
                    "transfer_id": {"S": transfer_id},
                    "source_warehouse": {"S": src},
                    "target_warehouse": {"S": tgt},
                    "sku": {"S": sku},
                    "quantity": {"N": str(qty)},
                    "status": {"S": "completed"},
                    "reason": {"S": "ai_orchestrated"},
                    "created_at": {"S": ts},
                    "completed_at": {"S": ts},
                    "initiated_by": {"S": "agentcore_orchestrator"},
                },
            }},
        ])
    except Exception as e:
        logger.error("DynamoDB transfer yazma hatasi: %s", e)


# ============================================================
# AgentCore Entrypoint
# ============================================================

@app.entrypoint
def invoke(payload):
    """
    AgentCore Runtime tarafindan cagrilan ana endpoint.

    Beklenen payload:
        {"prompt": "kritik stoklari goster"}

    Donus:
        {"result": "...", "session_id": "..."}
    """
    agents = init_agents()
    user_message = payload.get("prompt", "Merhaba, nasil yardimci olabilirim?")
    session_id = payload.get("session_id", str(uuid.uuid4()))

    # Conversation history (session bazli - basit in-memory)
    history = payload.get("history", [])

    context = build_context(agents)
    bedrock = agents["bedrock"]

    messages = []
    for msg in history[-6:]:
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
        reply = (
            result.get("output", {})
            .get("message", {})
            .get("content", [{}])[0]
            .get("text", "")
        )
        reply, executed = execute_transfers_from_reply(reply, agents)

        # Agent kararlarini logla
        if executed:
            for t in executed:
                try:
                    table = agents["dynamodb"].Table("AgentDecisions")
                    table.put_item(Item={
                        "decision_id": f"DEC-{uuid.uuid4().hex[:8].upper()}",
                        "agent_name": "orchestrator",
                        "decision_type": "ai_transfer",
                        "input_data": {
                            "source": t.source_warehouse_id,
                            "target": t.target_warehouse_id,
                            "sku": t.sku,
                            "quantity": t.quantity,
                        },
                        "output_data": {
                            "status": t.status.value,
                            "transfer_id": t.transfer_id,
                        },
                        "reasoning": "AgentCore orchestrator tarafindan baslatilan transfer",
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                    })
                except Exception as e:
                    logger.warning("Karar loglama hatasi: %s", e)

        return {
            "result": reply,
            "session_id": session_id,
            "transfers_executed": len(executed),
        }

    except Exception as e:
        logger.error("Orchestrator hatasi: %s", e)
        return {"result": f"Hata: {e}", "session_id": session_id, "error": True}


if __name__ == "__main__":
    app.run()

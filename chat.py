"""
Agentlarla interaktif sohbet arayuzu - MCP Server entegrasyonlu.

MCP Server'lar subprocess olarak baslatilir, agent islemleri MCP uzerinden yapilir.
Kullanim:
    python chat.py
"""

import json
import os
import sys
import re
import asyncio
import logging
from collections import defaultdict
from decimal import Decimal
from contextlib import AsyncExitStack

import env_loader
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import boto3
from boto3.dynamodb.conditions import Key
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

from src.agents.inventory_monitor import InventoryMonitorAgent
from src.agents.sales_predictor import SalesPredictorAgent
from src.agents.stock_aging_analyzer import StockAgingAnalyzerAgent
from src.agents.transfer_coordinator import TransferCoordinatorAgent
from src.agents.stock_validator import StockValidator
from src.models.warehouse import ApprovalConfig, OperationMode

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("chat")
# MCP log'larini biraz kisalim
logging.getLogger("mcp").setLevel(logging.WARNING)


def _decimal_to_native(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj == int(obj) else float(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_native(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_native(i) for i in obj]
    return obj


# ============================================================
# MCP Client Manager - 3 MCP server'i yonetir
# ============================================================

class MCPManager:
    """3 custom MCP server'i subprocess olarak baslatir ve tool call yapar."""

    def __init__(self):
        self._sessions: dict[str, ClientSession] = {}
        self._tools: dict[str, dict] = {}  # tool_name -> {server, schema}
        self._exit_stack = AsyncExitStack()

    async def start(self):
        """Tum MCP server'lari baslat."""
        servers = {
            "warehouse-data": "mcp_servers/warehouse_data_server.py",
            "analytics": "mcp_servers/analytics_server.py",
            "transfer-ops": "mcp_servers/transfer_ops_server.py",
        }
        for name, script in servers.items():
            try:
                params = StdioServerParameters(
                    command="python",
                    args=[script],
                    env={
                        **os.environ,
                        "AWS_CA_BUNDLE": "",
                        "CURL_CA_BUNDLE": "",
                        "AWS_DEFAULT_REGION": REGION,
                    },
                )
                read, write = await self._exit_stack.enter_async_context(stdio_client(params))
                session = await self._exit_stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                self._sessions[name] = session

                # Tool'lari kaydet
                tools_resp = await session.list_tools()
                for tool in tools_resp.tools:
                    self._tools[tool.name] = {"server": name, "schema": tool.inputSchema, "description": tool.description}

                logger.info("MCP server baslatildi: %s (%d tool)", name, len(tools_resp.tools))
            except Exception as e:
                logger.error("MCP server baslatilamadi [%s]: %s", name, e)

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Bir MCP tool'u cagir."""
        tool_info = self._tools.get(tool_name)
        if not tool_info:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

        session = self._sessions.get(tool_info["server"])
        if not session:
            return {"success": False, "error": f"Server not connected: {tool_info['server']}"}

        try:
            logger.info("MCP call: %s.%s(%s)", tool_info["server"], tool_name, json.dumps(arguments, ensure_ascii=False)[:200])
            result = await session.call_tool(tool_name, arguments)
            # Parse text content
            for content in result.content:
                if hasattr(content, "text"):
                    data = json.loads(content.text)
                    logger.info("MCP result: %s -> %s", tool_name, "OK" if data.get("success", True) else data.get("error", "?"))
                    return data
            return {"success": False, "error": "No text content in response"}
        except Exception as e:
            logger.error("MCP call error [%s]: %s", tool_name, e)
            return {"success": False, "error": str(e)}

    def list_tools(self) -> dict:
        """Tum tool'lari listele."""
        return self._tools

    async def stop(self):
        """Tum server'lari kapat."""
        try:
            await self._exit_stack.aclose()
        except (asyncio.CancelledError, Exception) as e:
            logger.debug("MCP shutdown (beklenen): %s", e)


# ============================================================
# MCP uzerinden veri yukleme (agent'lara veri saglamak icin)
# ============================================================

async def load_warehouses_mcp(mcp: MCPManager) -> dict:
    result = await mcp.call_tool("list_warehouses", {})
    warehouses = {}
    if result.get("success"):
        for item in result["data"]:
            wid = item["warehouse_id"]
            warehouses[wid] = {
                "name": item.get("name", wid),
                "region": item.get("region", ""),
                "capacity": item.get("capacity", 0),
                "is_trade_hub": item.get("is_trade_hub", False),
            }
    print(f"  {len(warehouses)} depo yuklendi (MCP)")
    return warehouses


async def load_products_mcp(mcp: MCPManager) -> tuple:
    """Products - kategori bazli MCP call."""
    categories_list = ["Elektronik", "Giyim", "Gıda", "Mobilya", "Kitap",
                       "Oyuncak", "Spor Malzemeleri", "Ev Aletleri", "Kozmetik", "Otomotiv"]
    categories = {}
    prices = {}
    aging_thresholds = {}
    for cat in categories_list:
        result = await mcp.call_tool("list_products_by_category", {"category": cat})
        if result.get("success"):
            for item in result["data"]:
                sku = item["sku"]
                categories[sku] = item.get("category", "")
                prices[sku] = item.get("price", 0.0)
                aging_thresholds[sku] = item.get("aging_threshold_days", 180)
    print(f"  {len(categories)} urun yuklendi (MCP)")
    return categories, prices, aging_thresholds


async def load_inventory_mcp(mcp: MCPManager, warehouse_ids: list) -> tuple:
    stock = {}
    entry_dates = {}
    thresholds = {}
    for wid in warehouse_ids:
        result = await mcp.call_tool("get_warehouse_inventory", {"warehouse_id": wid})
        if result.get("success"):
            for item in result["data"]:
                sku = item["sku"]
                stock[(wid, sku)] = item.get("quantity", 0)
                if item.get("received_date"):
                    entry_dates[(wid, sku)] = item["received_date"]
                if item.get("min_threshold"):
                    thresholds[(wid, sku)] = item["min_threshold"]
    print(f"  {len(stock)} stok kaydi yuklendi (MCP)")
    return stock, entry_dates, thresholds


async def load_sales_mcp(mcp: MCPManager, warehouse_ids: list, skus: list) -> dict:
    """Satis gecmisi - MCP analytics server uzerinden."""
    sales = defaultdict(lambda: defaultdict(float))
    # Her SKU icin satis gecmisi cek (ilk 10 SKU ornegi, tam liste cok buyuk)
    dynamodb = boto3.resource("dynamodb", region_name=REGION, verify=False)
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
    print(f"  {len(result)} depo-SKU satis gecmisi yuklendi")
    return result


# ============================================================
# Agent setup - MCP uzerinden veri yukleyerek
# ============================================================

async def setup_agents(mcp: MCPManager):
    """Tum agentlari MCP uzerinden yuklenen veriyle baslatir."""
    print("⏳ AWS'ye baglaniliyor...")
    dynamodb = boto3.resource("dynamodb", region_name=REGION, verify=False)
    bedrock = boto3.client("bedrock-runtime", region_name=REGION, verify=False)
    s3 = boto3.client("s3", region_name=REGION, verify=False)

    print("📦 Veriler MCP uzerinden yukleniyor...")
    warehouses = await load_warehouses_mcp(mcp)
    categories, prices, aging_thresholds = await load_products_mcp(mcp)
    warehouse_ids = list(warehouses.keys())
    skus = list(categories.keys())
    stock, entry_dates, inv_thresholds = await load_inventory_mcp(mcp, warehouse_ids)
    sales = await load_sales_mcp(mcp, warehouse_ids, skus)

    print("🤖 Agentlar baslatiliyor...")
    monitor = InventoryMonitorAgent(region_name=REGION, bedrock_runtime_client=bedrock, dynamodb_resource=dynamodb, s3_client=s3)
    predictor = SalesPredictorAgent(region_name=REGION, bedrock_runtime_client=bedrock, dynamodb_resource=dynamodb, s3_client=s3)
    aging = StockAgingAnalyzerAgent(region_name=REGION, bedrock_runtime_client=bedrock, dynamodb_resource=dynamodb, s3_client=s3)
    coordinator = TransferCoordinatorAgent(region_name=REGION, bedrock_runtime_client=bedrock, dynamodb_resource=dynamodb, s3_client=s3)
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

    print(f"✅ {len(warehouses)} depo, {len(skus)} SKU, {len(stock)} stok kaydi hazir")

    return {
        "monitor": monitor,
        "predictor": predictor,
        "aging": aging,
        "coordinator": coordinator,
        "validator": validator,
        "warehouses": warehouses,
        "categories": categories,
        "bedrock": bedrock,
        "mcp": mcp,
    }


# ============================================================
# Orchestrator - Bedrock + MCP tool calling
# ============================================================

SYSTEM_PROMPT = """Sen bir Cok-Agentli Depo Stok Yonetim Sistemi'nin ana koordinator agentisin.
Kullaniciyla Turkce konus. Sana sorulan sorulara gore uygun agent'i cagir ve sonuclari raporla.

Elindeki agentlar:
1. Inventory Monitor Agent - Stok seviyelerini izler, kritik stoklari tespit eder
2. Sales Predictor Agent - Satis potansiyeli hesaplar, tahmin yapar
3. Stock Aging Analyzer Agent - Urun yaslindirmasini analiz eder
4. Transfer Coordinator Agent - Depolar arasi transfer koordine eder

Kullanicinin sorusuna gore hangi agent'in ne yapmasi gerektigini belirle ve sonuclari acikla.
Kisa ve oz yanitlar ver. Verileri tablo formatinda goster.
Kullanici "kritik stoklari goster" dediginde SADECE kritik stok listesini goster, transfer onerisi ekleme.
Transfer onerisi ancak kullanici acikca istediginde yapilmali.

ONEMLI KURALLAR:
1. Kullanici sadece "oner" gibi sorular sordugunda SADECE oneri yap, [EXECUTE_TRANSFER] komutu EKLEME.
2. Kullanici acikca "transfer et", "uygula", "yap" gibi eylem kelimeleri kullandiginda [EXECUTE_TRANSFER] komutlarini ekle.
3. Transfer onerirken kaynak depodaki stok miktarini MUTLAKA kontrol et.
4. Onay bekleyen transferleri onaylamak icin [EXECUTE_TRANSFER] KULLANMA.

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
            lines.append(f"  ⚠️ {a.warehouse_id}/{a.sku}: {a.current_quantity} (esik: {a.threshold}, siddet: {a.severity.value})")
    else:
        lines.append("  Kritik stok uyarisi yok.")

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


async def chat_with_orchestrator(user_message, agents, history):
    bedrock = agents["bedrock"]
    mcp = agents["mcp"]
    context = build_context(agents)

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
        reply = result.get("output", {}).get("message", {}).get("content", [{}])[0].get("text", "")
        reply, executed = await execute_transfers_from_reply(reply, agents)

        # Transfer yapildiysa MCP uzerinden de logla
        if executed:
            for t in executed:
                await mcp.call_tool("log_decision", {
                    "agent_name": "orchestrator",
                    "decision_type": "ai_transfer",
                    "input_data": {"source": t.source_warehouse_id, "target": t.target_warehouse_id, "sku": t.sku, "quantity": t.quantity},
                    "output_data": {"status": t.status.value, "transfer_id": t.transfer_id},
                    "reasoning": "AI orchestrator tarafindan baslatilan transfer"
                })

        return reply
    except Exception as e:
        return f"Hata: {e}"


async def verify_db_stock_after_transfer(mcp: MCPManager, src: str, tgt: str, sku: str,
                                         expected_src: int, expected_tgt: int) -> str:
    """Transfer sonrasi DynamoDB'deki gercek stoklari MCP uzerinden okuyup dogrular."""
    try:
        src_result = await mcp.call_tool("get_inventory", {"warehouse_id": src, "sku": sku})
        tgt_result = await mcp.call_tool("get_inventory", {"warehouse_id": tgt, "sku": sku})

        db_src = src_result.get("data", {}).get("quantity", "?") if src_result.get("success") else "?"
        db_tgt = tgt_result.get("data", {}).get("quantity", "?") if tgt_result.get("success") else "?"

        src_ok = db_src == expected_src
        tgt_ok = db_tgt == expected_tgt

        if src_ok and tgt_ok:
            return f"[DB ✅ {src}:{db_src} {tgt}:{db_tgt}]"
        else:
            parts = []
            if not src_ok:
                parts.append(f"{src}: DB={db_src} beklenen={expected_src}")
            if not tgt_ok:
                parts.append(f"{tgt}: DB={db_tgt} beklenen={expected_tgt}")
            return f"[DB ⚠️ UYUMSUZ: {', '.join(parts)}]"
    except Exception as e:
        return f"[DB kontrol hatasi: {e}]"


async def execute_transfers_from_reply(reply, agents):
    """AI yanitindaki [EXECUTE_TRANSFER: ...] komutlarini parse edip calistirir.
    Transfer sonuclarini MCP uzerinden de DynamoDB'ye yazar."""
    pattern = r'\[EXECUTE_TRANSFER:\s*(WH\d+)\s+(WH\d+)\s+(SKU\d+)\s+(\d+)\]'
    matches = re.findall(pattern, reply)

    if not matches:
        return reply, []

    mcp = agents["mcp"]
    clean_reply = re.sub(r'\[EXECUTE_TRANSFER:.*?\]', '', reply).strip()
    clean_reply = re.sub(r'\n{3,}', '\n\n', clean_reply)

    SAFETY_THRESHOLD = 40
    executed = []
    transfer_results = []

    for src, tgt, sku, qty_str in matches:
        qty = int(qty_str)
        safe_qty = agents["coordinator"].get_safe_transfer_amount(src, sku, qty, SAFETY_THRESHOLD)

        if safe_qty == 0:
            transfer_results.append(f"  ❌ {sku} x{qty} → {tgt}: Kaynak depoda guvenli fazlalik yok")
            continue
        elif safe_qty < qty:
            transfer_results.append(f"  🔄 {src} → {tgt}: {sku} kismi x{safe_qty} (istenen: {qty})")
            qty = safe_qty

        try:
            # In-memory agent transfer
            t = agents["coordinator"].execute_transfer(src, tgt, sku, qty, reason="ai_orchestrated")
            agents["monitor"].update_stock(src, sku, agents["coordinator"].get_stock(src, sku))
            agents["monitor"].update_stock(tgt, sku, agents["coordinator"].get_stock(tgt, sku))

            # MCP uzerinden DynamoDB'ye yaz - sadece completed ise
            # awaiting_approval ise DB'ye yazma (onay sonrasi yazilacak)
            mcp_status = "onay_bekliyor"
            db_check = ""
            if t.status.value == "completed":
                mcp_result = await mcp.call_tool("execute_transfer", {
                    "source_warehouse_id": src,
                    "target_warehouse_id": tgt,
                    "sku": sku,
                    "quantity": qty,
                    "reason": "ai_orchestrated"
                })
                mcp_status = "mcp_ok" if mcp_result.get("success") else "mcp_fail"

                # DB stok dogrulama
                db_check = await verify_db_stock_after_transfer(mcp, src, tgt, sku,
                    agents["coordinator"].get_stock(src, sku),
                    agents["coordinator"].get_stock(tgt, sku))

            status_icon = "✅" if t.status.value == "completed" else "⏳" if t.status.value == "awaiting_approval" else "❌"
            transfer_results.append(f"  {status_icon} {src} → {tgt}: {sku} x{qty} ({t.status.value}) [{mcp_status}] {db_check}")
            executed.append(t)
        except Exception as e:
            transfer_results.append(f"  ❌ {src} → {tgt}: {sku} x{qty} — Hata: {e}")

    if transfer_results:
        clean_reply += "\n\n🚚 **Gerceklestirilen Transferler:**\n" + "\n".join(transfer_results)

    return clean_reply, executed


# ============================================================
# Komut isleyiciler
# ============================================================

async def handle_command(cmd, agents):
    """Sadece sistem komutlari - geri kalan her sey AI'a gider."""
    parts = cmd.strip().split()
    if not parts:
        return ""

    action = parts[0].lower()
    mcp = agents["mcp"]

    if action == "mcp":
        tools = mcp.list_tools()
        lines = [f"🔧 MCP Tools ({len(tools)} adet):"]
        by_server = defaultdict(list)
        for name, info in tools.items():
            by_server[info["server"]].append(f"  {name}: {info['description']}")
        for server, tool_lines in by_server.items():
            lines.append(f"\n[{server}]")
            lines.extend(tool_lines)
        return "\n".join(lines)

    elif action == "mcptest" and len(parts) >= 2:
        tool_name = parts[1]
        args = {}
        if len(parts) >= 3:
            try:
                args = json.loads(" ".join(parts[2:]))
            except json.JSONDecodeError:
                return "❌ JSON parse hatasi. Ornek: mcptest get_warehouse_info {\"warehouse_id\":\"WH001\"}"
        result = await mcp.call_tool(tool_name, args)
        return json.dumps(result, indent=2, ensure_ascii=False)[:2000]

    return None


# ============================================================
# S3 log flush - agent kararlarini S3'e yazar
# ============================================================

async def flush_agent_logs_to_s3(agents):
    """Agent kararlarini S3 agent-logs/ altina yazar."""
    for name in ["monitor", "predictor", "aging", "coordinator"]:
        agent = agents[name]
        if agent._decisions:
            log_data = {
                "agent": agent.agent_name,
                "decisions_count": len(agent._decisions),
                "decisions": [
                    {
                        "decision_id": d.decision_id,
                        "type": d.decision_type,
                        "reasoning": d.reasoning,
                        "timestamp": d.timestamp,
                    }
                    for d in agent._decisions[-20:]  # son 20
                ]
            }
            agent.log_to_s3(log_data, prefix="session-")


# ============================================================
# Main
# ============================================================

HELP_TEXT = """
╔══════════════════════════════════════════════════════════╗
║  🏭 Depo Stok Yonetim Sistemi - MCP + AI Agent         ║
╠══════════════════════════════════════════════════════════╣
║  Turkce yaz, AI agent yanitlar ve islem yapar.          ║
║                                                          ║
║  mcp               - MCP tool listesini goster          ║
║  mcptest <tool> {} - MCP tool'u dogrudan test et        ║
║  yardim / help     - Bu menuyu goster                    ║
║  cikis / exit      - Cikis                               ║
╚══════════════════════════════════════════════════════════╝
"""


async def main():
    print("🏭 Depo Stok Yonetim Sistemi - MCP Entegrasyonlu")
    print("=" * 58)

    mcp = MCPManager()
    try:
        print("🔌 MCP server'lar baslatiliyor...")
        await mcp.start()

        tools = mcp.list_tools()
        print(f"   {len(tools)} MCP tool hazir")

        agents = await setup_agents(mcp)
    except Exception as e:
        print(f"❌ Baslatma hatasi: {e}")
        import traceback
        traceback.print_exc()
        await mcp.stop()
        sys.exit(1)

    print(HELP_TEXT)
    history = []

    try:
        while True:
            try:
                user_input = input("\n🧑 Sen: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n👋 Gorusuruz!")
                break

            if not user_input:
                continue

            if user_input.lower() in ("çıkış", "cikis", "exit", "quit", "q"):
                print("👋 Gorusuruz!")
                break

            if user_input.lower() in ("yardım", "yardim", "help", "h"):
                print(HELP_TEXT)
                continue

            cmd_result = await handle_command(user_input, agents)
            if cmd_result is not None:
                print(f"\n🤖 Agent: {cmd_result}")
                continue

            print("🤖 Agent: dusunuyorum...")
            reply = await chat_with_orchestrator(user_input, agents, history)
            print(f"\n🤖 Agent: {reply}")

            history.append({"role": "user", "content": [{"text": user_input}]})
            history.append({"role": "assistant", "content": [{"text": reply}]})

    finally:
        print("\n📝 Agent loglari S3'e yaziliyor...")
        try:
            await flush_agent_logs_to_s3(agents)
            print("✅ Loglar S3'e yazildi")
        except Exception as e:
            print(f"⚠️ S3 log hatasi: {e}")

        print("🔌 MCP server'lar kapatiliyor...")
        try:
            await mcp.stop()
        except Exception:
            pass
        print("✅ Temiz cikis")


if __name__ == "__main__":
    asyncio.run(main())

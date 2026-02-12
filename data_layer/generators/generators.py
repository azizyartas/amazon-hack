"""Simülasyon verisi üretim modülü.

6 depo, 10 kategori, 100 SKU, 12 aylık GÜNLÜK satış geçmişi üretir.
Ticaret merkezleri: İstanbul ve Samsun (daha yüksek kapasite ve stok).

Problemli senaryolar:
- Stok tükenmesi (stockout)
- Yaşlanan/son kullanma yaklaşan stoklar
- Anormal satış spike'ları
- Depolar arası dengesiz stok dağılımı
- Hatalı/iptal edilen transferler
- Mevsimsel talep patlamaları
"""
import json
import csv
import os
import random
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

from .models import Warehouse, Category, Product, InventoryItem, SalesRecord


# --- SABİTLER ---

WAREHOUSES = [
    Warehouse("WH001", "İstanbul Merkez Depo", "İstanbul, Türkiye", "Marmara", 12000, is_trade_hub=True),
    Warehouse("WH002", "Ankara Depo", "Ankara, Türkiye", "İç Anadolu", 8000),
    Warehouse("WH003", "İzmir Depo", "İzmir, Türkiye", "Ege", 7000),
    Warehouse("WH004", "Antalya Depo", "Antalya, Türkiye", "Akdeniz", 5000),
    Warehouse("WH005", "Bursa Depo", "Bursa, Türkiye", "Marmara", 6000),
    Warehouse("WH006", "Samsun Depo", "Samsun, Türkiye", "Karadeniz", 10000, is_trade_hub=True),
]

CATEGORIES = [
    Category("Elektronik", 90, 1.5),
    Category("Giyim", 180, 2.0),
    Category("Gıda", 30, 3.0),
    Category("Mobilya", 365, 1.0),
    Category("Kitap", 730, 1.2),
    Category("Oyuncak", 180, 2.5),
    Category("Spor Malzemeleri", 365, 1.5),
    Category("Ev Aletleri", 180, 1.3),
    Category("Kozmetik", 365, 2.0),
    Category("Otomotiv", 730, 1.0),
]

PRODUCT_NAMES: Dict[str, List[str]] = {
    "Elektronik": [
        "Laptop 15.6 inch", "Kablosuz Kulaklık", "Akıllı Saat", "Tablet 10 inch",
        "Bluetooth Hoparlör", "USB-C Hub", "Webcam HD", "Mekanik Klavye",
        "Gaming Mouse", "Taşınabilir SSD 1TB",
    ],
    "Giyim": [
        "Erkek Kışlık Mont", "Kadın Trençkot", "Kot Pantolon Slim", "Pamuklu T-Shirt",
        "Spor Ayakkabı", "Deri Cüzdan", "Yün Kazak", "Keten Gömlek",
        "Şapka Beyzbol", "Çorap Seti 6lı",
    ],
    "Gıda": [
        "Zeytinyağı 1L", "Bal Kavanoz 500g", "Kuru Kayısı 1kg", "Fındık İç 500g",
        "Çay 1kg Rize", "Türk Kahvesi 250g", "Pekmez 800g", "Tahin 300g",
        "Pestil Paketi", "Lokum Kutusu 500g",
    ],
    "Mobilya": [
        "Ofis Sandalyesi", "Çalışma Masası 120cm", "Kitaplık 5 Raflı", "TV Ünitesi",
        "Yemek Masası 6 Kişilik", "Koltuk Takımı 3+1", "Gardırop 3 Kapılı", "Sehpa Set",
        "Yatak Başlığı", "Ayakkabılık",
    ],
    "Kitap": [
        "Roman Bestseller", "Yazılım Geliştirme Kitabı", "Tarih Ansiklopedisi", "Çocuk Hikaye Seti",
        "Felsefe Klasikleri", "Bilim Kurgu Serisi", "Yemek Tarifleri", "Seyahat Rehberi",
        "Kişisel Gelişim", "Şiir Antolojisi",
    ],
    "Oyuncak": [
        "Lego Set 500 Parça", "Puzzle 1000 Parça", "Peluş Ayı 40cm", "Uzaktan Kumandalı Araba",
        "Bebek Seti", "Masa Oyunu Strateji", "Slime Kit", "Nerf Tabanca",
        "Drone Mini", "Kaykay Çocuk",
    ],
    "Spor Malzemeleri": [
        "Yoga Matı", "Dambıl Seti 20kg", "Koşu Bandı", "Pilates Topu",
        "Direnç Bandı Seti", "Atlama İpi", "Bisiklet Kaskı", "Tenis Raketi",
        "Futbol Topu", "Yüzme Gözlüğü",
    ],
    "Ev Aletleri": [
        "Robot Süpürge", "Kahve Makinesi", "Tost Makinesi", "Blender Set",
        "Ütü Buharlı", "Elektrikli Süpürge", "Mikrodalga Fırın", "Ekmek Yapma Makinesi",
        "Su Isıtıcı", "Saç Kurutma Makinesi",
    ],
    "Kozmetik": [
        "Yüz Kremi 50ml", "Şampuan 500ml", "Parfüm 100ml", "Güneş Kremi SPF50",
        "Dudak Bakım Seti", "Makyaj Paleti", "Saç Bakım Yağı", "El Kremi Set",
        "Duş Jeli 400ml", "Deodorant Roll-on",
    ],
    "Otomotiv": [
        "Motor Yağı 4L", "Akü 72Ah", "Lastik 205/55R16", "Silecek Seti",
        "Araç Parfümü", "Torpido Düzenleyici", "Araç Şarj Cihazı", "Oto Yıkama Seti",
        "Far Ampulü LED", "Direksiyon Kılıfı",
    ],
}

PRICE_RANGES: Dict[str, tuple] = {
    "Elektronik": (500, 25000),
    "Giyim": (100, 3000),
    "Gıda": (30, 500),
    "Mobilya": (1000, 30000),
    "Kitap": (30, 300),
    "Oyuncak": (50, 2000),
    "Spor Malzemeleri": (100, 15000),
    "Ev Aletleri": (300, 10000),
    "Kozmetik": (50, 2000),
    "Otomotiv": (100, 5000),
}

SEASONAL_MULTIPLIERS = {
    "Elektronik": {"high_months": [11, 12, 1], "multiplier": 2.5},
    "Giyim": {"high_months": [9, 10, 11], "multiplier": 2.0},
    "Gıda": {"high_months": [6, 7, 8, 11], "multiplier": 1.5},
    "Mobilya": {"high_months": [3, 4, 5], "multiplier": 1.8},
    "Kitap": {"high_months": [9, 10, 6], "multiplier": 1.6},
    "Oyuncak": {"high_months": [12, 1, 4], "multiplier": 2.5},
    "Spor Malzemeleri": {"high_months": [5, 6, 7], "multiplier": 2.0},
    "Ev Aletleri": {"high_months": [11, 12, 6], "multiplier": 1.8},
    "Kozmetik": {"high_months": [2, 3, 12], "multiplier": 1.5},
    "Otomotiv": {"high_months": [3, 4, 10], "multiplier": 1.4},
}

REGIONAL_MULTIPLIERS = {
    "Marmara": 1.5,
    "İç Anadolu": 1.2,
    "Ege": 1.3,
    "Akdeniz": 1.1,
    "Karadeniz": 1.4,
}

TRADE_HUB_MULTIPLIER = 1.3


# --- ÜRETİM FONKSİYONLARI ---

def generate_warehouses() -> List[dict]:
    """6 depo verisi üretir."""
    return [
        {
            "warehouse_id": w.warehouse_id,
            "name": w.name,
            "location": w.location,
            "region": w.region,
            "capacity": w.capacity,
            "is_trade_hub": w.is_trade_hub,
            "created_at": "2024-01-01T00:00:00Z",
        }
        for w in WAREHOUSES
    ]


def generate_categories() -> List[dict]:
    """10 kategori verisi üretir."""
    return [
        {
            "name": c.name,
            "aging_threshold_days": c.aging_threshold_days,
            "min_stock_multiplier": c.min_stock_multiplier,
        }
        for c in CATEGORIES
    ]


def generate_products() -> List[dict]:
    """100 SKU üretir (her kategoriden 10 ürün)."""
    products = []
    sku_counter = 1
    for cat in CATEGORIES:
        names = PRODUCT_NAMES[cat.name]
        price_min, price_max = PRICE_RANGES[cat.name]
        for name in names:
            sku = f"SKU{sku_counter:03d}"
            price = round(random.uniform(price_min, price_max), 2)
            products.append({
                "sku": sku,
                "name": name,
                "category": cat.name,
                "price": price,
                "aging_threshold_days": cat.aging_threshold_days,
                "created_at": "2024-01-01T00:00:00Z",
            })
            sku_counter += 1
    return products


def generate_initial_inventory(products: List[dict]) -> List[dict]:
    """Her depo × her SKU için başlangıç stok seviyesi üretir.

    Ticaret merkezleri (İstanbul, Samsun) daha yüksek stok alır.
    Problemli senaryolar:
    - Bazı SKU'lar bazı depolarda kritik düşük stokta başlar
    - Bazı ürünler çok eski giriş tarihiyle yaşlandırma problemi yaratır
    - Bazı depolarda aşırı stok birikimi (dengesiz dağılım)
    """
    inventory = []
    now = datetime.now().isoformat() + "Z"

    # Problemli SKU'lar: kritik düşük stokla başlayacaklar
    stockout_skus = random.sample(range(1, 101), 15)  # 15 SKU kritik düşük
    # Yaşlanan stok: çok eski giriş tarihi
    aging_skus = random.sample(range(1, 101), 12)  # 12 SKU yaşlanmış
    # Aşırı stok birikimi: belirli depolarda fazla stok
    overstock_warehouses = {"WH003", "WH004"}  # İzmir ve Antalya'da fazla stok birikimi

    for wh in WAREHOUSES:
        for prod in products:
            cat = next(c for c in CATEGORIES if c.name == prod["category"])
            sku_num = int(prod["sku"][3:])

            # Baz stok: 30-300 arası (daha yoğun depolar)
            base_qty = random.randint(30, 300)

            # Ticaret merkezi ise %60 daha fazla stok
            if wh.is_trade_hub:
                base_qty = int(base_qty * 1.6)

            # --- PROBLEMLİ SENARYO: Kritik düşük stok ---
            if sku_num in stockout_skus and wh.warehouse_id in ("WH002", "WH004", "WH005"):
                base_qty = random.randint(0, 5)  # Neredeyse sıfır stok

            # --- PROBLEMLİ SENARYO: Aşırı stok birikimi ---
            if wh.warehouse_id in overstock_warehouses and sku_num % 3 == 0:
                base_qty = int(base_qty * 3)  # 3 kat fazla stok

            min_threshold = max(5, int(base_qty * cat.min_stock_multiplier / 4))
            max_threshold = max(min_threshold * 4, int(base_qty * 2))

            # --- PROBLEMLİ SENARYO: Yaşlanan stok ---
            if sku_num in aging_skus and wh.warehouse_id in ("WH003", "WH005"):
                # Yaşlandırma eşiğini aşmış ürünler
                days_ago = cat.aging_threshold_days + random.randint(30, 180)
            else:
                days_ago = random.randint(1, 365)

            received = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%dT00:00:00Z")

            inventory.append({
                "warehouse_id": wh.warehouse_id,
                "sku": prod["sku"],
                "quantity": base_qty,
                "min_threshold": min_threshold,
                "max_threshold": max_threshold,
                "received_date": received,
                "last_updated": now,
            })

    return inventory


def generate_daily_sales(products: List[dict], days: int = 365) -> List[dict]:
    """GÜNLÜK satış kayıtları üretir. ~200K+ kayıt.

    Her gün, her depo, her SKU için satış kaydı (satış olan günler).
    Hafta sonları %30 daha fazla satış.
    Problemli senaryolar dahil.
    """
    sales = []
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = today - timedelta(days=days)

    # Problemli senaryolar için tarihler
    # Anormal spike günleri (viral ürün, kampanya vs.)
    spike_events = [
        {"date_offset": 45, "skus": list(range(1, 11)), "multiplier": 8, "reason": "Black Friday kampanyası"},
        {"date_offset": 90, "skus": list(range(11, 21)), "multiplier": 6, "reason": "Sezon sonu indirimi"},
        {"date_offset": 150, "skus": list(range(21, 31)), "multiplier": 10, "reason": "Gıda bayram talebi"},
        {"date_offset": 200, "skus": [41, 42, 43], "multiplier": 12, "reason": "Viral ürün sosyal medya"},
        {"date_offset": 250, "skus": list(range(51, 61)), "multiplier": 7, "reason": "Okul dönemi talebi"},
        {"date_offset": 300, "skus": list(range(61, 71)), "multiplier": 5, "reason": "Yaz spor sezonu"},
    ]

    # Sıfır satış günleri (tedarik sorunu, depoda ürün yok)
    dead_periods = [
        {"warehouse": "WH004", "start_offset": 100, "duration": 14, "skus": list(range(1, 11))},
        {"warehouse": "WH002", "start_offset": 180, "duration": 7, "skus": list(range(21, 31))},
        {"warehouse": "WH005", "start_offset": 220, "duration": 10, "skus": list(range(31, 41))},
    ]

    for wh in WAREHOUSES:
        regional_mult = REGIONAL_MULTIPLIERS.get(wh.region, 1.0)
        hub_mult = TRADE_HUB_MULTIPLIER if wh.is_trade_hub else 1.0

        for prod in products:
            sku_num = int(prod["sku"][3:])
            seasonal = SEASONAL_MULTIPLIERS.get(prod["category"], {"high_months": [], "multiplier": 1.0})

            current = start_date
            while current < today:
                day_offset = (today - current).days
                month = current.month
                weekday = current.weekday()  # 0=Pazartesi, 6=Pazar

                # Baz günlük satış: 1-15 arası (daha yoğun)
                base_daily = random.randint(1, 15)

                # Hafta sonu çarpanı
                weekend_mult = 1.3 if weekday >= 5 else 1.0

                # Mevsimsel çarpan
                season_mult = seasonal["multiplier"] if month in seasonal["high_months"] else 1.0

                # --- PROBLEMLİ SENARYO: Anormal spike ---
                spike_mult = 1.0
                for spike in spike_events:
                    if (abs(day_offset - spike["date_offset"]) <= 2
                            and sku_num in spike["skus"]):
                        spike_mult = spike["multiplier"]

                # --- PROBLEMLİ SENARYO: Sıfır satış (tedarik sorunu) ---
                is_dead = False
                for dead in dead_periods:
                    if (wh.warehouse_id == dead["warehouse"]
                            and dead["start_offset"] <= day_offset <= dead["start_offset"] + dead["duration"]
                            and sku_num in dead["skus"]):
                        is_dead = True
                        break

                if is_dead:
                    daily_qty = 0
                else:
                    daily_qty = max(0, int(
                        base_daily * season_mult * regional_mult * hub_mult * weekend_mult * spike_mult
                    ))

                # Rastgele bazı günler satış olmayabilir (%10 ihtimal)
                if not is_dead and random.random() < 0.10:
                    daily_qty = 0

                # Sadece satış olan günleri kaydet (veri hacmini biraz kontrol et)
                if daily_qty > 0:
                    date_str = current.strftime("%Y-%m-%d")
                    revenue = round(daily_qty * prod["price"], 2)

                    sales.append({
                        "warehouse_id": wh.warehouse_id,
                        "date_sku": f"{date_str}#{prod['sku']}",
                        "sku": prod["sku"],
                        "date": date_str,
                        "quantity_sold": daily_qty,
                        "revenue": revenue,
                    })

                current += timedelta(days=1)

    return sales


def generate_problem_scenarios() -> List[dict]:
    """Agentların çözmesi gereken problemli senaryoları tanımlar.

    Bu dosya agentlara input olarak verilecek, çözüm üretmeleri bekleniyor.
    """
    scenarios = [
        # --- STOK TÜKENMESİ ---
        {
            "scenario_id": "PROB001",
            "type": "stockout_risk",
            "severity": "critical",
            "description": "Ankara deposunda Elektronik kategorisi kritik stok seviyesinde",
            "affected_warehouse": "WH002",
            "affected_skus": ["SKU001", "SKU002", "SKU003", "SKU004", "SKU005"],
            "current_stock_range": "0-5 adet",
            "expected_action": "İstanbul veya Samsun'dan acil transfer",
            "deadline_hours": 24,
        },
        {
            "scenario_id": "PROB002",
            "type": "stockout_risk",
            "severity": "critical",
            "description": "Antalya deposunda Elektronik ürünleri tükenmiş, turizm sezonu yaklaşıyor",
            "affected_warehouse": "WH004",
            "affected_skus": ["SKU001", "SKU003", "SKU005", "SKU007", "SKU009"],
            "current_stock_range": "0-3 adet",
            "expected_action": "Yüksek satış potansiyeli olan depoya acil transfer",
            "deadline_hours": 12,
        },
        {
            "scenario_id": "PROB003",
            "type": "stockout_risk",
            "severity": "high",
            "description": "Bursa deposunda Gıda ürünleri kritik seviyede",
            "affected_warehouse": "WH005",
            "affected_skus": ["SKU021", "SKU023", "SKU025", "SKU027"],
            "current_stock_range": "1-5 adet",
            "expected_action": "Samsun veya İstanbul'dan gıda transferi",
            "deadline_hours": 48,
        },

        # --- YAŞLANAN STOK ---
        {
            "scenario_id": "PROB004",
            "type": "aging_stock",
            "severity": "high",
            "description": "İzmir deposunda Gıda ürünleri son kullanma tarihine yaklaşıyor",
            "affected_warehouse": "WH003",
            "affected_skus": ["SKU021", "SKU022", "SKU023", "SKU024", "SKU025"],
            "aging_days_over_threshold": "30-60 gün",
            "expected_action": "Satış potansiyeli yüksek depoya acil transfer veya indirimli satış",
            "deadline_hours": 72,
        },
        {
            "scenario_id": "PROB005",
            "type": "aging_stock",
            "severity": "medium",
            "description": "Bursa deposunda Elektronik ürünler yaşlanıyor (yeni model çıkacak)",
            "affected_warehouse": "WH005",
            "affected_skus": ["SKU001", "SKU004", "SKU008"],
            "aging_days_over_threshold": "15-45 gün",
            "expected_action": "İstanbul'a transfer (yüksek satış potansiyeli)",
            "deadline_hours": 168,
        },

        # --- DENGESİZ STOK DAĞILIMI ---
        {
            "scenario_id": "PROB006",
            "type": "imbalanced_stock",
            "severity": "medium",
            "description": "İzmir ve Antalya'da aşırı stok birikimi, diğer depolar düşük",
            "overstock_warehouses": ["WH003", "WH004"],
            "understock_warehouses": ["WH002", "WH005"],
            "affected_categories": ["Mobilya", "Spor Malzemeleri"],
            "expected_action": "Stok dengeleme transferleri planla",
            "deadline_hours": 336,
        },

        # --- ANORMAL TALEP PATLAMASI ---
        {
            "scenario_id": "PROB007",
            "type": "demand_spike",
            "severity": "high",
            "description": "Sosyal medyada viral olan Oyuncak ürünü, talep 12x arttı",
            "affected_skus": ["SKU041", "SKU042", "SKU043"],
            "spike_multiplier": 12,
            "affected_warehouses": "all",
            "expected_action": "Tüm depolara acil stok dağıtımı, üretici siparişi",
            "deadline_hours": 48,
        },
        {
            "scenario_id": "PROB008",
            "type": "demand_spike",
            "severity": "high",
            "description": "Black Friday kampanyası - Elektronik talebinde 8x artış bekleniyor",
            "affected_skus": ["SKU001", "SKU002", "SKU003", "SKU004", "SKU005",
                             "SKU006", "SKU007", "SKU008", "SKU009", "SKU010"],
            "spike_multiplier": 8,
            "affected_warehouses": "all",
            "expected_action": "Ticaret merkezlerinden (İstanbul, Samsun) dağıtım planla",
            "deadline_hours": 72,
        },

        # --- TEDARİK SORUNU ---
        {
            "scenario_id": "PROB009",
            "type": "supply_disruption",
            "severity": "critical",
            "description": "Antalya deposuna 2 hafta boyunca Elektronik tedarik yapılamadı",
            "affected_warehouse": "WH004",
            "disruption_days": 14,
            "affected_skus": ["SKU001", "SKU002", "SKU003", "SKU004", "SKU005",
                             "SKU006", "SKU007", "SKU008", "SKU009", "SKU010"],
            "expected_action": "Diğer depolardan acil transfer, müşteri bilgilendirme",
            "deadline_hours": 24,
        },
        {
            "scenario_id": "PROB010",
            "type": "supply_disruption",
            "severity": "medium",
            "description": "Ankara deposuna Gıda tedarikinde 1 haftalık gecikme",
            "affected_warehouse": "WH002",
            "disruption_days": 7,
            "affected_skus": ["SKU021", "SKU022", "SKU023", "SKU024", "SKU025",
                             "SKU026", "SKU027", "SKU028", "SKU029", "SKU030"],
            "expected_action": "Samsun'dan gıda transferi planla",
            "deadline_hours": 48,
        },

        # --- HATALI TRANSFER ---
        {
            "scenario_id": "PROB011",
            "type": "failed_transfer",
            "severity": "high",
            "description": "İstanbul→Ankara transferi yarıda kaldı, stok havada",
            "transfer_details": {
                "source": "WH001",
                "target": "WH002",
                "sku": "SKU015",
                "quantity": 50,
                "status": "in_transit_stuck",
            },
            "expected_action": "Transfer durumunu çöz, stok tutarlılığını sağla",
            "deadline_hours": 6,
        },
        {
            "scenario_id": "PROB012",
            "type": "failed_transfer",
            "severity": "medium",
            "description": "Yanlış depoya gönderilmiş ürünler (İzmir yerine Antalya'ya)",
            "transfer_details": {
                "intended_target": "WH003",
                "actual_target": "WH004",
                "sku": "SKU035",
                "quantity": 30,
                "status": "misrouted",
            },
            "expected_action": "Düzeltme transferi planla veya Antalya'da tut (satış potansiyeli analizi)",
            "deadline_hours": 72,
        },

        # --- KAPASİTE AŞIMI ---
        {
            "scenario_id": "PROB013",
            "type": "capacity_overflow",
            "severity": "medium",
            "description": "İzmir deposu kapasite sınırına yaklaşıyor (%95 dolu)",
            "affected_warehouse": "WH003",
            "current_utilization": 0.95,
            "expected_action": "Düşük satış potansiyelli ürünleri diğer depolara aktar",
            "deadline_hours": 168,
        },

        # --- YÜKSEK DEĞERLİ TRANSFER (İNSAN ONAYI GEREKTİREN) ---
        {
            "scenario_id": "PROB014",
            "type": "high_value_transfer",
            "severity": "medium",
            "description": "500.000 TL üzeri Elektronik transferi - insan onayı gerekli",
            "transfer_details": {
                "source": "WH001",
                "target": "WH006",
                "skus": ["SKU001", "SKU003", "SKU004"],
                "total_value": 750000,
                "requires_approval": True,
            },
            "expected_action": "İnsan onayı talep et, onay beklerken alternatif planla",
            "deadline_hours": 48,
        },

        # --- MEVSİMSEL GEÇİŞ ---
        {
            "scenario_id": "PROB015",
            "type": "seasonal_transition",
            "severity": "low",
            "description": "Yaz→Kış geçişi: Giyim stokları yeniden dengelenmeli",
            "affected_categories": ["Giyim"],
            "summer_overstock_warehouses": ["WH004"],  # Antalya'da yazlık fazlası
            "winter_demand_warehouses": ["WH001", "WH002", "WH006"],  # İstanbul, Ankara, Samsun
            "expected_action": "Mevsimsel stok transferi planla",
            "deadline_hours": 336,
        },
    ]
    return scenarios


def save_json(data, filepath: str):
    """JSON dosyasına kaydet."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  ✓ {filepath} ({len(data)} kayıt)")


def save_csv(data: List[dict], filepath: str):
    """CSV dosyasına kaydet."""
    if not data:
        return
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    print(f"  ✓ {filepath} ({len(data)} kayıt)")


def generate_all(output_dir: str = "data_layer/data", seed: int = 42):
    """Tüm simülasyon verisini üretir ve kaydeder."""
    random.seed(seed)
    print("🏭 Simülasyon verisi üretiliyor...\n")

    # 1. Depolar
    print("📦 Depolar:")
    warehouses = generate_warehouses()
    save_json(warehouses, f"{output_dir}/warehouses.json")

    # 2. Kategoriler
    print("\n📂 Kategoriler:")
    categories = generate_categories()
    save_json(categories, f"{output_dir}/categories.json")

    # 3. Ürünler (100 SKU)
    print("\n🏷️  Ürünler:")
    products = generate_products()
    save_json(products, f"{output_dir}/products.json")

    # 4. Başlangıç stok seviyeleri (problemli senaryolar dahil)
    print("\n📊 Stok seviyeleri:")
    inventory = generate_initial_inventory(products)
    save_json(inventory, f"{output_dir}/initial-inventory.json")

    # 5. Günlük satış geçmişi (12 ay, ~200K+ kayıt)
    print("\n💰 Günlük satış geçmişi (365 gün):")
    sales = generate_daily_sales(products, days=365)
    save_json(sales, f"{output_dir}/sales-history.json")
    save_csv(sales, f"{output_dir}/sales-history.csv")

    # 6. Problemli senaryolar
    print("\n⚠️  Problemli senaryolar:")
    scenarios = generate_problem_scenarios()
    save_json(scenarios, f"{output_dir}/problem-scenarios.json")

    # Özet
    print(f"\n{'='*60}")
    print(f"✅ Üretim tamamlandı!")
    print(f"   Depolar: {len(warehouses)} (Ticaret merkezleri: İstanbul, Samsun)")
    print(f"   Kategoriler: {len(categories)}")
    print(f"   Ürünler (SKU): {len(products)}")
    print(f"   Stok kayıtları: {len(inventory)} ({len(warehouses)} depo × {len(products)} SKU)")
    print(f"   Satış kayıtları: {len(sales):,} (günlük bazda)")
    print(f"   Problemli senaryolar: {len(scenarios)}")
    print(f"   Çıktı dizini: {output_dir}/")

    # Problem özeti
    print(f"\n⚠️  Problem Senaryoları Özeti:")
    problem_types = {}
    for s in scenarios:
        t = s["type"]
        problem_types[t] = problem_types.get(t, 0) + 1
    for t, count in problem_types.items():
        print(f"   - {t}: {count} senaryo")

    return {
        "warehouses": warehouses,
        "categories": categories,
        "products": products,
        "inventory": inventory,
        "sales": sales,
        "scenarios": scenarios,
    }


if __name__ == "__main__":
    generate_all()

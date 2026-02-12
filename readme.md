# Çok-Agentlı Depo Stok Yönetim Sistemi

AWS Bedrock tabanlı, otonom agent topluluğu kullanarak depolar arası akıllı stok yönetimi sağlayan sistem.

## 🎯 Proje Özeti

6 depo, 100 SKU, 4 otonom agent. AWS Bedrock Nova modelleri ve Agent Core primitives kullanarak depolar arası stok transferlerini otomatikleştiren çok-agent sistemi.

## 📁 Proje Yapısı

```
.
├── data_layer/                 # Developer 1: Veri ve AWS altyapısı
│   ├── data/                   # Üretilmiş simülasyon verileri
│   │   ├── warehouses.json     # 6 depo tanımı
│   │   ├── products.json       # 100 SKU
│   │   ├── categories.json     # 10 kategori
│   │   ├── initial-inventory.json  # 600 envanter kaydı (6 depo × 100 SKU)
│   │   ├── sales-history.json  # 196K+ günlük satış kaydı
│   │   ├── sales-history.csv   # CSV formatında satış verisi
│   │   └── problem-scenarios.json  # 15 problem senaryosu
│   ├── generators/             # Veri üretim modülleri
│   │   ├── models.py           # Dataclass tanımları
│   │   └── generators.py       # Simülasyon verisi üretici
│   ├── infrastructure/         # AWS altyapı scriptleri
│   │   ├── dynamodb_setup.py   # 6 DynamoDB tablosu oluşturma & veri yükleme
│   │   └── s3_setup.py         # S3 bucket oluşturma & veri yükleme
│   ├── scripts/
│   │   └── setup_aws.py        # Ana kurulum scripti (tek komutla her şey)
│   └── CONNECTION_GUIDE.md     # Diğer devler için bağlantı rehberi
│
├── .kiro/
│   ├── settings/mcp.json       # MCP server konfigürasyonu
│   └── specs/                  # Proje spesifikasyonları
│       └── multi-agent-warehouse-stock-management/
│           ├── requirements.md # 10 gereksinim
│           ├── design.md       # Mimari tasarım, 32 doğruluk özelliği
│           └── tasks.md        # 21 görev, 13 haftalık sprint planı
│
├── requirements.txt
└── readme.md
```


## 👥 Ekip ve Sorumluluklar

| Developer | Dizin | Sorumluluk |
|-----------|-------|------------|
| Dev 1 | `data_layer/` | Veri üretimi, DynamoDB/S3 altyapısı |
| Dev 2 | kendi repo'sunda | 4 Bedrock agent implementasyonu |
| Dev 3 | kendi repo'sunda | DB-Agent arası MCP köprüsü |

Dev 2 ve Dev 3, `data_layer/CONNECTION_GUIDE.md` dosyasını okuyarak DynamoDB/S3 bağlantısını kurar.

## 🏗️ Agent Yapısı

- **Inventory Monitor Agent** (Nova Lite): Stok seviyelerini izler, kritik durumları tespit eder
- **Sales Predictor Agent** (Nova Pro): Satış tahminleri yapar, potansiyel hesaplar
- **Stock Aging Analyzer Agent** (Nova Lite): Ürün yaşlandırmasını analiz eder
- **Transfer Coordinator Agent** (Nova Pro): Transfer kararlarını koordine eder

## 📊 Veri Özeti

- **6 Depo**: İstanbul, Ankara, İzmir, Antalya, Bursa, Samsun (İstanbul & Samsun ticaret merkezi)
- **10 Kategori**: Elektronik, Giyim, Gıda, Mobilya, Kitap, Oyuncak, Spor Malzemeleri, Ev Aletleri, Kozmetik, Otomotiv
- **100 SKU**: Gerçekçi Türkçe ürün adları ve TL fiyatları
- **196K+ Satış Kaydı**: 365 günlük, mevsimsel çarpanlar, hafta sonu etkileri, spike olayları
- **15 Problem Senaryosu**: Stok tükenmesi, yaşlanma, dengesizlik, talep patlaması vb.

## 🚀 Hızlı Başlangıç

```bash
# Bağımlılıkları yükle
pip install -r requirements.txt

# AWS credentials yapılandır
aws configure

# Simülasyon verisini yeniden üret (opsiyonel, data/ zaten mevcut)
python -m data_layer.generators.generators

# AWS altyapısını kur ve veriyi yükle
python -m data_layer.scripts.setup_aws

# Silmek için
python -m data_layer.scripts.setup_aws --delete

# Farklı region kullanmak için
python -m data_layer.scripts.setup_aws --region eu-west-1
```

## 🗄️ DynamoDB Tabloları

| Tablo | Partition Key | Sort Key | GSI |
|-------|--------------|----------|-----|
| Warehouses | warehouse_id | - | - |
| Products | sku | - | CategoryIndex (category) |
| Inventory | warehouse_id | sku | - |
| SalesHistory | warehouse_id | date_sku | - |
| Transfers | transfer_id | - | StatusTimeIndex (status + created_at) |
| AgentDecisions | decision_id | - | AgentTimeIndex (agent_name + timestamp) |

## 📚 Detaylı Dokümantasyon

- `.kiro/specs/multi-agent-warehouse-stock-management/requirements.md` → Gereksinimler
- `.kiro/specs/multi-agent-warehouse-stock-management/design.md` → Mimari tasarım
- `.kiro/specs/multi-agent-warehouse-stock-management/tasks.md` → Sprint planı
- `data_layer/CONNECTION_GUIDE.md` → Data layer bağlantı rehberi

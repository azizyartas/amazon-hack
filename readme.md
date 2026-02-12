# Çok-Agentlı Depo Stok Yönetim Sistemi

AWS Bedrock tabanlı, otonom agent topluluğu kullanarak depolar arası akıllı stok yönetimi sağlayan sistem.

## 🎯 Proje Özeti

Bu proje, AWS Bedrock Nova modelleri ve Agent Core primitives kullanarak depolar arası stok yönetimini otomatikleştiren bir çok-agent sistemidir. Sistem, stok seviyeleri, satış potansiyeli ve ürün yaşlandırmasına göre akıllı kararlar alır.

## 🏗️ Mimari

### Agent Yapısı
- **Inventory Monitor Agent**: Stok seviyelerini izler, kritik durumları tespit eder
- **Sales Predictor Agent**: Satış tahminleri yapar, potansiyel hesaplar
- **Stock Aging Analyzer Agent**: Ürün yaşlandırmasını analiz eder
- **Transfer Coordinator Agent**: Transfer kararlarını koordine eder

### AWS Servisleri
- **AWS Bedrock**: Nova Pro/Lite modelleri, Agent Core primitives
- **Amazon DynamoDB**: Stok, transfer ve agent kararları verisi
- **Amazon S3**: Simülasyon verisi, agent logları
- **Amazon QuickSight**: Dashboard ve görselleştirme
- **AWS Lambda**: Agent orchestration
- **CloudWatch**: Monitoring ve alerting

## 📊 Veri Yapısı

### Simülasyon Verisi
- **6 Depo**: İstanbul, Ankara, İzmir, Antalya, Bursa, Trabzon
- **10 Kategori**: Elektronik, Giyim, Gıda, Mobilya, Kitap, vb.
- **100 SKU**: Çeşitli ürünler
- **12 Aylık Satış Geçmişi**: Her SKU için geçmiş satış verileri

## 👥 Ekip Yapısı (3 Kişi)

### Geliştirici 1: AWS Altyapı ve Agent Mimarisi
- Bedrock Agent Core entegrasyonu
- DynamoDB/S3 altyapısı
- Agent orchestration
- Hata yönetimi

### Geliştirici 2: Agent Mantığı ve İş Kuralları
- 4 agent implementasyonu
- Nova model entegrasyonu
- Karar algoritmaları
- Agent iletişimi

### Geliştirici 3: Test, Veri ve Görselleştirme
- Simülasyon verisi üretimi
- Property-based testler (32 özellik)
- Unit testler (80+ test)
- QuickSight dashboard'ları
- CI/CD pipeline

## 📁 Proje Yapısı

```
.
├── .kiro/
│   └── specs/
│       └── multi-agent-warehouse-stock-management/
│           ├── requirements.md    # Gereksinimler (10 ana gereksinim)
│           ├── design.md          # Mimari ve tasarım (32 özellik)
│           └── tasks.md           # Görevler ve sprint planı (21 görev)
├── src/
│   ├── agents/
│   │   ├── inventory_monitor.py
│   │   ├── sales_predictor.py
│   │   ├── stock_aging_analyzer.py
│   │   └── transfer_coordinator.py
│   ├── orchestration/
│   │   └── agent_orchestrator.py
│   ├── data/
│   │   ├── models.py
│   │   └── repositories.py
│   └── utils/
│       ├── bedrock_client.py
│       └── error_handler.py
├── tests/
│   ├── unit/
│   ├── property/
│   ├── integration/
│   └── simulation/
├── data/
│   ├── warehouses.json
│   ├── products.json
│   └── initial-inventory.json
└── infrastructure/
    └── cdk/
```

## 🚀 Başlangıç

### Gereksinimler
- Python 3.11+
- AWS Hesabı (Bedrock erişimi aktif)
- boto3, pytest, hypothesis

### Kurulum
```bash
# Bağımlılıkları yükle
pip install -r requirements.txt

# AWS credentials yapılandır
aws configure

# Simülasyon verisini üret
python scripts/generate_simulation_data.py

# Testleri çalıştır
pytest tests/ -v
```

## 📋 Geliştirme Planı

### Faz 1: Altyapı (Hafta 1-2)
- AWS altyapısı kurulumu
- Simülasyon verisi üretimi
- Temel agent yapısı

### Faz 2: Agent Geliştirme (Hafta 3-5)
- 4 agent implementasyonu
- Nova model entegrasyonu

### Faz 3: Koordinasyon (Hafta 6-7)
- Agent iletişimi
- Orchestration

### Faz 4: Dayanıklılık (Hafta 8)
- Hata yönetimi
- Stok tutarlılığı

### Faz 5: Test (Hafta 9-10)
- Property-based testler
- Unit ve entegrasyon testleri

### Faz 6: Görselleştirme (Hafta 11)
- QuickSight dashboard'ları
- Monitoring

### Faz 7: Optimizasyon (Hafta 12)
- Performans iyileştirmeleri
- Dokümantasyon

### Faz 8: Demo (Hafta 13)
- Demo hazırlığı
- AWS AI Agent Qualification

## 🧪 Test Stratejisi

### Property-Based Testing
- 32 özellik için Hypothesis testleri
- Minimum 100 iterasyon/test
- Tüm girdiler üzerinde doğrulama

### Unit Testing
- Her agent için 20+ test
- Edge case testleri
- Hata durumu testleri

### Simülasyon Testing
- 30 günlük tam simülasyon
- 6 depo, 100 SKU
- Yüksek yük testleri

## 📊 Doğruluk Özellikleri (Örnekler)

1. **Düşük Stok Tespiti**: Stok eşiğin altına düştüğünde uyarı oluşturulmalı
2. **Transfer Sonrası Stok Korunumu**: Transfer öncesi ve sonrası toplam stok aynı kalmalı
3. **Negatif Stok Yasağı**: Hiçbir işlem sonrası negatif stok olmamalı
4. **Atomik Transfer İşlemleri**: Transfer ya tamamen başarılı ya da hiç gerçekleşmemeli
5. **Yaşlı Stok Önceliklendirme**: Yaşlı stoklar transfer edilirken önceliklendirilmeli

*Toplam 32 özellik design.md dosyasında detaylandırılmıştır.*

## 💰 Maliyet Tahmini

**Aylık AWS Maliyeti**: $474-1,152
- Bedrock (Nova): $250-650
- DynamoDB: $50-100
- S3: $20-50
- Lambda: $30-80
- QuickSight: $24-72

## 📚 Dokümantasyon

Detaylı dokümantasyon için `.kiro/specs/multi-agent-warehouse-stock-management/` klasörüne bakın:
- `requirements.md`: Kullanıcı hikayeleri ve kabul kriterleri
- `design.md`: Mimari, veri modelleri, agent tasarımı
- `tasks.md`: Görev listesi ve sprint planı

## 🎯 AWS AI Agent Qualification

Sistem aşağıdaki kriterleri karşılar:
- ✅ Reasoning LLM kullanımı (Bedrock Nova)
- ✅ Otonom karar verme yetenekleri
- ✅ İnsan müdahalesi ile/müdahalesiz çalışma
- ✅ Bedrock Agent Core primitives kullanımı

## 📞 İletişim

Sorularınız için ekip üyeleriyle iletişime geçin.

## 📄 Lisans

[Lisans bilgisi eklenecek]

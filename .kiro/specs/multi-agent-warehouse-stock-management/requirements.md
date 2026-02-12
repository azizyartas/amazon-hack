# Gereksinimler Dokümanı

## Giriş

Çok-Agentlı Depo Stok Yönetim Sistemi, AWS Bedrock tabanlı otonom agent topluluğu kullanarak depolar arası akıllı stok yönetimi sağlayan bir sistemdir. Sistem, stok seviyeleri, satış potansiyeli ve ürün yaşlandırmasına göre otomatik kararlar alır ve depolar arası transfer işlemlerini koordine eder.

## Sözlük

- **Sistem**: Çok-Agentlı Depo Stok Yönetim Sistemi
- **Agent**: AWS Bedrock üzerinde çalışan otonom karar verme birimi
- **Depo**: Fiziksel veya sanal ürün depolama lokasyonu
- **SKU**: Stock Keeping Unit - Benzersiz ürün tanımlayıcısı
- **Transfer**: Bir depodan başka bir depoya ürün taşıma işlemi
- **Stok_Seviyesi**: Bir depodaki belirli bir SKU'nun mevcut miktarı
- **Yaşlandırma**: Ürünün depoda kalma süresi
- **Satış_Potansiyeli**: Bir ürünün belirli bir depoda satılma olasılığı
- **Inventory_Monitor_Agent**: Stok seviyelerini izleyen agent
- **Transfer_Coordinator_Agent**: Transfer işlemlerini koordine eden agent
- **Sales_Predictor_Agent**: Satış tahminleri yapan agent
- **Stock_Aging_Analyzer_Agent**: Ürün yaşlandırmasını analiz eden agent
- **Bedrock_Agent_Core**: AWS Bedrock'un agent primitives sağlayan çekirdek servisi
- **Nova_Model**: AWS Bedrock'un reasoning yeteneklerine sahip LLM modeli

## Gereksinimler

### Gereksinim 1: Stok Seviyesi İzleme

**Kullanıcı Hikayesi:** Bir sistem yöneticisi olarak, tüm depolardaki stok seviyelerinin gerçek zamanlı izlenmesini istiyorum, böylece stok eksikliklerini önceden tespit edebilirim.

#### Kabul Kriterleri

1. THE Inventory_Monitor_Agent SHALL tüm depolardaki Stok_Seviyesi verilerini sürekli izlemeli
2. WHEN bir SKU'nun Stok_Seviyesi kritik eşiğin altına düştüğünde, THE Inventory_Monitor_Agent SHALL bir uyarı oluşturmalı
3. THE Inventory_Monitor_Agent SHALL her depo için minimum stok eşiklerini saklamalı
4. WHEN stok verileri güncellendiğinde, THE Sistem SHALL değişiklikleri 5 saniye içinde yansıtmalı
5. THE Inventory_Monitor_Agent SHALL stok verilerini AWS Bedrock Nova_Model kullanarak analiz etmeli

### Gereksinim 2: Depolar Arası Otomatik Transfer

**Kullanıcı Hikayesi:** Bir lojistik yöneticisi olarak, stok azaldığında depolar arası otomatik transfer yapılmasını istiyorum, böylece manuel müdahale gerekmeden stok dengesi sağlanır.

#### Kabul Kriterleri

1. WHEN bir Depo'da Stok_Seviyesi minimum eşiğin altına düştüğünde, THE Transfer_Coordinator_Agent SHALL transfer ihtiyacını tespit etmeli
2. THE Transfer_Coordinator_Agent SHALL kaynak depoyu yeterli stok seviyesine göre seçmeli
3. WHEN transfer kararı alındığında, THE Transfer_Coordinator_Agent SHALL transfer miktarını hesaplamalı
4. THE Transfer_Coordinator_Agent SHALL transfer işlemini başlatmadan önce her iki deponun stok tutarlılığını doğrulamalı
5. WHEN transfer tamamlandığında, THE Sistem SHALL her iki deponun Stok_Seviyesi verilerini güncellemeli
6. THE Transfer_Coordinator_Agent SHALL AWS Bedrock Agent_Core primitives kullanarak transfer kararlarını otonom olarak almalı

### Gereksinim 3: Satış Potansiyeline Göre Ürün Yönlendirme

**Kullanıcı Hikayesi:** Bir satış müdürü olarak, ürünlerin satış potansiyeli yüksek depolara yönlendirilmesini istiyorum, böylece satış verimliliği artar.

#### Kabul Kriterleri

1. THE Sales_Predictor_Agent SHALL her Depo için SKU bazında Satış_Potansiyeli hesaplamalı
2. WHEN transfer kararı alınırken, THE Transfer_Coordinator_Agent SHALL Satış_Potansiyeli verilerini dikkate almalı
3. THE Sales_Predictor_Agent SHALL geçmiş satış verilerini analiz ederek tahmin yapmalı
4. THE Sales_Predictor_Agent SHALL mevsimsel trendleri ve bölgesel faktörleri hesaba katmalı
5. WHEN birden fazla hedef depo uygun olduğunda, THE Transfer_Coordinator_Agent SHALL en yüksek Satış_Potansiyeli olan depoyu seçmeli
6. THE Sales_Predictor_Agent SHALL AWS Bedrock Nova_Model kullanarak satış tahminleri yapmalı

### Gereksinim 4: Ürün Yaşlandırma Yönetimi

**Kullanıcı Hikayesi:** Bir depo müdürü olarak, eski stokların (yaşlanan ürünlerin) akıllıca dağıtılmasını istiyorum, böylece ürün kayıpları minimize edilir.

#### Kabul Kriterleri

1. THE Stock_Aging_Analyzer_Agent SHALL her SKU için Yaşlandırma süresini takip etmeli
2. WHEN bir ürünün Yaşlandırma süresi kritik eşiği aştığında, THE Stock_Aging_Analyzer_Agent SHALL öncelikli transfer önerisi oluşturmalı
3. THE Stock_Aging_Analyzer_Agent SHALL ürün kategorisine göre farklı yaşlandırma eşikleri uygulamalı
4. WHEN transfer kararı alınırken, THE Transfer_Coordinator_Agent SHALL yaşlı stokları önceliklendirmeli
5. THE Stock_Aging_Analyzer_Agent SHALL yaşlandırma analizlerini günlük olarak gerçekleştirmeli

### Gereksinim 5: Agent İşbirliği ve Koordinasyon

**Kullanıcı Hikayesi:** Bir sistem mimarı olarak, agentların birbirleriyle etkili iletişim kurmasını istiyorum, böylece tutarlı ve optimize edilmiş kararlar alınır.

#### Kabul Kriterleri

1. WHEN bir Agent karar almak için bilgiye ihtiyaç duyduğunda, THE Sistem SHALL ilgili Agent'tan veri talep etmeli
2. THE Sistem SHALL agentlar arası mesajlaşma için standart bir protokol kullanmalı
3. WHEN birden fazla Agent aynı kaynağı kullanmak istediğinde, THE Sistem SHALL çakışmaları önlemeli
4. THE Sistem SHALL agent kararlarını ve iletişimlerini loglama yapmalı
5. THE Sistem SHALL AWS Bedrock Agent_Core primitives kullanarak agent koordinasyonunu sağlamalı
6. WHEN bir Agent hata ile karşılaştığında, THE Sistem SHALL diğer Agentları bilgilendirmeli

### Gereksinim 6: Stok Tutarlılığı ve Veri Bütünlüğü

**Kullanıcı Hikayesi:** Bir veri yöneticisi olarak, tüm stok verilerinin tutarlı ve doğru olmasını istiyorum, böylece yanlış kararlar alınmasının önüne geçilir.

#### Kabul Kriterleri

1. THE Sistem SHALL her transfer işleminde atomik güncellemeler yapmalı
2. WHEN bir transfer başlatıldığında, THE Sistem SHALL kaynak depoda yeterli stok olduğunu doğrulamalı
3. THE Sistem SHALL negatif stok seviyelerine izin vermemeli
4. WHEN eşzamanlı transfer istekleri olduğunda, THE Sistem SHALL veri tutarlılığını korumalı
5. THE Sistem SHALL her stok değişikliğini audit log'a kaydetmeli
6. THE Sistem SHALL günlük olarak tüm depoların stok toplamlarını doğrulamalı

### Gereksinim 7: AWS Bedrock Entegrasyonu

**Kullanıcı Hikayesi:** Bir DevOps mühendisi olarak, sistemin AWS Bedrock servisleriyle tam entegre olmasını istiyorum, böylece ölçeklenebilir ve güvenilir bir altyapı sağlanır.

#### Kabul Kriterleri

1. THE Sistem SHALL AWS Bedrock Agent_Core primitives kullanarak agentları oluşturmalı
2. THE Sistem SHALL AWS Bedrock Nova_Model'i reasoning ve karar verme için kullanmalı
3. THE Sistem SHALL AWS SDK for Agents kullanarak agent işlemlerini yönetmeli
4. THE Sistem SHALL Bedrock API çağrılarında hata yönetimi ve retry mekanizması uygulamalı
5. THE Sistem SHALL Bedrock kullanım metriklerini izlemeli ve loglama yapmalı
6. WHERE QuickSight entegrasyonu aktif olduğunda, THE Sistem SHALL agent kararlarını ve metrikleri görselleştirmeli

### Gereksinim 8: Simülasyon Verisi Üretimi ve Yönetimi

**Kullanıcı Hikayesi:** Bir geliştirici olarak, sistemin gerçekçi simülasyon verisi üretmesini ve yönetmesini istiyorum, böylece agent davranışlarını test edebilirim.

#### Kabul Kriterleri

1. THE Sistem SHALL başlangıçta 5 farklı Depo lokasyonu için veri üretmeli
2. THE Sistem SHALL 10 farklı ürün kategorisi için başlangıç verisi oluşturmalı
3. THE Sistem SHALL 100 farklı SKU için stok, fiyat ve kategori bilgisi üretmeli
4. THE Sistem SHALL her SKU için 12 aylık geçmiş satış verisi simüle etmeli
5. THE Sistem SHALL her depo için rastgele ama gerçekçi başlangıç stok seviyeleri atamalı
6. THE Sistem SHALL ürün yaşlandırma verilerini rastgele ama tutarlı şekilde üretmeli
7. THE Sistem SHALL üretilen tüm veriyi yapılandırılmış formatta (JSON/CSV) saklamalı

### Gereksinim 9: Performans ve Ölçeklenebilirlik

**Kullanıcı Hikayesi:** Bir sistem yöneticisi olarak, sistemin yüksek yük altında da performanslı çalışmasını istiyorum, böylece iş sürekliliği sağlanır.

#### Kabul Kriterleri

1. THE Sistem SHALL 1000'den fazla eşzamanlı stok sorgusunu işleyebilmeli
2. WHEN bir transfer kararı alındığında, THE Sistem SHALL 10 saniye içinde işlemi tamamlamalı
3. THE Sistem SHALL agent yanıt sürelerini izlemeli ve 5 saniyenin üzerinde uyarı vermeli
4. THE Sistem SHALL AWS Bedrock rate limitlerini yönetmeli ve aşmaktan kaçınmalı
5. THE Sistem SHALL yatay ölçeklendirme yapabilmeli

### Gereksinim 10: İnsan Müdahalesi ve Onay Mekanizması

**Kullanıcı Hikayesi:** Bir operasyon müdürü olarak, kritik kararlar için insan onayı alınmasını istiyorum, böylece kontrol ve gözetim sağlanır.

#### Kabul Kriterleri

1. WHERE yüksek değerli transferler söz konusu olduğunda, THE Sistem SHALL insan onayı talep etmeli
2. THE Sistem SHALL onay bekleyen işlemleri bir kuyrukta tutmalı
3. WHEN insan onayı alındığında, THE Sistem SHALL transfer işlemini devam ettirmeli
4. WHEN onay reddedildiğinde, THE Sistem SHALL alternatif çözümler önermeye devam etmeli
5. THE Sistem SHALL onay eşiklerini yapılandırılabilir şekilde saklamalı
6. THE Sistem SHALL hem tam otonom hem de insan gözetimli modlarda çalışabilmeli

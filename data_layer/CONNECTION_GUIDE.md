# Data Layer Bağlantı Rehberi

Bu rehber, Agent ve MCP geliştiricilerinin DynamoDB ve S3 verilerine nasıl bağlanacağını açıklar.

## AWS Bilgileri

- **Region**: `us-east-1` (varsayılan, değiştirilebilir)
- **DynamoDB**: PAY_PER_REQUEST billing, 6 tablo
- **S3 Bucket**: `warehouse-stock-mgmt-{account_id}`

## DynamoDB Tablo Şemaları

### Warehouses
```
Partition Key: warehouse_id (S)
```
```json
{
  "warehouse_id": "WH001",
  "name": "İstanbul Merkez Depo",
  "location": "İstanbul, Türkiye",
  "region": "Marmara",
  "capacity": 12000,
  "is_trade_hub": true,
  "created_at": "2024-01-01T00:00:00Z"
}
```

### Products
```
Partition Key: sku (S)
GSI: CategoryIndex → category (S)
```
```json
{
  "sku": "SKU001",
  "name": "Laptop 15.6 inch",
  "category": "Elektronik",
  "price": 15000.50,
  "aging_threshold_days": 90,
  "created_at": "2024-01-01T00:00:00Z"
}
```

### Inventory
```
Partition Key: warehouse_id (S)
Sort Key: sku (S)
```
```json
{
  "warehouse_id": "WH001",
  "sku": "SKU001",
  "quantity": 150,
  "min_threshold": 20,
  "max_threshold": 300,
  "received_date": "2024-06-15T00:00:00Z",
  "last_updated": "2025-02-12T10:00:00Z"
}
```


### SalesHistory
```
Partition Key: warehouse_id (S)
Sort Key: date_sku (S)  → format: "2024-06-15#SKU001"
```
```json
{
  "warehouse_id": "WH001",
  "date_sku": "2024-06-15#SKU001",
  "sku": "SKU001",
  "date": "2024-06-15",
  "quantity_sold": 12,
  "revenue": 180006.00
}
```

### Transfers (agentlar tarafından yazılacak)
```
Partition Key: transfer_id (S)
GSI: StatusTimeIndex → status (S) + created_at (S)
```
```json
{
  "transfer_id": "TRF-20250212-001",
  "source_warehouse": "WH001",
  "target_warehouse": "WH002",
  "sku": "SKU001",
  "quantity": 50,
  "status": "pending",
  "created_at": "2025-02-12T10:00:00Z",
  "completed_at": null,
  "initiated_by": "transfer_coordinator"
}
```
Status değerleri: `pending`, `approved`, `in_transit`, `completed`, `failed`, `cancelled`

### AgentDecisions (agentlar tarafından yazılacak)
```
Partition Key: decision_id (S)
GSI: AgentTimeIndex → agent_name (S) + timestamp (S)
```
```json
{
  "decision_id": "DEC-20250212-001",
  "agent_name": "inventory_monitor",
  "timestamp": "2025-02-12T10:00:00Z",
  "decision_type": "low_stock_alert",
  "details": { "warehouse_id": "WH002", "sku": "SKU001", "current_qty": 3 },
  "action_taken": "transfer_requested"
}
```

## S3 Bucket Yapısı

```
warehouse-stock-mgmt-{account_id}/
├── raw-data/
│   ├── warehouses.json
│   ├── categories.json
│   ├── products.json
│   ├── initial-inventory.json
│   └── problem-scenarios.json
├── sales-history/
│   ├── sales-history-full.json
│   └── sales-history-full.csv
├── agent-logs/          ← agentlar buraya yazar
└── reports/
    ├── daily/
    ├── weekly/
    └── monthly/
```

## Örnek Bağlantı Kodları (boto3)

### Stok Sorgulama
```python
import boto3

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
table = dynamodb.Table("Inventory")

# Tek depo, tek SKU
response = table.get_item(Key={"warehouse_id": "WH001", "sku": "SKU001"})
item = response["Item"]

# Bir depodaki tüm stoklar
from boto3.dynamodb.conditions import Key
response = table.query(KeyConditionExpression=Key("warehouse_id").eq("WH001"))
items = response["Items"]
```

### Satış Geçmişi Sorgulama
```python
table = dynamodb.Table("SalesHistory")

# Belirli depo, belirli tarih aralığı
response = table.query(
    KeyConditionExpression=Key("warehouse_id").eq("WH001") 
        & Key("date_sku").between("2024-06-01#", "2024-06-30#z")
)
```

### Atomik Transfer İşlemi (transact_write_items)
```python
client = boto3.client("dynamodb", region_name="us-east-1")

client.transact_write_items(
    TransactItems=[
        {
            "Update": {
                "TableName": "Inventory",
                "Key": {"warehouse_id": {"S": "WH001"}, "sku": {"S": "SKU001"}},
                "UpdateExpression": "SET quantity = quantity - :qty",
                "ConditionExpression": "quantity >= :qty",
                "ExpressionAttributeValues": {":qty": {"N": "50"}},
            }
        },
        {
            "Update": {
                "TableName": "Inventory",
                "Key": {"warehouse_id": {"S": "WH002"}, "sku": {"S": "SKU001"}},
                "UpdateExpression": "SET quantity = quantity + :qty",
                "ExpressionAttributeValues": {":qty": {"N": "50"}},
            }
        },
    ]
)
```

## Depo Bilgileri

| ID | Depo | Bölge | Kapasite | Ticaret Merkezi |
|----|------|-------|----------|-----------------|
| WH001 | İstanbul Merkez | Marmara | 12,000 | ✅ |
| WH002 | Ankara | İç Anadolu | 8,000 | ❌ |
| WH003 | İzmir | Ege | 7,000 | ❌ |
| WH004 | Antalya | Akdeniz | 5,000 | ❌ |
| WH005 | Bursa | Marmara | 6,000 | ❌ |
| WH006 | Samsun | Karadeniz | 10,000 | ✅ |

## Kategori ve SKU Aralıkları

| Kategori | SKU Aralığı | Yaşlandırma Eşiği |
|----------|-------------|-------------------|
| Elektronik | SKU001-SKU010 | 90 gün |
| Giyim | SKU011-SKU020 | 180 gün |
| Gıda | SKU021-SKU030 | 30 gün |
| Mobilya | SKU031-SKU040 | 365 gün |
| Kitap | SKU041-SKU050 | 730 gün |
| Oyuncak | SKU051-SKU060 | 180 gün |
| Spor Malzemeleri | SKU061-SKU070 | 365 gün |
| Ev Aletleri | SKU071-SKU080 | 180 gün |
| Kozmetik | SKU081-SKU090 | 365 gün |
| Otomotiv | SKU091-SKU100 | 730 gün |

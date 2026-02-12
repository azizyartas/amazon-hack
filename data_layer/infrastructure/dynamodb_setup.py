"""DynamoDB tablo oluşturma ve veri yükleme.

6 tablo: Warehouses, Products, Inventory, SalesHistory, Transfers, AgentDecisions
"""
import boto3
import json
import time
from botocore.exceptions import ClientError


REGION = "us-east-1"  # Bedrock'un aktif olduğu region

TABLE_DEFINITIONS = [
    {
        "TableName": "Warehouses",
        "KeySchema": [
            {"AttributeName": "warehouse_id", "KeyType": "HASH"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "warehouse_id", "AttributeType": "S"},
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": "Products",
        "KeySchema": [
            {"AttributeName": "sku", "KeyType": "HASH"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "sku", "AttributeType": "S"},
            {"AttributeName": "category", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "CategoryIndex",
                "KeySchema": [
                    {"AttributeName": "category", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": "Inventory",
        "KeySchema": [
            {"AttributeName": "warehouse_id", "KeyType": "HASH"},
            {"AttributeName": "sku", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "warehouse_id", "AttributeType": "S"},
            {"AttributeName": "sku", "AttributeType": "S"},
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": "SalesHistory",
        "KeySchema": [
            {"AttributeName": "warehouse_id", "KeyType": "HASH"},
            {"AttributeName": "date_sku", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "warehouse_id", "AttributeType": "S"},
            {"AttributeName": "date_sku", "AttributeType": "S"},
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": "Transfers",
        "KeySchema": [
            {"AttributeName": "transfer_id", "KeyType": "HASH"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "transfer_id", "AttributeType": "S"},
            {"AttributeName": "status", "AttributeType": "S"},
            {"AttributeName": "created_at", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "StatusTimeIndex",
                "KeySchema": [
                    {"AttributeName": "status", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": "AgentDecisions",
        "KeySchema": [
            {"AttributeName": "decision_id", "KeyType": "HASH"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "decision_id", "AttributeType": "S"},
            {"AttributeName": "agent_name", "AttributeType": "S"},
            {"AttributeName": "timestamp", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "AgentTimeIndex",
                "KeySchema": [
                    {"AttributeName": "agent_name", "KeyType": "HASH"},
                    {"AttributeName": "timestamp", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
]


def create_tables(region: str = REGION):
    """Tüm DynamoDB tablolarını oluşturur."""
    dynamodb = boto3.client("dynamodb", region_name=region)

    for table_def in TABLE_DEFINITIONS:
        table_name = table_def["TableName"]
        try:
            dynamodb.describe_table(TableName=table_name)
            print(f"  ⏭️  {table_name} zaten mevcut, atlanıyor")
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                print(f"  🔨 {table_name} oluşturuluyor...")
                dynamodb.create_table(**table_def)
                # Tablonun aktif olmasını bekle
                waiter = dynamodb.get_waiter("table_exists")
                waiter.wait(TableName=table_name)
                print(f"  ✓  {table_name} oluşturuldu")
            else:
                raise


def load_data_to_table(table_name: str, data: list, region: str = REGION):
    """JSON verisini DynamoDB tablosuna yükler (batch write)."""
    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)

    # DynamoDB float desteklemez, Decimal'e çevir
    from decimal import Decimal

    def convert_floats(obj):
        if isinstance(obj, float):
            return Decimal(str(obj))
        if isinstance(obj, dict):
            return {k: convert_floats(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [convert_floats(i) for i in obj]
        return obj

    data = convert_floats(data)

    with table.batch_writer() as batch:
        for i, item in enumerate(data):
            batch.put_item(Item=item)
            if (i + 1) % 1000 == 0:
                print(f"    ... {i + 1}/{len(data)} yüklendi")

    print(f"  ✓  {table_name}: {len(data)} kayıt yüklendi")


def load_all_data(data_dir: str = "data_layer/data", region: str = REGION):
    """Tüm JSON verilerini DynamoDB'ye yükler."""
    print("\n📤 DynamoDB'ye veri yükleniyor...\n")

    # Warehouses
    with open(f"{data_dir}/warehouses.json", "r", encoding="utf-8") as f:
        load_data_to_table("Warehouses", json.load(f), region)

    # Products
    with open(f"{data_dir}/products.json", "r", encoding="utf-8") as f:
        load_data_to_table("Products", json.load(f), region)

    # Inventory
    with open(f"{data_dir}/initial-inventory.json", "r", encoding="utf-8") as f:
        load_data_to_table("Inventory", json.load(f), region)

    # SalesHistory (büyük veri - progress göster)
    print("  ⏳ SalesHistory yükleniyor (196K+ kayıt, biraz sürebilir)...")
    with open(f"{data_dir}/sales-history.json", "r", encoding="utf-8") as f:
        load_data_to_table("SalesHistory", json.load(f), region)

    print("\n✅ Tüm veriler DynamoDB'ye yüklendi!")


def delete_tables(region: str = REGION):
    """Tüm tabloları siler (dikkatli kullan)."""
    dynamodb = boto3.client("dynamodb", region_name=region)
    for table_def in TABLE_DEFINITIONS:
        table_name = table_def["TableName"]
        try:
            dynamodb.delete_table(TableName=table_name)
            print(f"  🗑️  {table_name} silindi")
        except ClientError:
            print(f"  ⏭️  {table_name} bulunamadı, atlanıyor")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--delete":
        print("🗑️  Tablolar siliniyor...")
        delete_tables()
    else:
        print("🏗️  DynamoDB tabloları oluşturuluyor...\n")
        create_tables()
        load_all_data()

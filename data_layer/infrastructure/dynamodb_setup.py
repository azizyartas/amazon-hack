"""DynamoDB tablo oluşturma ve veri yükleme.

6 tablo: Warehouses, Products, Inventory, SalesHistory, Transfers, AgentDecisions
"""
import boto3
import json
import time
import os
import sys
from botocore.exceptions import ClientError
from botocore.config import Config

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import env_loader
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


REGION = "us-west-2"  # Bedrock'un aktif olduğu region
BOTO_CONFIG = Config(retries={"max_attempts": 3})

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
    dynamodb = boto3.client("dynamodb", region_name=region, verify=False)

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


def load_data_to_table(table_name: str, data: list, region: str = REGION, threads: int = 10):
    """JSON verisini DynamoDB tablosuna yükler (paralel batch write)."""
    from decimal import Decimal
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading

    def convert_floats(obj):
        if isinstance(obj, float):
            return Decimal(str(obj))
        if isinstance(obj, dict):
            return {k: convert_floats(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [convert_floats(i) for i in obj]
        return obj

    data = convert_floats(data)
    total = len(data)
    counter = {"done": 0}
    lock = threading.Lock()

    def upload_chunk(chunk):
        """Bir chunk'ı batch write ile yükler."""
        dynamodb = boto3.resource("dynamodb", region_name=region, verify=False)
        table = dynamodb.Table(table_name)
        with table.batch_writer() as batch:
            for item in chunk:
                batch.put_item(Item=item)
        with lock:
            counter["done"] += len(chunk)
            done = counter["done"]
        if done % 10000 < len(chunk):
            print(f"    ... {done}/{total} yüklendi")

    # 10K'lık chunk'lara böl
    chunk_size = 10000
    chunks = [data[i:i + chunk_size] for i in range(0, total, chunk_size)]

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = [executor.submit(upload_chunk, chunk) for chunk in chunks]
        for future in as_completed(futures):
            future.result()  # hata varsa raise eder

    print(f"  ✓  {table_name}: {total} kayıt yüklendi ({threads} thread)")


def _table_has_data(table_name: str, region: str = REGION) -> bool:
    """Tabloda veri var mı kontrol eder (hızlı scan, 1 item)."""
    dynamodb = boto3.client("dynamodb", region_name=region, verify=False)
    resp = dynamodb.scan(TableName=table_name, Limit=1, Select="COUNT")
    return resp.get("Count", 0) > 0


def load_all_data(data_dir: str = "data_layer/data", region: str = REGION):
    """Tüm JSON verilerini DynamoDB'ye yükler (zaten yüklüyse atlar)."""
    print("\n📤 DynamoDB'ye veri yükleniyor...\n")

    # Warehouses
    if _table_has_data("Warehouses", region):
        print("  ⏭️  Warehouses zaten dolu, atlanıyor")
    else:
        with open(f"{data_dir}/warehouses.json", "r", encoding="utf-8") as f:
            load_data_to_table("Warehouses", json.load(f), region)

    # Products
    if _table_has_data("Products", region):
        print("  ⏭️  Products zaten dolu, atlanıyor")
    else:
        with open(f"{data_dir}/products.json", "r", encoding="utf-8") as f:
            load_data_to_table("Products", json.load(f), region)

    # Inventory
    if _table_has_data("Inventory", region):
        print("  ⏭️  Inventory zaten dolu, atlanıyor")
    else:
        with open(f"{data_dir}/initial-inventory.json", "r", encoding="utf-8") as f:
            load_data_to_table("Inventory", json.load(f), region)

    # SalesHistory (büyük veri)
    if _table_has_data("SalesHistory", region):
        print("  ⏭️  SalesHistory zaten dolu, atlanıyor")
    else:
        print("  ⏳ SalesHistory yükleniyor (196K+ kayıt, paralel yükleme)...")
        with open(f"{data_dir}/sales-history.json", "r", encoding="utf-8") as f:
            load_data_to_table("SalesHistory", json.load(f), region)

    print("\n✅ Tüm veriler DynamoDB'ye yüklendi!")


def delete_tables(region: str = REGION):
    """Tüm tabloları siler (dikkatli kullan)."""
    dynamodb = boto3.client("dynamodb", region_name=region, verify=False)
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

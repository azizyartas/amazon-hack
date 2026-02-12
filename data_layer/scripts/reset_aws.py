"""Agent islemlerini geri alir.

- Transfers tablosunu temizler
- AgentDecisions tablosunu temizler
- Inventory tablosunu orijinal haline dondurur (initial-inventory.json)

Kaynak veriler (Warehouses, Products, SalesHistory) korunur.

Kullanim:
    python -m data_layer.scripts.reset_aws
"""
import sys
import os
import json

os.environ["AWS_CA_BUNDLE"] = ""
os.environ["CURL_CA_BUNDLE"] = ""
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import boto3
from botocore.exceptions import ClientError
from data_layer.infrastructure.dynamodb_setup import load_data_to_table

REGION = "us-west-2"
DATA_DIR = "data_layer/data"
AGENT_TABLES = ["Transfers", "AgentDecisions"]


def clear_table(table_name, region=REGION):
    """Tablodaki tum verileri siler (tablo yapisini korur)."""
    dynamodb = boto3.resource("dynamodb", region_name=region, verify=False)
    client = boto3.client("dynamodb", region_name=region, verify=False)
    table = dynamodb.Table(table_name)

    desc = client.describe_table(TableName=table_name)
    key_names = [k["AttributeName"] for k in desc["Table"]["KeySchema"]]

    scan_kwargs = {"ProjectionExpression": ", ".join(key_names)}
    deleted = 0

    while True:
        resp = table.scan(**scan_kwargs)
        items = resp.get("Items", [])
        if not items:
            break
        with table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={k: item[k] for k in key_names})
                deleted += 1
        if "LastEvaluatedKey" not in resp:
            break
    return deleted


def restore_inventory(region=REGION):
    """Inventory tablosunu orijinal haline dondurur."""
    inv_path = os.path.join(DATA_DIR, "initial-inventory.json")
    with open(inv_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"  Inventory: {len(data)} kayit orijinal haline donduruluyor...", flush=True)
    load_data_to_table("Inventory", data, region, threads=5)
    print(f"  OK  Inventory: {len(data)} kayit orijinal degerlerle yazildi", flush=True)


def main():
    region = os.environ.get("AWS_DEFAULT_REGION", REGION)

    print("=" * 50)
    print("Agent Islemlerini Geri Al")
    print(f"Region: {region}")
    print("=" * 50)

    # 1. Agent tablolarini temizle
    for table_name in AGENT_TABLES:
        try:
            print(f"\n  {table_name} temizleniyor...", end="", flush=True)
            deleted = clear_table(table_name, region)
            if deleted > 0:
                print(f"\r  OK  {table_name}: {deleted} kayit silindi", flush=True)
            else:
                print(f"\r  OK  {table_name}: zaten bos", flush=True)
        except ClientError as e:
            print(f"\r  FAIL {table_name}: {e.response['Error']['Message']}", flush=True)

    # 2. Inventory'yi orijinal haline dondur
    print()
    restore_inventory(region)

    print("\n" + "=" * 50)
    print("Agent islemleri geri alindi.")
    print("Korunan: Warehouses, Products, SalesHistory")
    print("Sifirlanan: Transfers, AgentDecisions, Inventory")
    print("=" * 50)


if __name__ == "__main__":
    main()

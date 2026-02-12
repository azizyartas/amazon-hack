"""AWS altyapisini dogrular - tablolar dolu mu, S3 dosyalari var mi kontrol eder.

Gercek kayit sayisi icin full scan yapar (describe_table ItemCount yaklasiktir).

Kullanim:
    python -m data_layer.scripts.verify_aws
    python -m data_layer.scripts.verify_aws --quick   # Eski hizli mod (yaklasik)
"""
import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import env_loader
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import boto3
from botocore.exceptions import ClientError

REGION = "us-west-2"
DATA_DIR = "data_layer/data"

EXPECTED_TABLES = {
    "Warehouses": 6,
    "Products": 100,
    "Inventory": 600,
    "SalesHistory": 196665,
    "Transfers": 0,
    "AgentDecisions": 0,
}

EXPECTED_S3_FILES = [
    "raw-data/warehouses.json",
    "raw-data/categories.json",
    "raw-data/products.json",
    "raw-data/initial-inventory.json",
    "sales-history/sales-history-full.json",
    "sales-history/sales-history-full.csv",
    "raw-data/problem-scenarios.json",
]


def _count_table_items(dynamodb_client, table_name):
    """Tablodaki gercek kayit sayisini full scan ile sayar."""
    total = 0
    params = {"TableName": table_name, "Select": "COUNT"}
    while True:
        resp = dynamodb_client.scan(**params)
        total += resp["Count"]
        if "LastEvaluatedKey" not in resp:
            break
        params["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return total


def _load_expected_count(table_name):
    """Kaynak JSON dosyasindan beklenen kayit sayisini okur."""
    file_map = {
        "Warehouses": "warehouses.json",
        "Products": "products.json",
        "Inventory": "initial-inventory.json",
        "SalesHistory": "sales-history.json",
    }
    if table_name not in file_map:
        return 0
    path = os.path.join(DATA_DIR, file_map[table_name])
    if not os.path.exists(path):
        return EXPECTED_TABLES.get(table_name, 0)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return len(data)


def verify_dynamodb(region=REGION, quick=False):
    """DynamoDB tablolarini kontrol eder."""
    dynamodb = boto3.client("dynamodb", region_name=region, verify=False)
    all_ok = True

    if quick:
        print("\n--- DynamoDB Dogrulama (HIZLI / yaklasik) ---\n", flush=True)
    else:
        print("\n--- DynamoDB Dogrulama (GERCEK SAYIM) ---\n", flush=True)
        print("  (SalesHistory icin bu islem 1-2 dakika surebilir)\n", flush=True)

    for table_name, default_min in EXPECTED_TABLES.items():
        try:
            resp = dynamodb.describe_table(TableName=table_name)
            status = resp["Table"]["TableStatus"]

            if status != "ACTIVE":
                print(f"  FAIL {table_name}: status={status}", flush=True)
                all_ok = False
                continue

            if default_min == 0:
                print(f"  OK   {table_name}: status=ACTIVE (bos tablo, beklenen)", flush=True)
                continue

            expected = _load_expected_count(table_name)

            if quick:
                approx_count = resp["Table"]["ItemCount"]
                if approx_count >= expected:
                    print(f"  OK   {table_name}: ~{approx_count} kayit (beklenen: {expected})", flush=True)
                elif approx_count > 0:
                    print(f"  WARN {table_name}: ~{approx_count} kayit (beklenen: {expected}) - ItemCount yaklasiktir, --quick olmadan calistirin", flush=True)
                else:
                    scan_resp = dynamodb.scan(TableName=table_name, Limit=1, Select="COUNT")
                    if scan_resp["Count"] > 0:
                        print(f"  WARN {table_name}: veri var ama ItemCount=0 (henuz guncellenmedi), --quick olmadan calistirin", flush=True)
                    else:
                        print(f"  FAIL {table_name}: tablo bos, beklenen: {expected}", flush=True)
                        all_ok = False
            else:
                print(f"  ...  {table_name}: sayiliyor...", end="", flush=True)
                actual = _count_table_items(dynamodb, table_name)
                if actual == expected:
                    print(f"\r  OK   {table_name}: {actual} kayit (beklenen: {expected}) - TAM ESLESME", flush=True)
                elif actual >= expected:
                    print(f"\r  OK   {table_name}: {actual} kayit (beklenen: {expected})", flush=True)
                else:
                    missing = expected - actual
                    pct = (actual / expected * 100) if expected > 0 else 0
                    print(f"\r  FAIL {table_name}: {actual}/{expected} kayit (%{pct:.1f}) - {missing} kayit EKSIK", flush=True)
                    all_ok = False

        except ClientError as e:
            print(f"  FAIL {table_name}: {e.response['Error']['Message']}", flush=True)
            all_ok = False
    return all_ok


def verify_s3(region=REGION):
    """S3 bucket ve dosyalarini kontrol eder."""
    from data_layer.infrastructure.s3_setup import get_bucket_name
    s3 = boto3.client("s3", region_name=region, verify=False)
    bucket_name = get_bucket_name(region)
    all_ok = True
    print(f"\n--- S3 Dogrulama ({bucket_name}) ---\n", flush=True)
    try:
        s3.head_bucket(Bucket=bucket_name)
        print(f"  OK  Bucket mevcut: {bucket_name}", flush=True)
    except ClientError:
        print(f"  FAIL Bucket bulunamadi: {bucket_name}", flush=True)
        return False
    for s3_key in EXPECTED_S3_FILES:
        try:
            resp = s3.head_object(Bucket=bucket_name, Key=s3_key)
            size_kb = resp["ContentLength"] / 1024
            print(f"  OK  {s3_key} ({size_kb:.1f} KB)", flush=True)
        except ClientError:
            print(f"  FAIL {s3_key} bulunamadi", flush=True)
            all_ok = False
    return all_ok


def main():
    region = os.environ.get("AWS_DEFAULT_REGION", REGION)
    quick = "--quick" in sys.argv

    print("=" * 50, flush=True)
    print("AWS Altyapi Dogrulama", flush=True)
    print(f"Region: {region}", flush=True)
    if quick:
        print("Mod: HIZLI (yaklasik, describe_table)", flush=True)
    else:
        print("Mod: GERCEK SAYIM (full scan)", flush=True)
    print("=" * 50, flush=True)

    db_ok = verify_dynamodb(region, quick=quick)
    s3_ok = verify_s3(region)

    print("\n" + "=" * 50, flush=True)
    if db_ok and s3_ok:
        print("SONUC: TUM KONTROLLER BASARILI", flush=True)
    else:
        print("SONUC: BAZI KONTROLLER BASARISIZ", flush=True)
        if not db_ok:
            print("  - DynamoDB sorunlari var", flush=True)
        if not s3_ok:
            print("  - S3 sorunlari var", flush=True)
    print("=" * 50, flush=True)
    return 0 if (db_ok and s3_ok) else 1


if __name__ == "__main__":
    sys.exit(main())

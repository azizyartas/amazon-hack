"""S3 bucket oluşturma ve veri yükleme.

Bucket yapısı:
  warehouse-stock-mgmt-{account_id}/
  ├── raw-data/
  ├── sales-history/
  ├── agent-logs/
  └── reports/
"""
import boto3
import json
import os
from botocore.exceptions import ClientError

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


REGION = "us-west-2"
BUCKET_PREFIX = "warehouse-stock-mgmt"


def get_bucket_name(region: str = REGION) -> str:
    """Account ID ile unique bucket adı oluşturur."""
    sts = boto3.client("sts", region_name=region, verify=False)
    account_id = sts.get_caller_identity()["Account"]
    return f"{BUCKET_PREFIX}-{account_id}"


def create_bucket(region: str = REGION) -> str:
    """S3 bucket oluşturur."""
    s3 = boto3.client("s3", region_name=region, verify=False)
    bucket_name = get_bucket_name(region)

    try:
        if region == "us-east-1":
            s3.create_bucket(Bucket=bucket_name)
        else:
            s3.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": region},
            )
        print(f"  ✓ Bucket oluşturuldu: {bucket_name}")
    except ClientError as e:
        if e.response["Error"]["Code"] in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            print(f"  ⏭️  Bucket zaten mevcut: {bucket_name}")
        else:
            raise

    return bucket_name


def upload_file(bucket_name: str, local_path: str, s3_key: str, region: str = REGION):
    """Tek dosya yükler."""
    s3 = boto3.client("s3", region_name=region, verify=False)
    s3.upload_file(local_path, bucket_name, s3_key)
    print(f"  ✓ {s3_key}")


def upload_all_data(data_dir: str = "data_layer/data", region: str = REGION):
    """Tüm veriyi S3'e yükler."""
    bucket_name = get_bucket_name(region)
    print(f"\n📤 S3'e veri yükleniyor ({bucket_name})...\n")

    file_mappings = {
        "warehouses.json": "raw-data/warehouses.json",
        "categories.json": "raw-data/categories.json",
        "products.json": "raw-data/products.json",
        "initial-inventory.json": "raw-data/initial-inventory.json",
        "sales-history.json": "sales-history/sales-history-full.json",
        "sales-history.csv": "sales-history/sales-history-full.csv",
        "problem-scenarios.json": "raw-data/problem-scenarios.json",
    }

    for local_file, s3_key in file_mappings.items():
        local_path = os.path.join(data_dir, local_file)
        if os.path.exists(local_path):
            upload_file(bucket_name, local_path, s3_key, region)
        else:
            print(f"  ⚠️  {local_path} bulunamadı, atlanıyor")

    # Boş prefix'ler oluştur (klasör yapısı)
    s3 = boto3.client("s3", region_name=region, verify=False)
    for prefix in ["agent-logs/", "reports/daily/", "reports/weekly/", "reports/monthly/"]:
        s3.put_object(Bucket=bucket_name, Key=prefix, Body=b"")
        print(f"  ✓ {prefix} (klasör)")

    print(f"\n✅ Tüm veriler S3'e yüklendi! Bucket: {bucket_name}")
    return bucket_name


def delete_bucket(region: str = REGION):
    """Bucket ve içeriğini siler (dikkatli kullan)."""
    s3 = boto3.resource("s3", region_name=region, verify=False)
    bucket_name = get_bucket_name(region)
    try:
        bucket = s3.Bucket(bucket_name)
        bucket.objects.all().delete()
        bucket.delete()
        print(f"  🗑️  {bucket_name} silindi")
    except ClientError:
        print(f"  ⏭️  {bucket_name} bulunamadı")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--delete":
        print("🗑️  S3 bucket siliniyor...")
        delete_bucket()
    else:
        print("🏗️  S3 bucket oluşturuluyor...\n")
        bucket = create_bucket()
        upload_all_data()

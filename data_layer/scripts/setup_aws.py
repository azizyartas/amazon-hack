"""AWS altyapısını kurar ve veriyi yükler.

Kullanım:
    python -m data_layer.scripts.setup_aws              # Kur ve yükle
    python -m data_layer.scripts.setup_aws --delete     # Her şeyi sil
    python -m data_layer.scripts.setup_aws --region eu-west-1  # Farklı region
"""
import sys
import os

# Proje root'unu path'e ekle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from data_layer.infrastructure.dynamodb_setup import create_tables, load_all_data, delete_tables
from data_layer.infrastructure.s3_setup import create_bucket, upload_all_data, delete_bucket


def main():
    region = "us-east-1"
    delete_mode = False

    # Argümanları parse et
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--delete":
            delete_mode = True
        elif arg == "--region" and i + 1 < len(args):
            region = args[i + 1]

    if delete_mode:
        print("🗑️  AWS kaynakları siliniyor...\n")
        print("--- DynamoDB ---")
        delete_tables(region)
        print("\n--- S3 ---")
        delete_bucket(region)
        print("\n✅ Tüm kaynaklar silindi!")
        return

    print("=" * 60)
    print("🚀 AWS Altyapı Kurulumu - Depo Stok Yönetim Sistemi")
    print(f"   Region: {region}")
    print("=" * 60)

    # 1. DynamoDB
    print("\n📊 ADIM 1: DynamoDB Tabloları")
    print("-" * 40)
    create_tables(region)

    # 2. S3
    print("\n📦 ADIM 2: S3 Bucket")
    print("-" * 40)
    bucket = create_bucket(region)

    # 3. Veri yükleme
    print("\n📤 ADIM 3: Veri Yükleme")
    print("-" * 40)
    load_all_data(region=region)
    upload_all_data(region=region)

    print("\n" + "=" * 60)
    print("✅ AWS altyapısı hazır!")
    print(f"   DynamoDB: 6 tablo oluşturuldu ve veri yüklendi")
    print(f"   S3: {bucket} oluşturuldu ve veri yüklendi")
    print(f"   Region: {region}")
    print("=" * 60)


if __name__ == "__main__":
    main()

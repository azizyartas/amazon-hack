"""Eksik SalesHistory kayitlarini tamamlar.

batch_writer + put_item idempotent oldugu icin tum veriyi tekrar yukler.
Zaten var olan kayitlar uzerine yazilir, eksikler eklenir.

Kullanim:
    python -m data_layer.scripts.reload_sales
"""
import sys
import os
import json

os.environ["AWS_CA_BUNDLE"] = ""
os.environ["CURL_CA_BUNDLE"] = ""
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from data_layer.infrastructure.dynamodb_setup import load_data_to_table

REGION = "us-west-2"
DATA_DIR = "data_layer/data"


def main():
    region = os.environ.get("AWS_DEFAULT_REGION", REGION)
    sales_path = os.path.join(DATA_DIR, "sales-history.json")

    print("=" * 50)
    print("SalesHistory Eksik Kayit Tamamlama")
    print(f"Region: {region}")
    print("=" * 50)

    print(f"\nJSON dosyasi yukleniyor: {sales_path}")
    with open(sales_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"Toplam kayit: {len(data)}")

    print(f"\nSalesHistory tablosuna yukleniyor (put_item, var olanlar uzerine yazilir)...")
    print("Bu islem birkac dakika surebilir...\n")
    load_data_to_table("SalesHistory", data, region, threads=10)

    print("\n" + "=" * 50)
    print("TAMAMLANDI! Dogrulamak icin:")
    print("  python -m data_layer.scripts.verify_aws")
    print("=" * 50)


if __name__ == "__main__":
    main()

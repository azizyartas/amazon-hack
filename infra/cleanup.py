"""
AgentCore ve IAM kaynaklarini temizler.

Kullanim:
    agentcore destroy
    python infra/cleanup.py
"""

import subprocess
import sys

import boto3
from botocore.exceptions import ClientError

ROLE_NAME = "BedrockAgentCore-WarehouseStockMgmt-ExecutionRole"
POLICY_NAME = "BedrockAgentCore-WarehouseStockMgmt-Policy"


def main():
    print("AgentCore temizlik baslatiliyor...")

    # 1. agentcore destroy
    print("\n[1/2] agentcore destroy...")
    try:
        subprocess.run(["agentcore", "destroy"], timeout=120)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"  Uyari: {e}")

    # 2. IAM temizlik
    print("\n[2/2] IAM temizlik...")
    iam = boto3.client("iam")

    try:
        iam.delete_role_policy(RoleName=ROLE_NAME, PolicyName=POLICY_NAME)
        print(f"  Policy silindi: {POLICY_NAME}")
    except ClientError as e:
        print(f"  Policy silinemedi: {e}")

    try:
        iam.delete_role(RoleName=ROLE_NAME)
        print(f"  Role silindi: {ROLE_NAME}")
    except ClientError as e:
        print(f"  Role silinemedi: {e}")

    print("\nTemizlik tamamlandi.")


if __name__ == "__main__":
    main()

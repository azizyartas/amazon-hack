"""
AgentCore Deploy Script - Depo Stok Yonetim Sistemi.

AWS CLI gerektirmez, boto3 ile IAM role olusturur ve agentcore CLI ile deploy eder.

Kullanim:
    python infra/deploy.py
"""

import json
import os
import sys
import time
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import env_loader

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import boto3
from botocore.exceptions import ClientError

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")
ROLE_NAME = "BedrockAgentCore-WarehouseStockMgmt-ExecutionRole"
POLICY_NAME = "BedrockAgentCore-WarehouseStockMgmt-Policy"

TRUST_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": "bedrock-agentcore.amazonaws.com"
            },
            "Action": "sts:AssumeRole",
        }
    ],
}

EXECUTION_POLICY_PATH = os.path.join(os.path.dirname(__file__), "agentcore_execution_policy.json")


def check_credentials():
    """AWS credential kontrolu."""
    print("\n[1/5] AWS kimlik kontrolu...")
    try:
        sts = boto3.client("sts", region_name=REGION, verify=False)
        identity = sts.get_caller_identity()
        account_id = identity["Account"]
        print(f"  Account: {account_id}")
        print(f"  ARN: {identity['Arn']}")
        print(f"  Region: {REGION}")
        return account_id
    except Exception as e:
        print(f"  HATA: AWS credentials ayarli degil veya gecersiz!")
        print(f"  Detay: {e}")
        print()
        print("  PowerShell'de credential ayarlamak icin:")
        print('    $env:AWS_DEFAULT_REGION = "us-west-2"')
        print('    $env:AWS_ACCESS_KEY_ID = "..."')
        print('    $env:AWS_SECRET_ACCESS_KEY = "..."')
        print('    $env:AWS_SESSION_TOKEN = "..."')
        sys.exit(1)


def create_iam_role(account_id: str) -> str:
    """IAM execution role olusturur veya mevcut olani kullanir."""
    print("\n[2/5] IAM Execution Role olusturuluyor...")
    iam = boto3.client("iam", region_name=REGION, verify=False)

    # Role var mi kontrol et
    try:
        resp = iam.get_role(RoleName=ROLE_NAME)
        role_arn = resp["Role"]["Arn"]
        print(f"  Role zaten mevcut: {ROLE_NAME}")
        print(f"  ARN: {role_arn}")
        return role_arn
    except iam.exceptions.NoSuchEntityException:
        pass

    # Yeni role olustur
    try:
        resp = iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(TRUST_POLICY),
            Description="AgentCore execution role for Warehouse Stock Management System",
        )
        role_arn = resp["Role"]["Arn"]
        print(f"  Role olusturuldu: {ROLE_NAME}")
        print(f"  ARN: {role_arn}")
        return role_arn
    except ClientError as e:
        print(f"  HATA: Role olusturulamadi: {e}")
        sys.exit(1)


def attach_policy():
    """Execution policy'yi role'e ekler."""
    print("\n[3/5] IAM Policy ekleniyor...")
    iam = boto3.client("iam", region_name=REGION, verify=False)

    with open(EXECUTION_POLICY_PATH) as f:
        policy_doc = f.read()

    try:
        iam.put_role_policy(
            RoleName=ROLE_NAME,
            PolicyName=POLICY_NAME,
            PolicyDocument=policy_doc,
        )
        print(f"  Policy eklendi: {POLICY_NAME}")
    except ClientError as e:
        print(f"  HATA: Policy eklenemedi: {e}")
        sys.exit(1)

    # IAM propagation bekle
    print("  IAM propagation icin 10 saniye bekleniyor...")
    time.sleep(10)


def configure_agentcore(role_arn: str):
    """agentcore configure calistirir."""
    print("\n[4/5] AgentCore configure...")
    cmd = [
        sys.executable, "-m", "bedrock_agentcore_starter_toolkit",
        "configure",
        "-e", "agentcore_app.py",
        "-r", REGION,
        "--execution-role", role_arn,
        "--non-interactive",
    ]

    # Oncelikle agentcore CLI'yi dene
    agentcore_cmd = [
        "agentcore",
        "configure",
        "-e", "agentcore_app.py",
        "-r", REGION,
        "--execution-role", role_arn,
        "--non-interactive",
    ]

    for attempt_cmd in [agentcore_cmd, cmd]:
        try:
            result = subprocess.run(
                attempt_cmd,
                capture_output=True,
                text=True,
                timeout=120,
                env={**os.environ, "AWS_CA_BUNDLE": "", "CURL_CA_BUNDLE": ""},
            )
            if result.returncode == 0:
                print("  Configure tamamlandi.")
                if result.stdout:
                    print(f"  {result.stdout.strip()[:200]}")
                return
            else:
                print(f"  Komut basarisiz (code={result.returncode})")
                if result.stderr:
                    print(f"  stderr: {result.stderr.strip()[:300]}")
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            print("  HATA: Configure timeout (120s)")
            continue

    print("  HATA: agentcore configure calistirilamadi!")
    print("  Manuel olarak calistirin:")
    print(f'    agentcore configure -e agentcore_app.py -r {REGION} --execution-role {role_arn}')
    sys.exit(1)


def deploy_agentcore():
    """agentcore deploy calistirir."""
    print("\n[5/5] AgentCore deploy baslatiliyor...")
    print("  Bu islem birkac dakika surebilir (CodeBuild + deploy)...")

    for attempt_cmd in [["agentcore", "deploy"], [sys.executable, "-m", "bedrock_agentcore_starter_toolkit", "deploy"]]:
        try:
            # Deploy'u interaktif olarak calistir (output gorunsun)
            result = subprocess.run(
                attempt_cmd,
                timeout=600,
                env={**os.environ, "AWS_CA_BUNDLE": "", "CURL_CA_BUNDLE": ""},
            )
            if result.returncode == 0:
                print("\n  Deploy tamamlandi!")
                return
            else:
                print(f"\n  Deploy basarisiz (code={result.returncode})")
                print("  Loglari kontrol edin: agentcore status")
                sys.exit(1)
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            print("  HATA: Deploy timeout (10 dakika)")
            sys.exit(1)

    print("  HATA: agentcore deploy calistirilamadi!")
    print("  Manuel olarak calistirin: agentcore deploy")
    sys.exit(1)


def main():
    print("=" * 50)
    print(" AgentCore Deploy - Depo Stok Yonetim Sistemi")
    print(f" Region: {REGION}")
    print("=" * 50)

    account_id = check_credentials()
    role_arn = create_iam_role(account_id)
    attach_policy()
    configure_agentcore(role_arn)
    deploy_agentcore()

    print()
    print("=" * 50)
    print(" DEPLOY BASARILI!")
    print("=" * 50)
    print()
    print("Test etmek icin:")
    print('  agentcore invoke \'{"prompt": "kritik stoklari goster"}\'')
    print()
    print("Programatik test:")
    print('  python infra/invoke_agent.py "kritik stoklari goster"')
    print()
    print("Durum kontrolu:")
    print("  agentcore status")
    print()
    print("Temizlik:")
    print("  agentcore destroy")
    print(f"  python infra/cleanup.py")


if __name__ == "__main__":
    main()

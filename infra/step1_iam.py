"""Adim 1: IAM Role ve Policy olustur."""
import os, json, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import env_loader
import urllib3; urllib3.disable_warnings()
import boto3

REGION = "us-west-2"
ROLE_NAME = "BedrockAgentCore-WarehouseStockMgmt-ExecutionRole"
POLICY_NAME = "BedrockAgentCore-WarehouseStockMgmt-Policy"

TRUST = json.dumps({
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
        "Action": "sts:AssumeRole",
    }],
})

iam = boto3.client("iam", region_name=REGION, verify=False)

# Role olustur veya mevcut olani kullan
try:
    r = iam.get_role(RoleName=ROLE_NAME)
    print(f"Role zaten mevcut: {r['Role']['Arn']}")
except iam.exceptions.NoSuchEntityException:
    r = iam.create_role(
        RoleName=ROLE_NAME,
        AssumeRolePolicyDocument=TRUST,
        Description="AgentCore execution role for Warehouse Stock Management",
    )
    print(f"Role olusturuldu: {r['Role']['Arn']}")

# Policy ekle
with open("infra/agentcore_execution_policy.json") as f:
    pol = f.read()

iam.put_role_policy(
    RoleName=ROLE_NAME,
    PolicyName=POLICY_NAME,
    PolicyDocument=pol,
)
print(f"Policy eklendi: {POLICY_NAME}")

sts = boto3.client("sts", region_name=REGION, verify=False)
account_id = sts.get_caller_identity()["Account"]
role_arn = f"arn:aws:iam::{account_id}:role/{ROLE_NAME}"
print(f"Role ARN: {role_arn}")
print("IAM TAMAM - Adim 2'ye gecebilirsiniz")

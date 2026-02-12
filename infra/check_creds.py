"""Credential kontrol - boto3 ile."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import env_loader
import boto3
try:
    sts = boto3.client("sts", region_name="us-west-2", verify=False)
    i = sts.get_caller_identity()
    print(f"Account: {i['Account']}")
    print(f"ARN: {i['Arn']}")
except Exception as e:
    print(f"HATA: {e}")
    sys.exit(1)

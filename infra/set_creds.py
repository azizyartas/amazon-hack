"""Credential'lari set edip STS kontrolu yapar."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import env_loader

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import boto3
sts = boto3.client("sts", region_name="us-west-2", verify=False)
identity = sts.get_caller_identity()
print(f"Account: {identity['Account']}")
print(f"ARN: {identity['Arn']}")
print("Credentials OK!")

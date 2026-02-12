"""Verify runner - credential'lari environment'tan okur."""
import os

# AWS credentials should be set via environment variables or AWS CLI profile
# Do NOT hardcode credentials here
# Export them in your shell before running:
#   export AWS_DEFAULT_REGION=us-west-2
#   export AWS_ACCESS_KEY_ID=your-key
#   export AWS_SECRET_ACCESS_KEY=your-secret
#   export AWS_SESSION_TOKEN=your-token

if not os.environ.get("AWS_DEFAULT_REGION"):
    os.environ["AWS_DEFAULT_REGION"] = "us-west-2"

import sys
sys.path.insert(0, ".")
from data_layer.scripts.verify_aws import main
sys.exit(main())

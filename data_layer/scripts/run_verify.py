"""Verify runner - credential'lari .env'den okur."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import env_loader

import sys
sys.path.insert(0, ".")
from data_layer.scripts.verify_aws import main
sys.exit(main())

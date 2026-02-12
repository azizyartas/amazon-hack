"""Merkezi .env yukleyici. Tum scriptler bunu import etsin."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Proje kokundeki .env dosyasini bul ve yukle
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path, override=False)

# SSL workaround (kurumsal proxy/self-signed cert)
os.environ["AWS_CA_BUNDLE"] = ""
os.environ["CURL_CA_BUNDLE"] = ""

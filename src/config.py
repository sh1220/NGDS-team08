"""Environment configuration."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090").rstrip("/")
LOKI_URL = os.getenv("LOKI_URL", "http://localhost:3100").rstrip("/")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "semantic-obs")

CATALOG_DIR = Path(os.getenv("CATALOG_DIR", ROOT / "catalog"))

# Defaults substituted into catalog placeholders
TARGET_NAMESPACE = os.getenv("TARGET_NAMESPACE", "ngds")
TARGET_POD = os.getenv("TARGET_POD", "postgres-.*")
TARGET_CONTAINER = os.getenv("TARGET_CONTAINER", "postgres")
# node filesystem that holds the postgres PVC ('/' for local-path style storage)
DATA_MOUNTPOINT = os.getenv("DATA_MOUNTPOINT", "/")

HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "15"))

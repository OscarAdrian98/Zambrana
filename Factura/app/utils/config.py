import sys
import os
from pathlib import Path

APP_NAME = "FacturaPro"


def get_base_dir():
    if os.environ.get("FACTURA_DATA_ROOT"):
        return Path(os.environ["FACTURA_DATA_ROOT"]).resolve()
    if getattr(sys, "frozen", False):
        # Ejecutándose como .exe
        return Path(os.getenv("LOCALAPPDATA")) / APP_NAME
    else:
        # Desarrollo
        return Path(__file__).resolve().parents[2]


BASE_DIR = get_base_dir()
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "facturacion_app.db"
LICENSE_PATH = DATA_DIR / "license.key"
LOGS_DIR = BASE_DIR / "logs"
BACKUP_DIR = BASE_DIR / "backups"
REMESAS_DIR = BASE_DIR / "remesas"

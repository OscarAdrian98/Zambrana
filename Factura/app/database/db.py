import sqlite3
from app.utils.config import DATA_DIR, DB_PATH


def get_connection():
    """
    Devuelve una conexión a la base de datos SQLite.
    Asegura que la carpeta data exista antes de conectar.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)

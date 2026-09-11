"""
db/sqlserver_ambar.py - Conexion sincronica a SQL Server Ambar via pyodbc.
"""
import logging
import threading
from contextlib import contextmanager

import pyodbc

from config import get_settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_connections: list[pyodbc.Connection] = []
_max_connections: int = 5


def init_pool() -> None:
    """Inicializa el pool de conexiones SQL Server."""
    global _connections
    s = get_settings()
    conn_str = s.ambar_connection_string
    try:
        with _lock:
            initial_connections = min(3, _max_connections)
            for _ in range(initial_connections):
                conn = pyodbc.connect(conn_str, timeout=5)
                conn.autocommit = False
                _connections.append(conn)
        logger.info("Pool SQL Server Ambar inicializado (%d conexiones)", len(_connections))
    except Exception as exc:
        logger.error("Error iniciando pool SQL Server Ambar: %s", exc)
        raise


def close_pool() -> None:
    global _connections
    with _lock:
        for conn in _connections:
            try:
                conn.close()
            except Exception:
                pass
        _connections.clear()
    logger.info("Pool SQL Server Ambar cerrado")


def _get_raw_connection() -> pyodbc.Connection:
    """Obtiene o crea una conexion del pool."""
    s = get_settings()
    with _lock:
        if _connections:
            conn = _connections.pop()
            try:
                conn.cursor().execute("SELECT 1")
                return conn
            except Exception:
                logger.warning("Conexion Ambar invalida, creando una nueva")

        conn = pyodbc.connect(s.ambar_connection_string, timeout=5)
        conn.autocommit = False
        return conn


def _return_connection(conn: pyodbc.Connection) -> None:
    """Devuelve una conexion al pool."""
    with _lock:
        if len(_connections) < _max_connections:
            _connections.append(conn)
        else:
            conn.close()


@contextmanager
def get_connection():
    """Context manager sincronico para SQL Server con commit/rollback."""
    conn = _get_raw_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _return_connection(conn)

"""
db/mysql_prestashop.py - Pool de conexiones async para MySQL PrestaShop.
"""
import logging
from contextlib import asynccontextmanager

import aiomysql

from config import get_settings

logger = logging.getLogger(__name__)
_pool: aiomysql.Pool | None = None


async def init_pool() -> None:
    global _pool
    s = get_settings()

    if not s.ps_mysql_is_test:
        raise RuntimeError(
            "Configuracion invalida: PS_MYSQL_IS_TEST debe ser true para evitar uso de produccion"
        )

    try:
        _pool = await aiomysql.create_pool(
            host=s.ps_mysql_host,
            port=s.ps_mysql_port,
            user=s.ps_mysql_user,
            password=s.ps_mysql_password,
            db=s.ps_mysql_db,
            charset="utf8mb4",
            autocommit=True,
            connect_timeout=5,
            minsize=1,
            maxsize=s.ps_mysql_pool_size,
        )
        logger.info("Pool MySQL PrestaShop inicializado (solo lectura en esta fase)")
    except Exception as exc:
        logger.error("Error iniciando pool MySQL PrestaShop: %s", exc)
        raise


async def close_pool() -> None:
    global _pool
    if _pool:
        _pool.close()
        await _pool.wait_closed()
        logger.info("Pool MySQL PrestaShop cerrado")


@asynccontextmanager
async def get_connection():
    """Context manager que devuelve una conexion del pool."""
    if _pool is None:
        raise RuntimeError("Pool MySQL PrestaShop no inicializado")
    async with _pool.acquire() as conn:
        yield conn

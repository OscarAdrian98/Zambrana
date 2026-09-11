"""
db/mysql_b2b.py - Pool de conexiones async para MySQL AppB2B.
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
    try:
        _pool = await aiomysql.create_pool(
            host=s.b2b_mysql_host,
            port=s.b2b_mysql_port,
            user=s.b2b_mysql_user,
            password=s.b2b_mysql_password,
            db=s.b2b_mysql_db,
            charset="utf8mb4",
            autocommit=True,
            connect_timeout=5,
            minsize=1,
            maxsize=s.b2b_mysql_pool_size,
        )
        logger.info("Pool MySQL B2B inicializado")
    except Exception as exc:
        logger.error("Error iniciando pool MySQL B2B: %s", exc)
        raise


async def close_pool() -> None:
    global _pool
    if _pool:
        _pool.close()
        await _pool.wait_closed()
        logger.info("Pool MySQL B2B cerrado")


@asynccontextmanager
async def get_connection():
    if _pool is None:
        raise RuntimeError("Pool MySQL B2B no inicializado")
    async with _pool.acquire() as conn:
        yield conn

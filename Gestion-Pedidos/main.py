"""
main.py - Entry point de la aplicacion FastAPI.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import get_settings
from app.utils.logging_config import setup_logging
from app.db import mysql_prestashop, mysql_b2b, sqlserver_ambar
from app.routes.pedidos import router as pedidos_router

settings = get_settings()
setup_logging(debug=settings.app_debug)
logger = logging.getLogger(__name__)


def _log_startup_error(
    db_name: str, exc: Exception, debug: bool, optional: bool = False
) -> None:
    if debug:
        logger.exception("No se pudo iniciar %s", db_name)
        return
    level = logger.warning if optional else logger.error
    level("No se pudo iniciar %s: %s", db_name, exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa recursos al arrancar y los cierra al parar."""
    logger.info("Iniciando Gestion Pedidos PrestaShop <-> Ambar...")
    logger.info(
        "Entorno activo: PS=%s (%s/%s) | AMBAR=%s (%s/%s) | READ_ONLY=%s",
        settings.prestashop_env_label,
        settings.ps_mysql_host,
        settings.ps_mysql_db,
        settings.ambar_env_label,
        settings.ambar_server_target,
        settings.ambar_sqlserver_db,
        settings.app_read_only,
    )

    db_status = {
        "prestashop": False,
        "b2b": False,
        "ambar": False,
    }

    try:
        await mysql_prestashop.init_pool()
        db_status["prestashop"] = True
    except Exception as exc:
        _log_startup_error("MySQL PrestaShop", exc, settings.app_debug, optional=False)

    try:
        await mysql_b2b.init_pool()
        db_status["b2b"] = True
    except Exception as exc:
        _log_startup_error("MySQL B2B", exc, settings.app_debug, optional=True)

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, sqlserver_ambar.init_pool)
        db_status["ambar"] = True
    except Exception as exc:
        _log_startup_error("SQL Server Ambar", exc, settings.app_debug, optional=False)

    app.state.db_status = db_status
    logger.info("Estado conexiones: %s", db_status)

    yield

    logger.info("Cerrando conexiones...")
    await mysql_prestashop.close_pool()
    await mysql_b2b.close_pool()
    sqlserver_ambar.close_pool()
    logger.info("Aplicacion cerrada")


app = FastAPI(
    title="Gestion Pedidos PrestaShop <-> Ambar",
    description="Sistema de gestion de pedidos web con integracion ERP Ambar",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.settings = settings
app.state.db_status = {
    "prestashop": False,
    "b2b": False,
    "ambar": False,
}

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(pedidos_router)


@app.get("/health")
async def health():
    runtime_settings = app.state.settings
    return {
        "status": "ok",
        "app": "Gestion Pedidos",
        "version": "1.0.0",
        "db_status": app.state.db_status,
        "environment": runtime_settings.environment_context,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.app_port,
        reload=settings.app_debug,
        log_level="debug" if settings.app_debug else "info",
    )

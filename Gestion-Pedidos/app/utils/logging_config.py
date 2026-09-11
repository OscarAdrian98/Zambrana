"""
utils/logging_config.py — Logging estructurado para trazabilidad completa.
Registra búsquedas, coincidencias, inserts y errores con contexto.
"""
import logging
import sys
from datetime import datetime


def setup_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler consola
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.setLevel(level)

    # Handler archivo (rotación diaria simple)
    log_filename = f"logs/gestion_pedidos_{datetime.now():%Y%m%d}.log"
    try:
        import os
        os.makedirs("logs", exist_ok=True)
        file_handler = logging.FileHandler(log_filename, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        handlers = [console, file_handler]
    except Exception:
        handlers = [console]

    logging.basicConfig(level=level, handlers=handlers)

    # Silenciar loggers ruidosos
    logging.getLogger("aiomysql").setLevel(logging.WARNING)
    logging.getLogger("pyodbc").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

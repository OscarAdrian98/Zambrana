"""Logging local con rotación acotada para ejecución operativa."""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[2]


def rutas_logs() -> dict[str, str]:
    if os.environ.get("STOCK_ENV") == "operational":
        carpeta = Path(os.environ.get("STOCK_LOG_DIR", "logs"))
        if not carpeta.is_absolute():
            carpeta = RAIZ / carpeta
        return {
            "general": str(carpeta / "stock2-general.log"),
            "resumen": str(carpeta / "stock2-resumen.log"),
            "errores": str(carpeta / "stock2-errores.log"),
        }
    return {
        "general": str(RAIZ / "Registro-Stock-Hoy.log"),
        "resumen": str(RAIZ / "Resumen-Stock.log"),
        "errores": str(RAIZ / "Registro-Stock-Hoy.log"),
    }


def _handler(ruta: str, *, nivel: int) -> RotatingFileHandler:
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        ruta,
        maxBytes=10 * 1024 * 1024,
        backupCount=14,
        encoding="utf-8",
    )
    handler.setLevel(nivel)
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )
    return handler


_rutas = rutas_logs()
_root = logging.getLogger()
_root.setLevel(logging.INFO)
if not any(getattr(h, "_stock2_general", False) for h in _root.handlers):
    general = _handler(_rutas["general"], nivel=logging.INFO)
    general._stock2_general = True
    _root.addHandler(general)
    if _rutas["errores"] != _rutas["general"]:
        errores = _handler(_rutas["errores"], nivel=logging.ERROR)
        errores._stock2_errores = True
        _root.addHandler(errores)

logger_funciones_especificas = logging.getLogger("FuncionesEspecificas")
logger_funciones_especificas.setLevel(logging.INFO)
logger_funciones_especificas.propagate = False
if not any(
    getattr(h, "_stock2_resumen", False)
    for h in logger_funciones_especificas.handlers
):
    resumen = _handler(_rutas["resumen"], nivel=logging.INFO)
    resumen._stock2_resumen = True
    logger_funciones_especificas.addHandler(resumen)


def borrar_archivo_log():
    """Compatibilidad: rota mediante handlers; no borra logs operativos."""

    logging.info("La limpieza manual de logs está desactivada; se usa rotación")

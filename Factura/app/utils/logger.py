import logging
from logging.handlers import RotatingFileHandler

from app.utils.config import LOGS_DIR

LOG_FILE = LOGS_DIR / "app.log"


# ==================================================
# CONFIGURAR LOGGER GLOBAL
# ==================================================
def setup_logger():
    """
    Configura el logger global de la aplicación.
    Usa archivo rotativo para evitar crecimiento infinito.
    """

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Evitar duplicar handlers si ya está configurado
    if logger.handlers:
        return logger

    handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=2 * 1024 * 1024,  # 2MB por archivo
        backupCount=5,  # Máximo 5 archivos rotados
        encoding="utf-8",
    )

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger

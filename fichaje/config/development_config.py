"""Configuración segura para el entorno local de desarrollo."""

import os
from urllib.parse import quote_plus

from sqlalchemy.engine import make_url


LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost"})
DEVELOPMENT_DATABASE = "fichaje_dev"
DEVELOPMENT_USER = "fichaje_dev"
DEVELOPMENT_PORT = 3306


def validate_development_database_uri(uri):
    parsed = make_url(uri)
    if not parsed.drivername.startswith("mysql"):
        raise RuntimeError("Development must use local MySQL/MariaDB.")
    if parsed.host not in LOCAL_HOSTS:
        raise RuntimeError("Development database host must be local.")
    if parsed.port != DEVELOPMENT_PORT:
        raise RuntimeError("Development database port must be 3306.")
    if parsed.database != DEVELOPMENT_DATABASE:
        raise RuntimeError("Development database must be fichaje_dev.")
    if parsed.username != DEVELOPMENT_USER:
        raise RuntimeError("Development database user must be fichaje_dev.")
    return parsed


def load_development_config(environ=None):
    environ = os.environ if environ is None else environ
    host = environ.get("FICHAJE_DEV_DB_HOST", "127.0.0.1")
    database = environ.get("FICHAJE_DEV_DB_NAME", DEVELOPMENT_DATABASE)
    user = environ.get("FICHAJE_DEV_DB_USER", DEVELOPMENT_USER)
    password = environ.get("FICHAJE_DEV_DB_PASSWORD")
    secret_key = environ.get("FICHAJE_DEV_SECRET_KEY")

    if not password:
        raise RuntimeError("Missing local development database password.")
    if not secret_key:
        raise RuntimeError("Missing local development Flask secret.")

    uri = (
        "mysql+pymysql://"
        f"{quote_plus(user)}:{quote_plus(password)}@{host}:{DEVELOPMENT_PORT}/"
        f"{database}?charset=utf8mb4"
    )
    validate_development_database_uri(uri)

    return {
        "FICHAJE_ENV": "development",
        "TESTING": False,
        "SECRET_KEY": secret_key,
        "SQLALCHEMY_DATABASE_URI": uri,
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "ALLOW_EMAILS": False,
        "ALLOW_DISCORD": False,
        "ALLOW_PUSH": False,
        "ALLOW_AUTOFICHAJE": False,
        "DEVELOPMENT_BANNER": (
            "ENTORNO DE DESARROLLO — DATOS LOCALES ANONIMIZADOS"
        ),
    }

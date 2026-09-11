"""Diagnóstico agregado y de solo lectura previo a la migración del email."""

import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


CONSULTA = text(
    """
    SELECT COUNT(*) AS filas,
           (
               SELECT COUNT(*) FROM (
                   SELECT 1 FROM usuarios
                   GROUP BY BINARY email HAVING COUNT(*) > 1
               ) AS exactos
           ) AS grupos_exactos,
           (
               SELECT COUNT(*) FROM (
                   SELECT 1 FROM usuarios
                   GROUP BY LOWER(TRIM(email)) HAVING COUNT(*) > 1
               ) AS normalizados
           ) AS grupos_normalizados,
           SUM(email IS NULL) AS nulos,
           SUM(TRIM(email) = '') AS vacios,
           SUM(BINARY email <> BINARY TRIM(email)) AS espacios_laterales,
           SUM(BINARY email <> BINARY LOWER(email)) AS mayusculas
    FROM usuarios
    """
)

INDICADORES_BLOQUEANTES = (
    "grupos_exactos",
    "grupos_normalizados",
    "nulos",
    "vacios",
    "espacios_laterales",
    "mayusculas",
)


def validar_entorno(environ=None):
    environ = os.environ if environ is None else environ
    if environ.get("FICHAJE_EMAIL_PREFLIGHT") != "1":
        raise RuntimeError("El preflight requiere autorización explícita.")
    uri = environ.get("FICHAJE_EMAIL_PREFLIGHT_DB_URL")
    if not uri:
        raise RuntimeError("Falta la URI explícita del preflight.")

    destino = make_url(uri)
    if destino.drivername != "mysql+pymysql":
        raise RuntimeError("El preflight sólo admite MySQL/MariaDB.")
    if not destino.host or not destino.database or not destino.username:
        raise RuntimeError("El destino del preflight está incompleto.")
    if destino.username.casefold() == "root":
        raise RuntimeError("El preflight no admite el usuario root.")
    return uri


def ejecutar_preflight(uri):
    motor = create_engine(uri, pool_pre_ping=True)
    try:
        with motor.connect() as conexion:
            conexion.execute(text("SET TRANSACTION READ ONLY"))
            fila = conexion.execute(CONSULTA).mappings().one()
            conexion.rollback()
            return {clave: int(valor or 0) for clave, valor in fila.items()}
    finally:
        motor.dispose()


def tiene_bloqueos(resultado):
    return any(resultado.get(indicador, 0) > 0 for indicador in INDICADORES_BLOQUEANTES)


def main():
    resultado = ejecutar_preflight(validar_entorno())
    for clave, valor in resultado.items():
        print(f"{clave}={valor}")
    return 2 if tiene_bloqueos(resultado) else 0


if __name__ == "__main__":
    raise SystemExit(main())

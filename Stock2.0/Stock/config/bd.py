"""Conexiones de Stock 2.0 con perfil, propósito y base verificados."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Dict, Optional

import pymysql


ENTORNO_VALIDACION = "laragon_validation"
ENTORNO_VALIDACION_REMOTA = "remote_test_validation"
ENTORNO_PRUEBA_PROVEEDORES_OPERATIVOS = (
    "operational_providers_test_prestashop"
)
ENTORNO_OPERATIVO = "operational"
ENTORNOS_PERMITIDOS = {
    ENTORNO_VALIDACION,
    ENTORNO_VALIDACION_REMOTA,
    ENTORNO_PRUEBA_PROVEEDORES_OPERATIVOS,
    ENTORNO_OPERATIVO,
}

TIPO_PRESTASHOP = "prestashop"
TIPO_PROVEEDORES = "proveedores"
TIPOS_CONEXION = {TIPO_PRESTASHOP, TIPO_PROVEEDORES}

BASE_PRESTASHOP_LOCAL = "prestashop_test"
BASE_PROVEEDORES_LOCAL = "stock_proveedores_test"
BASE_PRESTASHOP_PRUEBAS_REMOTA = "prestashop_remote_test"
BASE_PROVEEDORES_PRUEBAS_LOCAL = "stock_proveedores_test"
BASE_PRESTASHOP_OPERATIVA = "prestashop_example"
BASE_PROVEEDORES_OPERATIVA = "stock_proveedores"
BASES_LOCALES_PERMITIDAS = {
    BASE_PRESTASHOP_LOCAL,
    BASE_PROVEEDORES_LOCAL,
}
HOSTS_LOCALES = {"127.0.0.1", "localhost", "::1"}


def _cargar_archivo_entorno(nombre: str) -> None:
    """Carga un archivo local ignorado sin sobrescribir el entorno efectivo."""

    ruta = Path(__file__).resolve().parents[2] / nombre
    if not ruta.is_file():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip())


_PERFIL_SOLICITADO = os.environ.get("STOCK_ENV")
if _PERFIL_SOLICITADO == ENTORNO_VALIDACION:
    _cargar_archivo_entorno(".env.validation")
elif _PERFIL_SOLICITADO == ENTORNO_VALIDACION_REMOTA:
    _cargar_archivo_entorno(".env.remote-test")
elif _PERFIL_SOLICITADO == ENTORNO_PRUEBA_PROVEEDORES_OPERATIVOS:
    _cargar_archivo_entorno(".env.operational-providers-test")
elif _PERFIL_SOLICITADO == ENTORNO_OPERATIVO:
    _cargar_archivo_entorno(".env.operational")


def _entero_entorno(nombre: str, predeterminado: int) -> int:
    valor = os.environ.get(nombre)
    return predeterminado if valor is None else int(valor)


def _configuracion_comun(*, host: str, puerto: int, usuario: str,
                         password: str, base: str) -> dict:
    return {
        "host": host,
        "port": puerto,
        "user": usuario,
        "password": password,
        "database": base,
        "connect_timeout": 30,
        "read_timeout": 300,
        "write_timeout": 300,
        "charset": "utf8mb4",
        "init_command": "SET NAMES utf8mb4",
    }


def _configuracion_local(base: str) -> dict:
    return _configuracion_comun(
        host=os.environ.get("LARAGON_MYSQL_HOST", "127.0.0.1"),
        puerto=_entero_entorno("LARAGON_MYSQL_PORT", 3306),
        usuario=os.environ.get("LARAGON_MYSQL_USER", ""),
        password=os.environ.get("LARAGON_MYSQL_PASSWORD", ""),
        base=base,
    )


def _configuracion_prestashop_pruebas_remota() -> dict:
    return _configuracion_comun(
        host=os.environ.get("STOCK_TEST_PRESTASHOP_MYSQL_HOST", ""),
        puerto=_entero_entorno("STOCK_TEST_PRESTASHOP_MYSQL_PORT", 3306),
        usuario=os.environ.get("STOCK_TEST_PRESTASHOP_MYSQL_USER", ""),
        password=os.environ.get("STOCK_TEST_PRESTASHOP_MYSQL_PASSWORD", ""),
        base=BASE_PRESTASHOP_PRUEBAS_REMOTA,
    )


def _configuracion_operativa(base: str) -> dict:
    """Construye un perfil sin valores operativos predeterminados."""

    return _configuracion_comun(
        host=os.environ.get("STOCK_OPERATIONAL_MYSQL_HOST", ""),
        puerto=_entero_entorno("STOCK_OPERATIONAL_MYSQL_PORT", 3306),
        usuario=os.environ.get("STOCK_OPERATIONAL_MYSQL_USER", ""),
        password=os.environ.get("STOCK_OPERATIONAL_MYSQL_PASSWORD", ""),
        base=base,
    )


def _configuracion_proveedores_operativa() -> dict:
    """Configura exclusivamente la base remota de proveedores operativa."""

    return _configuracion_comun(
        host=os.environ.get("STOCK_OPERATIONAL_PROVIDERS_MYSQL_HOST", ""),
        puerto=_entero_entorno(
            "STOCK_OPERATIONAL_PROVIDERS_MYSQL_PORT",
            3306,
        ),
        usuario=os.environ.get("STOCK_OPERATIONAL_PROVIDERS_MYSQL_USER", ""),
        password=os.environ.get(
            "STOCK_OPERATIONAL_PROVIDERS_MYSQL_PASSWORD",
            "",
        ),
        base=BASE_PROVEEDORES_OPERATIVA,
    )


def _configuracion_bloqueada() -> dict:
    return _configuracion_comun(
        host="",
        puerto=3306,
        usuario="",
        password="",
        base="",
    )


def _seleccionar_configuraciones(perfil: Optional[str]):
    if perfil == ENTORNO_VALIDACION:
        return (
            BASE_PRESTASHOP_LOCAL,
            BASE_PROVEEDORES_LOCAL,
            _configuracion_local(BASE_PRESTASHOP_LOCAL),
            _configuracion_local(BASE_PROVEEDORES_LOCAL),
        )
    if perfil == ENTORNO_VALIDACION_REMOTA:
        return (
            BASE_PRESTASHOP_PRUEBAS_REMOTA,
            BASE_PROVEEDORES_PRUEBAS_LOCAL,
            _configuracion_prestashop_pruebas_remota(),
            _configuracion_local(BASE_PROVEEDORES_PRUEBAS_LOCAL),
        )
    if perfil == ENTORNO_PRUEBA_PROVEEDORES_OPERATIVOS:
        return (
            BASE_PRESTASHOP_PRUEBAS_REMOTA,
            BASE_PROVEEDORES_OPERATIVA,
            _configuracion_prestashop_pruebas_remota(),
            _configuracion_proveedores_operativa(),
        )
    if perfil == ENTORNO_OPERATIVO:
        return (
            BASE_PRESTASHOP_OPERATIVA,
            BASE_PROVEEDORES_OPERATIVA,
            _configuracion_operativa(BASE_PRESTASHOP_OPERATIVA),
            _configuracion_operativa(BASE_PROVEEDORES_OPERATIVA),
        )
    return None, None, _configuracion_bloqueada(), _configuracion_bloqueada()


(
    BASE_PRESTASHOP_ACTIVA,
    BASE_PROVEEDORES_ACTIVA,
    prestashop_config,
    proveedores_config,
) = _seleccionar_configuraciones(_PERFIL_SOLICITADO)


def es_entorno_operativo() -> bool:
    return os.environ.get("STOCK_ENV") == ENTORNO_OPERATIVO


def es_entorno_validacion_remota() -> bool:
    return os.environ.get("STOCK_ENV") == ENTORNO_VALIDACION_REMOTA


def es_entorno_prueba_proveedores_operativos() -> bool:
    return (
        os.environ.get("STOCK_ENV")
        == ENTORNO_PRUEBA_PROVEEDORES_OPERATIVOS
    )


def _host_local(config: dict) -> bool:
    return str(config.get("host", "")).strip().casefold() in HOSTS_LOCALES


def validar_entorno_local_configurado() -> None:
    """Impide abrir conexiones si no se activó el entorno Laragon."""

    if os.environ.get("STOCK_ENV") != ENTORNO_VALIDACION:
        raise RuntimeError(
            "Entorno bloqueado: STOCK_ENV debe ser laragon_validation"
        )
    if not prestashop_config.get("user") or not proveedores_config.get("user"):
        raise RuntimeError("Falta LARAGON_MYSQL_USER")
    if not _host_local(prestashop_config) or not _host_local(
        proveedores_config
    ):
        raise RuntimeError("El perfil Laragon exige hosts locales")
    if (
        prestashop_config.get("database") != BASE_PRESTASHOP_LOCAL
        or proveedores_config.get("database") != BASE_PROVEEDORES_LOCAL
    ):
        raise RuntimeError("Configuración local con bases inesperadas")


def validar_entorno_remoto_configurado() -> None:
    """Valida la pareja remota/local sin aceptar equivalencias por conjunto."""

    if os.environ.get("STOCK_ENV") != ENTORNO_VALIDACION_REMOTA:
        raise RuntimeError(
            "Entorno bloqueado: STOCK_ENV debe ser remote_test_validation"
        )
    if (
        not prestashop_config.get("host")
        or not prestashop_config.get("user")
        or not prestashop_config.get("password")
    ):
        raise RuntimeError(
            "Falta la configuración externa de PrestaShop de pruebas"
        )
    if _host_local(prestashop_config):
        raise RuntimeError("PrestaShop de pruebas no puede usar un host local")
    if prestashop_config.get("database") != BASE_PRESTASHOP_PRUEBAS_REMOTA:
        raise RuntimeError("La base remota debe ser prestashop_remote_test")
    if not proveedores_config.get("user"):
        raise RuntimeError("Falta LARAGON_MYSQL_USER")
    if not _host_local(proveedores_config):
        raise RuntimeError("Proveedores debe usar un host Laragon local")
    if proveedores_config.get("database") != BASE_PROVEEDORES_PRUEBAS_LOCAL:
        raise RuntimeError("La base local debe ser stock_proveedores_test")


def validar_entorno_prueba_proveedores_operativos_configurado() -> None:
    """Valida prestashop_remote_test remoto con stock_proveedores remoto."""

    if (
        os.environ.get("STOCK_ENV")
        != ENTORNO_PRUEBA_PROVEEDORES_OPERATIVOS
    ):
        raise RuntimeError(
            "Entorno bloqueado: STOCK_ENV debe ser "
            "operational_providers_test_prestashop"
        )
    for tipo, config in (
        (TIPO_PRESTASHOP, prestashop_config),
        (TIPO_PROVEEDORES, proveedores_config),
    ):
        if (
            not config.get("host")
            or not config.get("user")
            or not config.get("password")
        ):
            raise RuntimeError(
                f"Falta la configuración externa de {tipo}"
            )
        if _host_local(config):
            raise RuntimeError(
                f"El perfil intermedio rechaza host local para {tipo}"
            )
    if prestashop_config.get("database") != BASE_PRESTASHOP_PRUEBAS_REMOTA:
        raise RuntimeError(
            "PrestaShop debe ser exclusivamente prestashop_remote_test"
        )
    if prestashop_config.get("database") == BASE_PRESTASHOP_OPERATIVA:
        raise RuntimeError("prestashop_example está prohibida en esta prueba")
    if proveedores_config.get("database") != BASE_PROVEEDORES_OPERATIVA:
        raise RuntimeError(
            "Proveedores debe ser exclusivamente stock_proveedores"
        )


def validar_entorno_configurado() -> None:
    """Valida el perfil completo antes de permitir una conexión."""

    perfil = os.environ.get("STOCK_ENV")
    if perfil not in ENTORNOS_PERMITIDOS or perfil != _PERFIL_SOLICITADO:
        raise RuntimeError(f"Perfil de Stock no autorizado: {perfil!r}")
    if perfil == ENTORNO_VALIDACION:
        validar_entorno_local_configurado()
        return
    if perfil == ENTORNO_VALIDACION_REMOTA:
        validar_entorno_remoto_configurado()
        return
    if perfil == ENTORNO_PRUEBA_PROVEEDORES_OPERATIVOS:
        validar_entorno_prueba_proveedores_operativos_configurado()
        return
    if (
        not prestashop_config.get("host")
        or not prestashop_config.get("user")
        or not prestashop_config.get("password")
    ):
        raise RuntimeError("Falta la configuración operativa externa de MySQL")
    if _host_local(prestashop_config):
        raise RuntimeError("El perfil operativo rechaza hosts locales")
    if (
        prestashop_config.get("database") != BASE_PRESTASHOP_OPERATIVA
        or proveedores_config.get("database") != BASE_PROVEEDORES_OPERATIVA
    ):
        raise RuntimeError("Bases operativas inesperadas")


def _base_esperada_por_tipo(tipo_conexion: str) -> Optional[str]:
    if tipo_conexion == TIPO_PRESTASHOP:
        return BASE_PRESTASHOP_ACTIVA
    if tipo_conexion == TIPO_PROVEEDORES:
        return BASE_PROVEEDORES_ACTIVA
    return None


def _config_esperada_por_tipo(tipo_conexion: str) -> Optional[dict]:
    if tipo_conexion == TIPO_PRESTASHOP:
        return prestashop_config
    if tipo_conexion == TIPO_PROVEEDORES:
        return proveedores_config
    return None


def validar_objetivo_conexion(
    config: Dict,
    *,
    base_esperada: str,
    tipo_conexion: str,
) -> None:
    """Impide intercambiar diccionarios o propósitos de conexión."""

    validar_entorno_configurado()
    if tipo_conexion not in TIPOS_CONEXION:
        raise RuntimeError(f"Tipo de conexión no autorizado: {tipo_conexion!r}")
    base_del_tipo = _base_esperada_por_tipo(tipo_conexion)
    config_del_tipo = _config_esperada_por_tipo(tipo_conexion)
    if base_esperada != base_del_tipo:
        raise RuntimeError(
            f"Base inesperada para {tipo_conexion}: {base_esperada!r}"
        )
    if config.get("database") != base_del_tipo:
        raise RuntimeError(
            f"Configuración intercambiada para {tipo_conexion}"
        )
    for clave in ("host", "port", "user", "password", "database"):
        if config.get(clave) != config_del_tipo.get(clave):
            raise RuntimeError(
                f"Configuración no autorizada para {tipo_conexion}"
            )


def obtener_base_activa(conexion) -> Optional[str]:
    with conexion.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        fila = cursor.fetchone()
    return fila[0] if fila else None


def validar_conexion_local(conexion, base_esperada: str) -> str:
    """Compatibilidad para las herramientas exclusivamente locales."""

    validar_entorno_local_configurado()
    tipos = {
        BASE_PRESTASHOP_LOCAL: TIPO_PRESTASHOP,
        BASE_PROVEEDORES_LOCAL: TIPO_PROVEEDORES,
    }
    tipo_conexion = tipos.get(base_esperada)
    if tipo_conexion is None:
        raise RuntimeError(f"Base local no permitida: {base_esperada!r}")
    return validar_conexion_configurada(
        conexion,
        base_esperada,
        tipo_conexion=tipo_conexion,
    )


def validar_conexion_configurada(
    conexion,
    base_esperada: str,
    *,
    tipo_conexion: str,
) -> str:
    """Comprueba propósito y base efectiva mediante SELECT DATABASE()."""

    validar_entorno_configurado()
    base_del_tipo = _base_esperada_por_tipo(tipo_conexion)
    if tipo_conexion not in TIPOS_CONEXION or base_esperada != base_del_tipo:
        raise RuntimeError(
            f"Objetivo no autorizado para {tipo_conexion}: {base_esperada!r}"
        )
    activa = obtener_base_activa(conexion)
    if activa != base_esperada:
        raise RuntimeError(
            f"Base {tipo_conexion} inesperada: {activa!r}; se esperaba "
            f"{base_esperada!r}"
        )
    return activa


def _cerrar_sin_error(conexion) -> None:
    if conexion is None:
        return
    try:
        conexion.close()
    except pymysql.Error:
        pass


def crear_conexion_con_reintentos(
    config: Dict,
    *,
    base_esperada: str,
    tipo_conexion: str,
    max_intentos: int = 3,
    espera: int = 5,
) -> Optional[pymysql.Connection]:
    validar_objetivo_conexion(
        config,
        base_esperada=base_esperada,
        tipo_conexion=tipo_conexion,
    )
    for intento in range(max_intentos):
        conexion = None
        try:
            conexion = pymysql.connect(**config)
            validar_conexion_configurada(
                conexion,
                base_esperada,
                tipo_conexion=tipo_conexion,
            )
            with conexion.cursor() as cursor:
                cursor.execute("SET SESSION net_read_timeout=300")
                cursor.execute("SET SESSION net_write_timeout=300")
                cursor.execute("SET SESSION wait_timeout=300")
                cursor.execute("SET SESSION interactive_timeout=300")
            setattr(conexion, "_stock_tipo_conexion", tipo_conexion)
            setattr(conexion, "_stock_base_esperada", base_esperada)
            print(f"Conectado a la base autorizada {base_esperada}")
            return conexion
        except pymysql.Error as error:
            _cerrar_sin_error(conexion)
            print(
                f"Conexión de {tipo_conexion}, intento "
                f"{intento + 1}/{max_intentos}: {type(error).__name__}"
            )
            if intento < max_intentos - 1:
                time.sleep(espera)
            else:
                raise
        except Exception:
            _cerrar_sin_error(conexion)
            raise
    return None


def conectar_bd(
    config: Dict,
    *,
    base_esperada: str,
    tipo_conexion: str,
) -> Optional[pymysql.Connection]:
    try:
        return crear_conexion_con_reintentos(
            config,
            base_esperada=base_esperada,
            tipo_conexion=tipo_conexion,
        )
    except pymysql.Error as error:
        print(
            f"Error de conexión de {tipo_conexion}: "
            f"{type(error).__name__}"
        )
        return None


def conectar_prestashop() -> Optional[pymysql.Connection]:
    return conectar_bd(
        prestashop_config,
        base_esperada=BASE_PRESTASHOP_ACTIVA,
        tipo_conexion=TIPO_PRESTASHOP,
    )


def conectar_proveedores() -> Optional[pymysql.Connection]:
    return conectar_bd(
        proveedores_config,
        base_esperada=BASE_PROVEEDORES_ACTIVA,
        tipo_conexion=TIPO_PROVEEDORES,
    )


def reconectar_bd_si_necesario(
    conexion: pymysql.Connection,
    config: Dict,
    *,
    base_esperada: str,
    tipo_conexion: str,
) -> Optional[pymysql.Connection]:
    validar_objetivo_conexion(
        config,
        base_esperada=base_esperada,
        tipo_conexion=tipo_conexion,
    )
    try:
        conexion.ping(reconnect=True)
        validar_conexion_configurada(
            conexion,
            base_esperada,
            tipo_conexion=tipo_conexion,
        )
        return conexion
    except (pymysql.Error, AttributeError):
        _cerrar_sin_error(conexion)
        return crear_conexion_con_reintentos(
            config,
            base_esperada=base_esperada,
            tipo_conexion=tipo_conexion,
        )


def ejecutar_query_con_reintentos(
    conexion: pymysql.Connection,
    query: str,
    params=None,
    *,
    config: Dict,
    base_esperada: str,
    tipo_conexion: str,
    max_intentos: int = 3,
):
    validar_objetivo_conexion(
        config,
        base_esperada=base_esperada,
        tipo_conexion=tipo_conexion,
    )
    for intento in range(max_intentos):
        try:
            if not conexion.open:
                conexion = reconectar_bd_si_necesario(
                    conexion,
                    config,
                    base_esperada=base_esperada,
                    tipo_conexion=tipo_conexion,
                )
            validar_conexion_configurada(
                conexion,
                base_esperada,
                tipo_conexion=tipo_conexion,
            )
            with conexion.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchall()
        except pymysql.Error as error:
            if (
                "MySQL server has gone away" in str(error)
                and intento < max_intentos - 1
            ):
                time.sleep(5)
                conexion = reconectar_bd_si_necesario(
                    conexion,
                    config,
                    base_esperada=base_esperada,
                    tipo_conexion=tipo_conexion,
                )
            else:
                raise


def cerrar_conexion(
    conexion: Optional[pymysql.Connection],
    *,
    tipo_conexion: Optional[str] = None,
):
    if conexion and getattr(conexion, "open", False):
        tipo = tipo_conexion or getattr(
            conexion,
            "_stock_tipo_conexion",
            "base de datos",
        )
        try:
            conexion.close()
            print(f"Conexión de {tipo} cerrada")
        except pymysql.Error as error:
            print(
                f"Error al cerrar conexión de {tipo}: "
                f"{type(error).__name__}"
            )

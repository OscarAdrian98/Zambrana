"""Defensas para la futura ejecución operativa.

El módulo no abre conexiones ni activa el perfil. Solo valida conexiones ya
abiertas y gestiona un bloqueo de sesión cuando ``STOCK_ENV=operational``.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path

from config.lote_validacion import (
    PROVEEDORES_EXCLUIDOS_VALIDACION,
    PROVEEDORES_OPERATIVOS_VALIDACION,
)


BASE_PRESTASHOP_OPERATIVA = "prestashop_example"
BASE_PRESTASHOP_PRUEBAS_REMOTA = "prestashop_remote_test"
BASE_PROVEEDORES_OPERATIVA = "stock_proveedores"
BLOQUEO_OPERATIVO = "stock2_variantes_operativo"
PROVEEDORES_OPERATIVOS = PROVEEDORES_OPERATIVOS_VALIDACION
PROVEEDORES_EXCLUIDOS = PROVEEDORES_EXCLUIDOS_VALIDACION
TABLAS_PRESTASHOP_REQUERIDAS = {
    "ps_manufacturer",
    "ps_product",
    "ps_product_attribute",
    "ps_product_attribute_shop",
    "ps_product_lang",
    "ps_product_shop",
    "ps_product_supplier",
    "ps_stock_available",
    "ps_supplier",
}
TABLAS_PRESTASHOP_MODIFICABLES = (
    "ps_product",
    "ps_product_shop",
    "ps_product_attribute",
    "ps_product_attribute_shop",
    "ps_product_lang",
    "ps_product_supplier",
    "ps_stock_available",
)
SECRETOS_OPERATIVOS_REQUERIDOS = (
    "STOCK_OPERATIONAL_MYSQL_HOST",
    "STOCK_OPERATIONAL_MYSQL_USER",
    "STOCK_OPERATIONAL_MYSQL_PASSWORD",
    "SECRET_MASTER_PASSWORD",
    "SECRET_SALT",
    "STOCK_SMTP_HOST",
    "STOCK_SMTP_USER",
    "STOCK_SMTP_PASSWORD",
    "STOCK_EMAIL_TO",
)

COLUMNAS_PRODUCTOS = {
    "id_producto",
    "id_proveedor",
    "id_marca",
    "referencia_producto",
    "ean_producto",
    "stock_cantidad_producto",
    "stock_txt_producto",
    "hay_stock_producto",
    "fecha_disponibilidad_producto",
    "fecha_actualizacion_producto",
}
COLUMNAS_VARIANTES = {
    "id_variante",
    "id_proveedor",
    "id_marca",
    "referencia_producto",
    "ean_producto",
    "clave_variante",
    "stock_cantidad_producto",
    "stock_txt_producto",
    "hay_stock_producto",
    "fecha_disponibilidad_producto",
    "fecha_actualizacion_producto",
    "ultima_ejecucion_id",
    "presente_ultima_ejecucion",
    "fecha_creacion",
    "fecha_modificacion",
}
COLUMNAS_VARIANTES_ADITIVAS_MULTIMARCA = {
    "id_configuracion_origen",
    "estado_clasificacion_marca",
    "metodo_resolucion_marca",
}
INDICES_VARIANTES = {
    "PRIMARY": ("id_variante",),
    "uk_variante_proveedor_ref_clave": (
        "id_proveedor",
        "referencia_producto",
        "clave_variante",
    ),
    "idx_variante_proveedor_ean": ("id_proveedor", "ean_producto"),
    "idx_variante_proveedor_ejecucion": (
        "id_proveedor",
        "ultima_ejecucion_id",
    ),
    "idx_variante_proveedor_presente": (
        "id_proveedor",
        "presente_ultima_ejecucion",
    ),
}


class MigracionAusenteError(RuntimeError):
    """La tabla de variantes aún no existe."""


class MigracionIncompletaError(RuntimeError):
    """La estructura existe, pero no coincide con la aprobada."""


class EjecucionConcurrenteError(RuntimeError):
    """Otra instancia del sincronizador nuevo conserva el bloqueo."""


def validar_secretos_operativos() -> None:
    """Falla antes de conectar si falta configuración externa obligatoria."""

    ausentes = [
        nombre
        for nombre in SECRETOS_OPERATIVOS_REQUERIDOS
        if not os.environ.get(nombre, "").strip()
    ]
    if ausentes:
        raise RuntimeError(
            "Configuración operativa externa incompleta: "
            + ", ".join(ausentes)
        )


def _identidad_servidor(conexion, base_esperada: str) -> dict:
    with conexion.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        base = cursor.fetchone()[0]
        cursor.execute("SELECT VERSION()")
        version = str(cursor.fetchone()[0])
        cursor.execute("SELECT CURRENT_USER()")
        usuario = str(cursor.fetchone()[0])
    if base != base_esperada:
        raise RuntimeError(
            f"Base activa inesperada: {base!r}; se esperaba {base_esperada!r}"
        )
    if not version or not usuario:
        raise RuntimeError("No se pudo identificar versión o usuario SQL")
    return {
        "database": base,
        "version": version,
        "mariadb": "mariadb" in version.casefold(),
        "current_user": usuario,
    }


def _validar_tablas_prestashop(conexion) -> list[str]:
    with conexion.cursor() as cursor:
        cursor.execute(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA=DATABASE()"
        )
        presentes = {str(fila[0]) for fila in cursor.fetchall()}
    faltan = sorted(TABLAS_PRESTASHOP_REQUERIDAS - presentes)
    if faltan:
        raise MigracionIncompletaError(
            f"Faltan tablas PrestaShop requeridas: {faltan}"
        )
    return sorted(TABLAS_PRESTASHOP_REQUERIDAS)


def _validar_configuraciones_proveedores(conexion) -> dict[int, int]:
    placeholders = ",".join(["%s"] * len(PROVEEDORES_OPERATIVOS))
    with conexion.cursor() as cursor:
        cursor.execute(
            "SELECT id_proveedor, COUNT(*) FROM configuracion_proveedores "
            f"WHERE id_proveedor IN ({placeholders}) GROUP BY id_proveedor",
            tuple(PROVEEDORES_OPERATIVOS),
        )
        conteos = {int(fila[0]): int(fila[1]) for fila in cursor.fetchall()}
    faltan = sorted(set(PROVEEDORES_OPERATIVOS) - set(conteos))
    if faltan:
        raise RuntimeError(
            f"Proveedores operativos sin configuración: {faltan}"
        )
    return conteos


def _privilegios_para_base(conexion, base: str) -> set[str]:
    with conexion.cursor() as cursor:
        cursor.execute("SHOW GRANTS FOR CURRENT_USER()")
        concesiones = [str(fila[0]) for fila in cursor.fetchall()]
    permisos = set()
    objetivos = {"*.*", f"{base}.*"}
    for concesion in concesiones:
        normalizada = concesion.replace("`", "").upper()
        if " ON " not in normalizada:
            continue
        cabecera, resto = normalizada.split(" ON ", 1)
        objetivo = resto.split(" TO ", 1)[0].strip()
        objetivo = re.sub(r"\\([_%\\])", r"\1", objetivo)
        if objetivo not in {valor.upper() for valor in objetivos}:
            continue
        privilegios = cabecera.removeprefix("GRANT ").strip()
        if "ALL PRIVILEGES" in privilegios or privilegios == "ALL":
            return {"ALL"}
        permisos.update(
            permiso.strip() for permiso in privilegios.split(",")
        )
    return permisos


def _exigir_permisos(conexion, base: str, requeridos: set[str]) -> list[str]:
    permisos = _privilegios_para_base(conexion, base)
    faltan = set() if "ALL" in permisos else requeridos - permisos
    if faltan:
        raise RuntimeError(
            f"Permisos insuficientes en {base}: faltan {sorted(faltan)}"
        )
    return sorted(requeridos)


def _validar_directorio_logs() -> dict:
    raiz = Path(__file__).resolve().parents[2]
    ruta = Path(os.environ.get("STOCK_LOG_DIR", "logs"))
    if not ruta.is_absolute():
        ruta = raiz / ruta
    ruta.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=ruta, prefix=".preflight-", delete=True):
        pass
    libres = shutil.disk_usage(ruta).free
    minimo = int(os.environ.get("STOCK_MIN_FREE_MB", "1024")) * 1024 * 1024
    if libres < minimo:
        raise RuntimeError(
            f"Espacio libre insuficiente en logs: {libres} bytes"
        )
    return {"ruta": str(ruta), "libre_bytes": libres, "minimo_bytes": minimo}


def _validar_bloqueo_disponible(conexion) -> None:
    with conexion.cursor() as cursor:
        cursor.execute("SELECT IS_FREE_LOCK(%s)", (BLOQUEO_OPERATIVO,))
        fila = cursor.fetchone()
    if not fila or fila[0] != 1:
        raise EjecucionConcurrenteError(
            "GET_LOCK operativo ocupado por otra ejecución Stock2.0"
        )


def _base_activa(conexion) -> str | None:
    with conexion.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        fila = cursor.fetchone()
    return fila[0] if fila else None


def validar_base_operativa(conexion, esperada: str) -> str:
    if esperada not in {
        BASE_PRESTASHOP_OPERATIVA,
        BASE_PROVEEDORES_OPERATIVA,
    }:
        raise RuntimeError(f"Base operativa no autorizada: {esperada!r}")
    activa = _base_activa(conexion)
    if activa != esperada:
        raise RuntimeError(
            f"Base activa inesperada: {activa!r}; se esperaba {esperada!r}"
        )
    return activa


def _inventario_esquema(conexion) -> tuple[dict, dict, dict]:
    with conexion.cursor() as cursor:
        cursor.execute(
            """
            SELECT TABLE_NAME, COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME IN ('productos', 'productos_variantes')
            ORDER BY TABLE_NAME, ORDINAL_POSITION
            """
        )
        columnas = {"productos": set(), "productos_variantes": set()}
        for tabla, columna in cursor.fetchall():
            columnas.setdefault(str(tabla), set()).add(str(columna))

        cursor.execute(
            """
            SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME IN ('productos', 'productos_variantes')
            ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX
            """
        )
        indices: dict[str, dict[str, list[str]]] = {
            "productos": {},
            "productos_variantes": {},
        }
        unicidad: dict[str, dict[str, int]] = {
            "productos": {},
            "productos_variantes": {},
        }
        for tabla, nombre, no_unico, _posicion, columna in cursor.fetchall():
            tabla = str(tabla)
            nombre = str(nombre)
            indices.setdefault(tabla, {}).setdefault(nombre, []).append(
                str(columna)
            )
            unicidad.setdefault(tabla, {})[nombre] = int(no_unico)

        cursor.execute(
            """
            SELECT TABLE_NAME, ENGINE, TABLE_COLLATION, ROW_FORMAT
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME IN ('productos', 'productos_variantes')
            """
        )
        tablas = {
            str(fila[0]): {
                "engine": fila[1],
                "collation": fila[2],
                "row_format": fila[3],
            }
            for fila in cursor.fetchall()
        }
    return columnas, {"columnas": indices, "unicidad": unicidad}, tablas


def validar_migracion_operativa(conexion) -> dict:
    """Valida la tabla nueva y la compatibilidad exacta del resumen."""

    validar_base_operativa(conexion, BASE_PROVEEDORES_OPERATIVA)
    columnas, inventario_indices, tablas = _inventario_esquema(conexion)
    columnas_productos = columnas.get("productos", set())
    if columnas_productos != COLUMNAS_PRODUCTOS:
        faltan = sorted(COLUMNAS_PRODUCTOS - columnas_productos)
        sobran = sorted(columnas_productos - COLUMNAS_PRODUCTOS)
        raise MigracionIncompletaError(
            f"Estructura de productos incompatible: faltan={faltan}, "
            f"sobran={sobran}"
        )
    indices_productos = inventario_indices["columnas"].get("productos", {})
    unicidad_productos = inventario_indices["unicidad"].get("productos", {})
    if tuple(indices_productos.get("PRIMARY", ())) != ("id_producto",):
        raise MigracionIncompletaError("PRIMARY de productos inesperada")
    if (
        tuple(indices_productos.get("pk_ref_x_prov", ()))
        != ("id_proveedor", "referencia_producto")
        or unicidad_productos.get("pk_ref_x_prov") != 0
    ):
        raise MigracionIncompletaError(
            "Falta la clave única histórica pk_ref_x_prov"
        )
    tabla_productos = tablas.get("productos")
    if (
        not tabla_productos
        or str(tabla_productos.get("engine", "")).casefold() != "innodb"
    ):
        raise MigracionIncompletaError("productos no usa InnoDB")

    columnas_variantes = columnas.get("productos_variantes", set())
    if not columnas_variantes and "productos_variantes" not in tablas:
        raise MigracionAusenteError("No existe productos_variantes")
    faltan_columnas = sorted(COLUMNAS_VARIANTES - columnas_variantes)
    sobran_columnas = sorted(
        columnas_variantes
        - COLUMNAS_VARIANTES
        - COLUMNAS_VARIANTES_ADITIVAS_MULTIMARCA
    )
    indices_variantes = inventario_indices["columnas"].get(
        "productos_variantes", {}
    )
    faltan_indices = {
        nombre: columnas_esperadas
        for nombre, columnas_esperadas in INDICES_VARIANTES.items()
        if tuple(indices_variantes.get(nombre, ())) != columnas_esperadas
    }
    unicidad_variantes = inventario_indices["unicidad"].get(
        "productos_variantes", {}
    )
    unicidad_invalida = any(
        unicidad_variantes.get(nombre) != (0 if nombre in {
            "PRIMARY",
            "uk_variante_proveedor_ref_clave",
        } else 1)
        for nombre in INDICES_VARIANTES
    )
    tabla_variantes = tablas.get("productos_variantes")
    motor_invalido = (
        not tabla_variantes
        or str(tabla_variantes.get("engine", "")).casefold() != "innodb"
    )
    formato_invalido = (
        not tabla_variantes
        or str(tabla_variantes.get("row_format", "")).casefold() != "dynamic"
        or str(tabla_variantes.get("collation", "")).casefold()
        not in {"utf8_general_ci", "utf8mb3_general_ci"}
    )
    if (
        faltan_columnas
        or sobran_columnas
        or faltan_indices
        or unicidad_invalida
        or motor_invalido
        or formato_invalido
    ):
        raise MigracionIncompletaError(
            "Migración incompleta: "
            f"faltan_columnas={faltan_columnas}, "
            f"sobran_columnas={sobran_columnas}, "
            f"indices={sorted(faltan_indices)}, "
            f"unicidad_invalida={unicidad_invalida}, "
            f"motor_invalido={motor_invalido}, "
            f"formato_invalido={formato_invalido}"
        )
    return {
        "productos_columnas": len(columnas_productos),
        "variantes_columnas": len(columnas_variantes),
        "variantes_indices": sorted(INDICES_VARIANTES),
        "engine": tabla_variantes["engine"],
        "collation": tabla_variantes["collation"],
        "row_format": tabla_variantes["row_format"],
    }


def validar_preflight_operativo(conexion_prestashop, conexion_proveedores) -> dict:
    validar_secretos_operativos()
    identidad_prestashop = _identidad_servidor(
        conexion_prestashop, BASE_PRESTASHOP_OPERATIVA
    )
    identidad_proveedores = _identidad_servidor(
        conexion_proveedores, BASE_PROVEEDORES_OPERATIVA
    )
    estructura = validar_migracion_operativa(conexion_proveedores)
    tablas = _validar_tablas_prestashop(conexion_prestashop)
    configuraciones = _validar_configuraciones_proveedores(
        conexion_proveedores
    )
    permisos = {
        "prestashop": _exigir_permisos(
            conexion_prestashop,
            BASE_PRESTASHOP_OPERATIVA,
            {"SELECT", "UPDATE"},
        ),
        "proveedores": _exigir_permisos(
            conexion_proveedores,
            BASE_PROVEEDORES_OPERATIVA,
            {"SELECT", "INSERT", "UPDATE"},
        ),
    }
    directorio_logs = _validar_directorio_logs()
    _validar_bloqueo_disponible(conexion_proveedores)
    return {
        "prestashop": identidad_prestashop,
        "proveedores": identidad_proveedores,
        "estructura": estructura,
        "tablas_prestashop": tablas,
        "configuraciones_proveedores": configuraciones,
        "permisos": permisos,
        "logs": directorio_logs,
        "lock_disponible": True,
    }


def validar_preflight_prueba_proveedores_operativos(
    conexion_prestashop,
    conexion_proveedores,
) -> dict:
    """Protege la prueba con PrestaShop de test y proveedores operativos."""

    activa_prestashop = _base_activa(conexion_prestashop)
    if activa_prestashop != BASE_PRESTASHOP_PRUEBAS_REMOTA:
        raise RuntimeError(
            f"Base PrestaShop inesperada: {activa_prestashop!r}; "
            "se esperaba 'prestashop_remote_test'"
        )
    if activa_prestashop == BASE_PRESTASHOP_OPERATIVA:
        raise RuntimeError("prestashop_example está prohibida en esta prueba")
    estructura = validar_migracion_operativa(conexion_proveedores)
    return {
        "prestashop": BASE_PRESTASHOP_PRUEBAS_REMOTA,
        "proveedores": BASE_PROVEEDORES_OPERATIVA,
        "estructura": estructura,
    }


@dataclass
class BloqueoEjecucionOperativa:
    """Bloqueo asesor MySQL ligado a la conexión de proveedores."""

    conexion: object
    timeout_segundos: int = 5
    nombre: str = BLOQUEO_OPERATIVO
    adquirido: bool = False
    _mutex: threading.Lock = field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
    )

    def adquirir(self) -> None:
        with self._mutex:
            if self.timeout_segundos < 0 or self.timeout_segundos > 300:
                raise ValueError("Timeout de bloqueo fuera del rango 0..300")
            with self.conexion.cursor() as cursor:
                cursor.execute(
                    "SELECT GET_LOCK(%s, %s)",
                    (self.nombre, self.timeout_segundos),
                )
                fila = cursor.fetchone()
            if not fila or fila[0] != 1:
                raise EjecucionConcurrenteError(
                    "Otra ejecución del sincronizador nuevo está activa"
                )
            self.adquirido = True

    def liberar(self) -> None:
        with self._mutex:
            if not self.adquirido:
                return
            try:
                with self.conexion.cursor() as cursor:
                    cursor.execute("SELECT RELEASE_LOCK(%s)", (self.nombre,))
                    cursor.fetchone()
            finally:
                self.adquirido = False

    def validar_propiedad(self) -> None:
        """Confirma que esta misma sesion conserva el bloqueo nombrado."""

        with self._mutex:
            if not self.adquirido:
                raise EjecucionConcurrenteError(
                    "El bloqueo externo no esta adquirido"
                )
            with self.conexion.cursor() as cursor:
                cursor.execute(
                    "SELECT CONNECTION_ID(), IS_USED_LOCK(%s)",
                    (self.nombre,),
                )
                fila = cursor.fetchone()
            if not fila or fila[1] is None or int(fila[0]) != int(fila[1]):
                raise EjecucionConcurrenteError(
                    "La sesion externa ya no conserva el bloqueo operativo"
                )

    def __enter__(self):
        self.adquirir()
        return self

    def __exit__(self, _tipo, _error, _traza):
        self.liberar()
        return False


@dataclass
class VigilanteBloqueoOperativo:
    """Mantiene viva una sesión GET_LOCK durante una fase remota larga."""

    bloqueo: BloqueoEjecucionOperativa
    intervalo_segundos: float = 30.0
    _detener: threading.Event = field(
        default_factory=threading.Event,
        init=False,
        repr=False,
    )
    _hilo: threading.Thread | None = field(default=None, init=False, repr=False)
    _error: BaseException | None = field(default=None, init=False, repr=False)

    def _vigilar(self) -> None:
        while not self._detener.wait(self.intervalo_segundos):
            try:
                self.bloqueo.validar_propiedad()
            except BaseException as error:  # se propaga en el hilo principal
                self._error = error
                self._detener.set()

    def iniciar(self) -> None:
        if self.intervalo_segundos <= 0:
            raise ValueError("El intervalo de keepalive debe ser positivo")
        if self._hilo is not None:
            raise RuntimeError("El vigilante ya está iniciado")
        self.bloqueo.validar_propiedad()
        self._hilo = threading.Thread(
            target=self._vigilar,
            name="stock2-get-lock-keepalive",
            daemon=True,
        )
        self._hilo.start()

    def detener(self) -> None:
        self._detener.set()
        if self._hilo is not None:
            self._hilo.join(timeout=max(self.intervalo_segundos * 2, 1.0))
            self._hilo = None

    def comprobar(self) -> None:
        if self._error is not None:
            raise EjecucionConcurrenteError(
                "Falló el keepalive del bloqueo operativo"
            ) from self._error
        self.bloqueo.validar_propiedad()

    def __enter__(self):
        self.iniciar()
        return self

    def __exit__(self, tipo, _error, _traza):
        self.detener()
        if tipo is None:
            self.comprobar()
        return False

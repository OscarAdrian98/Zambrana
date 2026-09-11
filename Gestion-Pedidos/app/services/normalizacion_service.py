"""
services/normalizacion_service.py — Normalización centralizada de datos.

MEJORA vs legacy: en el PHP la normalización estaba duplicada en línea dentro
de matches.php con str_replace repetidos. Aquí es un módulo único, testeado
y reutilizable por todos los servicios.
"""
import re
import unicodedata
import logging

from app.services.cliente_fiscal_service import resolve_ambar_country

logger = logging.getLogger(__name__)

# Tabla de transliteración específica para Ambar (conserva Ñ, Ç)
_QUITAR_NOMBRE = str.maketrans(
    "ÁÉÍÓÚáéíóú",
    "AEIOUaeiou",
)
_QUITAR_DIR = str.maketrans(
    "ÁÉÍÓÚáéíóú",
    "AEIOUaeiou",
)

# Abreviaciones de dirección iguales al legacy
_ABREVIATURAS_DIR = [
    (r"\bPOLIGONO\b", "POL."),
    (r"\bINDUSTRIAL\b", "IND."),
    (r"\bURBANIZACION\b", "URB."),
    (r"\bNUMERO\b", "N."),
    (r"\bAVENIDA\b", "AVDA."),
    (r"\bCARRETERA\b", "CRTA."),
    (r"\bC/\b", "CALLE "),
]

_RE_ESPACIOS = re.compile(r"\s+")
_RE_CARACTERES_PELIGROSOS = re.compile(r"['\"]")


def normalizar_para_comparar(texto: str | None) -> str:
    """
    Normaliza un texto para comparación (PRO, matching, etc.).
    Elimina acentos, colapsa espacios, pone en mayúsculas.
    Equivalente a la función normalizarNombre() del PHP legacy.
    """
    if not texto:
        return ""
    s = str(texto)
    # Quitar NBSP y tabulaciones
    s = s.replace("\xa0", " ").replace("&nbsp;", " ")
    s = s.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    s = _RE_ESPACIOS.sub(" ", s).strip().upper()
    # Eliminar diacríticos via NFD
    nfd = unicodedata.normalize("NFD", s)
    s = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return s


def normalizar_nombre_ambar(apellidos: str, nombre: str) -> str:
    """
    Formatea nombre para insertar en Ambar: APELLIDOS NOMBRE en mayúsculas,
    transliterando vocales acentuadas pero conservando Ñ.
    Equivalente al bloque de NOMBRE en matches.php.
    """
    completo = f"{apellidos} {nombre}".strip()
    completo = completo.translate(_QUITAR_NOMBRE)
    completo = _RE_ESPACIOS.sub(" ", completo).strip().upper()
    # Ñ no se transliteró — conservarla
    completo = completo.replace("N~", "Ñ")  # por si acaso
    completo = _limpiar_comillas(completo)
    return completo[:80]  # Ambar trunca a 80 chars


def normalizar_direccion_ambar(linea1: str, linea2: str = "") -> str:
    """
    Normaliza una dirección para Ambar: mayúsculas, abreviaciones,
    sin caracteres peligrosos. Equivalente al bloque DIRECCIÓN del PHP.
    """
    dir_completa = f"{linea1} {linea2}".strip()
    dir_completa = dir_completa.replace("#", "").replace("&", "Y")
    dir_completa = dir_completa.translate(_QUITAR_DIR)
    dir_completa = dir_completa.upper()
    for patron, reemplazo in _ABREVIATURAS_DIR:
        dir_completa = re.sub(patron, reemplazo, dir_completa)
    dir_completa = _RE_ESPACIOS.sub(" ", dir_completa).strip()
    dir_completa = _limpiar_comillas(dir_completa)
    return dir_completa[:60]


def normalizar_ciudad_ambar(ciudad: str) -> str:
    """Normaliza ciudad para Ambar."""
    ciudad = ciudad.translate(_QUITAR_DIR)
    ciudad = _RE_ESPACIOS.sub(" ", ciudad).strip().upper()
    ciudad = _limpiar_comillas(ciudad)
    return ciudad[:30]


def normalizar_provincia_ambar(provincia: str) -> str:
    """Normaliza provincia para Ambar."""
    provincia = provincia.translate(_QUITAR_DIR)
    provincia = _RE_ESPACIOS.sub(" ", provincia).strip().upper()
    provincia = _limpiar_comillas(provincia)
    return provincia[:30]


def normalizar_pais_ambar(nombre_pais: str, cod_pais_ps: str) -> tuple[str, str]:
    """
    Devuelve (nombre_pais_ambar, codigo_pais_ambar).
    Compatibilidad para consumidores antiguos; la resolución real está
    centralizada y exige un ISO de PrestaShop soportado.
    """
    country = resolve_ambar_country(cod_pais_ps, nombre_pais)
    return country.pais_nombre, country.pais_codigo


def normalizar_telefono_ambar(telefono: str) -> str:
    """
    Limpia un teléfono y lo formatea con espacios cada 3 dígitos.
    Equivalente al bloque de TELEFONO del PHP.
    """
    if not telefono:
        return ""
    limpio = re.sub(r"[-.\s/+]", "", telefono)
    # Quitar prefijo +34 o 0034
    limpio = re.sub(r"^(\+34|0034)", "", limpio)
    limpio = _limpiar_comillas(limpio)
    # Agrupar cada 3 dígitos
    grupos = [limpio[i:i+3] for i in range(0, len(limpio), 3)]
    return " ".join(grupos).strip()[:20]


def combinar_telefonos_ambar(movil: str, telefono: str) -> str:
    """
    Combina móvil y teléfono fijo en un campo con salto de línea
    (CHAR(13)+CHAR(10) en SQL Server). Equivalente al legacy insert.php.
    """
    mov = normalizar_telefono_ambar(movil)
    tel = normalizar_telefono_ambar(telefono)
    if mov and tel:
        return f"{mov}\r\n{tel}"
    return mov or tel


def formatear_dni_ambar(dni: str, nombre_pais: str) -> str:
    """
    Formatea un DNI/NIF para Ambar.
    Si es Portugal, añade prefijo PT si no lo tiene.
    Equivalente a formatearDNIambar() del PHP legacy (funciones.inc.php).
    """
    if not dni:
        return ""
    dni = dni.strip().upper()
    if "portug" in (nombre_pais or "").lower():
        if not dni.startswith("PT"):
            dni = f"PT{dni}"
    return dni[:20]


def dni_solo_numeros(dni: str) -> str:
    """Extrae solo los dígitos de un DNI para cruce con Ambar."""
    return re.sub(r"[^0-9]", "", dni or "")


def _limpiar_comillas(texto: str) -> str:
    """Reemplaza comillas simples y dobles por equivalente Ambar (´)."""
    return texto.replace("'", "´").replace('"', "´´")

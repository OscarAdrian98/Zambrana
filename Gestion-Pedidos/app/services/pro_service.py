"""
services/pro_service.py — Detección de usuarios PRO desde AppB2B.

MEJORA vs legacy: en el PHP se cargaba la tabla completa de b2b_registrations
y se creaba un set para comparar. Aquí hacemos lo mismo pero:
- La carga es async
- El set se puede cachear si la tabla es grande
- La normalización usa el módulo centralizado
"""
import logging
import re
import unicodedata
from aiomysql import Connection
from app.services.normalizacion_service import normalizar_para_comparar

logger = logging.getLogger(__name__)

_RE_SPACES = re.compile(r"\s+")


def _normalizar_email(email: str | None) -> str:
    return str(email or "").strip().lower()


def _normalizar_texto_base(value: str | None) -> str:
    if not value:
        return ""
    txt = str(value).strip().lower()
    txt = txt.replace("\xa0", " ").replace("\r", " ").replace("\n", " ").replace("\t", " ")
    txt = _RE_SPACES.sub(" ", txt).strip()
    txt = unicodedata.normalize("NFD", txt)
    txt = "".join(ch for ch in txt if unicodedata.category(ch) != "Mn")
    return txt


def _first_key(row: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return str(row.get(key) or "")
    return ""


def _build_name_candidates(row: dict) -> set[str]:
    candidates: set[str] = set()
    nombre = _first_key(row, ("nombre", "first_name", "firstname", "name"))
    apellidos = _first_key(row, ("apellidos", "last_name", "lastname", "surname"))
    empresa = _first_key(row, ("nombre_empresa", "empresa", "razon_social", "nombre_comercial", "company"))

    for raw in (
        f"{nombre} {apellidos}",
        f"{apellidos} {nombre}",
        nombre,
        apellidos,
        empresa,
    ):
        norm = _normalizar_texto_base(raw)
        if norm:
            candidates.add(norm)
    return candidates


async def cargar_set_usuarios_pro(conn: Connection) -> frozenset[str]:
    """
    Carga todos los usuarios PRO de AppB2B como un frozenset
    de nombres normalizados (para comparación rápida O(1)).

    El frozenset se puede cachear por petición o con TTL según volumen.
    """
    sql = "SELECT nombre, apellidos FROM b2b_registrations"
    try:
        async with conn.cursor() as cur:
            await cur.execute(sql)
            rows = await cur.fetchall()
        pro_set = frozenset(
            normalizar_para_comparar(f"{row[0]} {row[1]}")
            for row in rows
        )
        logger.debug("PRO set cargado: %d registros", len(pro_set))
        return pro_set
    except Exception as e:
        logger.error("Error cargando usuarios PRO: %s", e)
        return frozenset()


async def cargar_indices_usuarios_pro(conn: Connection) -> tuple[frozenset[str], frozenset[str]]:
    """
    Devuelve dos índices para detección PRO:
    - emails normalizados (prioridad alta)
    - nombres completos normalizados (fallback)
    """
    try:
        async with conn.cursor() as cur:
            await cur.execute("SHOW COLUMNS FROM b2b_registrations")
            columns = [str(r[0]) for r in await cur.fetchall()]
            logger.info("PRO service: columnas b2b_registrations=%s", columns)

            await cur.execute("SELECT * FROM b2b_registrations")
            rows = await cur.fetchall()
            row_count = len(rows)

            idx_email: set[str] = set()
            idx_nombre: set[str] = set()
            for row in rows:
                row_map = {columns[i]: row[i] for i in range(min(len(columns), len(row)))}
                email_norm = _normalizar_email(_first_key(row_map, ("email", "correo", "mail", "e_mail")))
                if email_norm:
                    idx_email.add(email_norm)
                idx_nombre.update(_build_name_candidates(row_map))

            logger.info("PRO service: registros cargados=%d", row_count)
            logger.info("PRO service: emails cargados=%d", len(idx_email))
            logger.info("PRO service: nombres cargados=%d", len(idx_nombre))
            return frozenset(idx_email), frozenset(idx_nombre)
    except Exception as e:
        logger.error("Error cargando índices PRO: %s", e)
        return frozenset(), frozenset()


def es_cliente_pro(
    nombre: str, apellidos: str, pro_set: frozenset[str]
) -> bool:
    """
    Comprueba si un cliente es PRO comparando su nombre normalizado
    contra el frozenset cargado desde AppB2B.
    """
    clave = normalizar_para_comparar(f"{nombre} {apellidos}")
    return clave in pro_set


def es_cliente_pro_por_email_o_nombre(
    *,
    email: str | None,
    nombre: str,
    apellidos: str,
    pro_emails: frozenset[str],
    pro_nombres: frozenset[str],
) -> bool:
    es_pro, _, _ = diagnosticar_cliente_pro_por_email_o_nombre(
        email=email,
        nombre=nombre,
        apellidos=apellidos,
        pro_emails=pro_emails,
        pro_nombres=pro_nombres,
    )
    return es_pro


def diagnosticar_cliente_pro_por_email_o_nombre(
    *,
    email: str | None,
    nombre: str,
    apellidos: str,
    pro_emails: frozenset[str],
    pro_nombres: frozenset[str],
) -> tuple[bool, bool, bool]:
    email_norm = _normalizar_email(email)
    email_match = bool(email_norm) and email_norm in pro_emails
    nombre_full = _normalizar_texto_base(f"{nombre} {apellidos}")
    nombre_flip = _normalizar_texto_base(f"{apellidos} {nombre}")
    nombre_match = (nombre_full in pro_nombres) or (nombre_flip in pro_nombres)
    return email_match or nombre_match, email_match, nombre_match

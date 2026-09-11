"""
repositories/clientes_repository.py - Consultas a Ambar para clientes.
"""
import logging
import re
import time
from datetime import date

import pyodbc

from app.schemas.cliente import ClienteAmbarDTO

logger = logging.getLogger(__name__)

SQL_CLIENTE_BASE = """
    SELECT TOP 10
        c.Cliente           AS numero_cliente,
        c.Nombre            AS nombre,
        c.NIF               AS nif,
        c.[Dirección]       AS direccion,
        c.[Población]       AS ciudad,
        c.Provincia         AS provincia,
        c.CP                AS postal,
        c.[Teléfono]        AS telefono,
        c.email             AS email,
        c.CuentaContable    AS cuenta_contable,
        c.Libre1            AS libre1,
        c.Pais              AS pais,
        c.PaisCodigo        AS cod_pais,
        c.Baja              AS baja,
        c.Bloqueo           AS bloqueo,
        c.BloqueoAviso      AS aviso
    FROM Clientes c
"""


def buscar_cliente_por_email_y_dni(
    conn: pyodbc.Connection,
    email: str,
    dni_numerico_envio: str,
    dni_numerico_factura: str,
) -> list[ClienteAmbarDTO]:
    """
    Mantiene busqueda individual (compatibilidad).
    """
    if not email and not dni_numerico_envio and not dni_numerico_factura:
        return []

    conditions = []
    params = []

    if email and email.strip():
        conditions.append("c.email LIKE ?")
        params.append(f"%{email.strip()}%")

    if dni_numerico_envio:
        conditions.append("c.NIF LIKE ?")
        params.append(f"%{dni_numerico_envio}%")

    if dni_numerico_factura and dni_numerico_factura != dni_numerico_envio:
        conditions.append("c.NIF LIKE ?")
        params.append(f"%{dni_numerico_factura}%")

    if not conditions:
        return []

    sql = f"{SQL_CLIENTE_BASE} WHERE ({' OR '.join(conditions)})"

    cursor = conn.cursor()
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    cols = [col[0] for col in cursor.description]
    return [_row_to_cliente(dict(zip(cols, row))) for row in rows]


def buscar_clientes_batch(
    conn: pyodbc.Connection,
    pedidos_datos: list[dict],
) -> dict[int, list[ClienteAmbarDTO]]:
    """
    Matching por lote en UNA consulta agrupada para evitar N consultas por pedido.

    pedidos_datos keys esperadas:
      - id_pedido
      - email
      - dni_num_envio
      - dni_num_factura
    """
    if not pedidos_datos:
        return {}

    t_total_start = time.monotonic()
    resultado: dict[int, list[ClienteAmbarDTO]] = {}
    claves_por_pedido: dict[int, dict[str, list[tuple[str, str]] | str]] = {}
    emails_set: set[str] = set()
    nifs_set: set[str] = set()

    for pd in pedidos_datos:
        id_pedido = int(pd["id_pedido"])
        email_norm = _normalizar_email(pd.get("email"))
        dni_env_norm = _normalizar_nif(pd.get("dni_num_envio"))
        dni_fact_norm = _normalizar_nif(pd.get("dni_num_factura"))

        nifs: list[tuple[str, str]] = []
        if dni_env_norm:
            nifs.append(("dni_envio", dni_env_norm))
        if dni_fact_norm and dni_fact_norm != dni_env_norm:
            nifs.append(("dni_factura", dni_fact_norm))

        claves_por_pedido[id_pedido] = {
            "email": email_norm,
            "nifs": nifs,
        }
        resultado[id_pedido] = []

        if email_norm:
            emails_set.add(email_norm)
        nifs_set.update(v for _, v in nifs)

    if not emails_set and not nifs_set:
        return resultado

    t_sql_start = time.monotonic()
    clientes_by_id: dict[int, ClienteAmbarDTO] = {}

    # Fase 1 (rápida): match exacto por email/NIF sin funciones sobre columna.
    fast_where_parts: list[str] = []
    fast_params: list[str] = []
    if emails_set:
        placeholders = ",".join(["?"] * len(emails_set))
        fast_where_parts.append(f"c.email IN ({placeholders})")
        fast_params.extend(sorted(emails_set))
    if nifs_set:
        placeholders = ",".join(["?"] * len(nifs_set))
        fast_where_parts.append(f"c.NIF IN ({placeholders})")
        fast_params.extend(sorted(nifs_set))

    rows_fast = _buscar_clientes_por_filtros(conn, fast_where_parts, fast_params)
    for cliente in rows_fast:
        clientes_by_id[cliente.numero_cliente] = cliente

    # Claves pendientes tras fase rápida.
    emails_match_fast = {
        _normalizar_email(c.email)
        for c in rows_fast
        if _normalizar_email(c.email)
    }
    nifs_match_fast = {
        _normalizar_nif(c.nif)
        for c in rows_fast
        if _normalizar_nif(c.nif)
    }
    missing_emails = sorted(emails_set - emails_match_fast)
    missing_nifs = sorted(nifs_set - nifs_match_fast)

    # Fase 2 (fallback): solo para claves sin resolver con normalización SQL legacy.
    fallback_where_parts: list[str] = []
    fallback_params: list[str] = []
    if missing_emails:
        placeholders = ",".join(["?"] * len(missing_emails))
        fallback_where_parts.append(
            f"LOWER(LTRIM(RTRIM(ISNULL(c.email, '')))) IN ({placeholders})"
        )
        fallback_params.extend(missing_emails)
    if missing_nifs:
        placeholders = ",".join(["?"] * len(missing_nifs))
        fallback_where_parts.append(f"{_sql_normalizar_nif('c.NIF')} IN ({placeholders})")
        fallback_params.extend(missing_nifs)

    rows_fallback: list[ClienteAmbarDTO] = []
    if fallback_where_parts:
        rows_fallback = _buscar_clientes_por_filtros(conn, fallback_where_parts, fallback_params)
        for cliente in rows_fallback:
            clientes_by_id[cliente.numero_cliente] = cliente

    t_sql_ms = (time.monotonic() - t_sql_start) * 1000
    t_merge_start = time.monotonic()

    clientes_por_email: dict[str, list[ClienteAmbarDTO]] = {}
    clientes_por_nif: dict[str, list[ClienteAmbarDTO]] = {}

    for cliente in clientes_by_id.values():
        email_key = _normalizar_email(cliente.email)
        nif_key = _normalizar_nif(cliente.nif)

        if email_key:
            clientes_por_email.setdefault(email_key, []).append(cliente)
        if nif_key:
            clientes_por_nif.setdefault(nif_key, []).append(cliente)

    for id_pedido, claves in claves_por_pedido.items():
        candidatos: dict[int, tuple[ClienteAmbarDTO, set[str]]] = {}

        email_key = claves["email"]
        if isinstance(email_key, str) and email_key:
            for cliente in clientes_por_email.get(email_key, []):
                current = candidatos.get(cliente.numero_cliente)
                if current is None:
                    candidatos[cliente.numero_cliente] = (cliente, {"email"})
                else:
                    current[1].add("email")

        nifs_pedido = list(claves["nifs"])
        for motivo, nif_key in nifs_pedido:
            for cliente in clientes_por_nif.get(nif_key, []):
                current = candidatos.get(cliente.numero_cliente)
                if current is None:
                    candidatos[cliente.numero_cliente] = (cliente, {motivo})
                else:
                    current[1].add(motivo)

        final_candidatos: list[ClienteAmbarDTO] = []
        for cliente, razones in candidatos.values():
            razones_ordenadas = [r for r in ("email", "dni_factura", "dni_envio") if r in razones]
            if len(razones_ordenadas) > 1:
                razones_ordenadas = ["varios", *razones_ordenadas]
            final_candidatos.append(cliente.model_copy(update={"match_reason": razones_ordenadas}))

        resultado[id_pedido] = sorted(
            final_candidatos,
            key=lambda c: (c.baja, c.bloqueo, c.numero_cliente),
        )

    t_merge_ms = (time.monotonic() - t_merge_start) * 1000
    t_total_ms = (time.monotonic() - t_total_start) * 1000
    logger.info(
        "Matching Ambar sql_ms=%.2f merge_ms=%.2f total_ms=%.2f pedidos=%d claves_email=%d "
        "claves_nif=%d candidatos=%d fallback_email=%d fallback_nif=%d",
        t_sql_ms,
        t_merge_ms,
        t_total_ms,
        len(claves_por_pedido),
        len(emails_set),
        len(nifs_set),
        len(clientes_by_id),
        len(missing_emails),
        len(missing_nifs),
    )
    return resultado


def _buscar_clientes_por_filtros(
    conn: pyodbc.Connection,
    where_parts: list[str],
    params: list[str],
) -> list[ClienteAmbarDTO]:
    if not where_parts:
        return []

    sql = f"""
        SELECT
            c.Cliente           AS numero_cliente,
            c.Nombre            AS nombre,
            c.NIF               AS nif,
            c.[Dirección]       AS direccion,
            c.[Población]       AS ciudad,
            c.Provincia         AS provincia,
            c.CP                AS postal,
            c.[Teléfono]        AS telefono,
            c.email             AS email,
            c.CuentaContable    AS cuenta_contable,
            c.Libre1            AS libre1,
            c.Pais              AS pais,
            c.PaisCodigo        AS cod_pais,
            c.Baja              AS baja,
            c.Bloqueo           AS bloqueo,
            c.BloqueoAviso      AS aviso
        FROM Clientes c
        WHERE {' OR '.join(where_parts)}
    """
    cursor = conn.cursor()
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    cols = [col[0] for col in cursor.description]
    return [_row_to_cliente(dict(zip(cols, row))) for row in rows]


def obtener_proximo_id_cliente(conn: pyodbc.Connection) -> int:
    """Obtiene el proximo ID de cliente disponible (< 90000)."""
    sql = "SELECT MAX(Cliente) FROM Clientes WHERE Cliente < 90000"
    cursor = conn.cursor()
    cursor.execute(sql)
    row = cursor.fetchone()
    ultimo = row[0] if row and row[0] else 0
    return int(ultimo) + 1


def crear_cliente_ambar(conn: pyodbc.Connection, datos: dict) -> int:
    """
    Inserta un nuevo cliente en Ambar.
    """
    id_cliente = obtener_proximo_id_cliente(conn)

    columnas_insert = [
        "Cliente", "Alta", "TipoDocumento", "NIF", "Nombre",
        "CP", "[Población]", "Provincia", "PaisCodigo", "Pais",
        "[Dirección]", "[Teléfono]", "email",
        "EtqAtt", "[EtqDirección]", "EtqCP", "[EtqPoblación]", "EtqProvincia",
        "FormaPago", "Libre1",
        "SeriePedidos", "SerieAlbaranes", "SerieFacturas",
        "CuentaContable", "Baja", "Bloqueo",
        "AplicaReciclaje", "AplicaTramos", "AplicaOfertasFecha",
        "EstadoCobro", "TipoRetencion", "FacturasMail",
        "psPenSubir", "IdiomaArticulos", "CuentaAUsar",
        "TipoMandato", "ClaseMandato", "InversionSujetoPasivo",
        "[IvaRégimen]", "IvaClase",
    ]
    placeholders = ",".join(["?"] * len(columnas_insert))
    sql = f"""
        INSERT INTO Clientes (
            {", ".join(columnas_insert)}
        ) VALUES (
            {placeholders}
        )
    """
    params = (
        id_cliente,
        datos["fecha_alta"],
        datos["tipo_documento"],
        datos["nif"],
        datos["nombre"],
        datos["postal"],
        datos["ciudad"],
        datos["provincia"],
        datos["cod_pais"],
        datos["pais"],
        datos["direccion"],
        datos["telefonos"],
        datos["email"],
        datos["nombre"],
        datos["direccion"],
        datos["postal"],
        datos["ciudad"],
        datos["provincia"],
        "RE",
        "1 - PARTICULAR",
        datos["serie"],
        datos["serie"],
        datos["serie"],
        datos["cuenta_contable"],
        0,
        "S",
        "S",
        "S",
        "S",
        "N",
        "O",
        "N",
        0,
        "C",
        "N",
        "C",
        "R",
        "N",
        datos["regimen_iva"],
        datos["clase_iva"],
    )

    cursor = conn.cursor()
    logger.info(
        "Insert cliente columnas usadas (%d): %s | valores=%d",
        len(columnas_insert),
        ", ".join(columnas_insert),
        len(params),
    )
    cursor.execute(sql, params)

    sql_contador = """
        UPDATE Config SET Valor = ?
        WHERE Grupo='CONTADORES DE REGISTROS' AND Variable='CLIENTES'
    """
    cursor.execute(sql_contador, (str(id_cliente),))
    conn.commit()

    logger.info("Cliente Ambar creado: id=%d cc=%s", id_cliente, datos["cuenta_contable"])
    return id_cliente


def activar_cliente_ambar(conn: pyodbc.Connection, id_cliente: int) -> bool:
    """Reactiva un cliente dado de baja."""
    sql = """
        UPDATE Clientes
        SET Baja = 0, FechaModif = ?, FechaBaja = NULL
        WHERE Cliente = ?
    """
    cursor = conn.cursor()
    cursor.execute(sql, (date.today().strftime("%d-%m-%Y"), id_cliente))
    conn.commit()
    logger.info("Cliente %d reactivado en Ambar", id_cliente)
    return True


def buscar_duplicados_defensivos(
    conn: pyodbc.Connection,
    email: str,
    nif: str,
) -> list[ClienteAmbarDTO]:
    """
    Comprobacion defensiva previa a insercion real.
    Busca coincidencias exactas por email normalizado o NIF normalizado.
    """
    email_norm = _normalizar_email(email)
    nif_norm = _normalizar_nif(nif)
    if not email_norm and not nif_norm:
        return []

    where_parts: list[str] = []
    params: list[str] = []
    if email_norm:
        where_parts.append("LOWER(LTRIM(RTRIM(ISNULL(c.email, '')))) = ?")
        params.append(email_norm)
    if nif_norm:
        where_parts.append(f"{_sql_normalizar_nif('c.NIF')} = ?")
        params.append(nif_norm)

    sql = f"""
        SELECT TOP 25
            c.Cliente           AS numero_cliente,
            c.Nombre            AS nombre,
            c.NIF               AS nif,
            c.[Dirección]       AS direccion,
            c.[Población]       AS ciudad,
            c.Provincia         AS provincia,
            c.CP                AS postal,
            c.[Teléfono]        AS telefono,
            c.email             AS email,
            c.CuentaContable    AS cuenta_contable,
            c.Libre1            AS libre1,
            c.Pais              AS pais,
            c.PaisCodigo        AS cod_pais,
            c.Baja              AS baja,
            c.Bloqueo           AS bloqueo,
            c.BloqueoAviso      AS aviso
        FROM Clientes c
        WHERE {" OR ".join(where_parts)}
    """
    cursor = conn.cursor()
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    cols = [col[0] for col in cursor.description]
    return [_row_to_cliente(dict(zip(cols, row))) for row in rows]


def _row_to_cliente(d: dict) -> ClienteAmbarDTO:
    return ClienteAmbarDTO(
        numero_cliente=int(d["numero_cliente"]),
        nombre=d["nombre"] or "",
        nif=d["nif"] or "",
        direccion=d["direccion"] or "",
        ciudad=d["ciudad"] or "",
        provincia=d["provincia"] or "",
        postal=d["postal"] or "",
        telefono=d["telefono"] or "",
        email=d["email"] or "",
        cuenta_contable=d["cuenta_contable"] or "",
        libre1=d["libre1"] or "",
        pais=d["pais"] or "",
        cod_pais=d["cod_pais"] or "",
        baja=_to_bool(d["baja"]),
        bloqueo=_to_bool(d["bloqueo"]),
        aviso=d["aviso"] or "",
    ).calcular_estado()


def _normalizar_email(value: str | None) -> str:
    return (value or "").strip().lower()


def _normalizar_nif(value: str | None) -> str:
    raw = (value or "").strip().upper()
    return re.sub(r"[^A-Z0-9]", "", raw)


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "t", "s", "si", "y", "yes"}


def _sql_normalizar_nif(field_name: str) -> str:
    return (
        "UPPER(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(ISNULL("
        + field_name +
        ", ''), ' ', ''), '-', ''), '.', ''), '/', ''), '\\', ''))"
    )

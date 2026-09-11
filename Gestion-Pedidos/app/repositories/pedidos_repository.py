"""
repositories/pedidos_repository.py — Consultas PrestaShop para pedidos.

MEJORAS vs legacy matches.php:
- Consulta principal parametrizada (sin concatenación)
- Mensajes cargados en batch (un solo SELECT para todos los pedidos)
- INNER JOIN con LEFT JOIN en ps_state para soportar países sin provincia
- Filtros validados por capa de schemas antes de llegar aquí
"""
import logging
import time
import re
import unicodedata
from datetime import datetime, date
from aiomysql import Connection
from app.schemas.pedido import PedidoPSDTO, DireccionDTO, MensajePedidoDTO, FiltrosPedidosDTO

logger = logging.getLogger(__name__)

_ESTADOS_PEDIDO_CACHE: list[dict] | None = None
_ESTADOS_PEDIDO_CACHE_EXPIRES_AT: float = 0.0
_ESTADOS_PEDIDO_CACHE_TTL_SECONDS: int = 600
ESTADOS_PEDIDO_PERMITIDOS: list[str] = [
    "Entregado",
    "Enviado",
    "Esperando el pago",
    "Pedido Realizado",
    "Tramitando Pedido",
    "seQura: Aprobado",
    "seQura: Cancelado",
    "seQura: En revisión",
    "Cancelado",
    "En Tránsito desde Fábrica",
    "Preparando Paquete",
    "Reembolsado",
    "Pedido pendiente por falta de stock (no pagado)",
    "En espera de pago por transferencia bancaria",
    "Pedido Realizado (Reponiendo Productos)",
    "Recogida en Tienda Pendiente",
    "Pedido Realizado - Reembolso",
]
_RE_MULTI_SPACE = re.compile(r"\s+")


async def obtener_modos_pago_ultimo_ano(conn: Connection) -> list[str]:
    """Obtiene modos de pago distintos del último año para el selector."""
    sql = """
        SELECT DISTINCT payment
        FROM ps_orders
        WHERE date_add >= DATE_SUB(CURDATE(), INTERVAL 1 YEAR)
        ORDER BY payment ASC
    """
    async with conn.cursor() as cur:
        await cur.execute(sql)
        rows = await cur.fetchall()
    return [row[0] for row in rows if row[0]]


async def obtener_estados_pedido(
    conn: Connection, *, force_refresh: bool = False, ttl_seconds: int = _ESTADOS_PEDIDO_CACHE_TTL_SECONDS
) -> list[dict]:
    """Obtiene estados de pedido de PrestaShop para filtros y accion por fila."""
    global _ESTADOS_PEDIDO_CACHE, _ESTADOS_PEDIDO_CACHE_EXPIRES_AT

    now = time.monotonic()
    if (
        not force_refresh
        and _ESTADOS_PEDIDO_CACHE is not None
        and now < _ESTADOS_PEDIDO_CACHE_EXPIRES_AT
    ):
        return [dict(item) for item in _ESTADOS_PEDIDO_CACHE]

    sql = """
        SELECT os.id_order_state, osl.name, os.color
        FROM ps_order_state os
        INNER JOIN ps_order_state_lang osl
            ON os.id_order_state = osl.id_order_state
        WHERE osl.id_lang = 1
        ORDER BY osl.name ASC
    """
    async with conn.cursor() as cur:
        await cur.execute(sql)
        rows = await cur.fetchall()
    estados_raw = [
        {
            "id_order_state": int(row[0]),
            "nombre": row[1] or "",
            "color": row[2] or "#cccccc",
        }
        for row in rows
    ]
    orden_permitidos = {
        _normalizar_estado_nombre(nombre): idx
        for idx, nombre in enumerate(ESTADOS_PEDIDO_PERMITIDOS)
    }
    estados = [
        st
        for st in estados_raw
        if _normalizar_estado_nombre(st["nombre"]) in orden_permitidos
    ]
    estados.sort(key=lambda st: orden_permitidos[_normalizar_estado_nombre(st["nombre"])])
    _ESTADOS_PEDIDO_CACHE = estados
    _ESTADOS_PEDIDO_CACHE_EXPIRES_AT = now + max(60, int(ttl_seconds or _ESTADOS_PEDIDO_CACHE_TTL_SECONDS))
    return [dict(item) for item in estados]


async def obtener_ids_ultimos_pedidos(conn: Connection, n: int) -> list[int]:
    """
    MEJORA vs legacy: en el PHP hacía una subconsulta dentro del filtro
    principal (N+1). Aquí separamos en dos queries más limpias.
    """
    if n <= 0 or n > 200:
        return []
    sql = "SELECT id_order FROM ps_orders ORDER BY id_order DESC LIMIT %s"
    async with conn.cursor() as cur:
        await cur.execute(sql, (n,))
        rows = await cur.fetchall()
    return [r[0] for r in rows]


async def obtener_max_id_pedido(conn: Connection) -> int:
    """Obtiene el id_order mas alto actual en PrestaShop."""
    sql = "SELECT MAX(id_order) FROM ps_orders"
    async with conn.cursor() as cur:
        await cur.execute(sql)
        row = await cur.fetchone()
    return int((row or [0])[0] or 0)


async def obtener_pedidos_nuevos_desde(conn: Connection, last_id: int, limit: int = 20) -> dict:
    """
    Consulta ligera para detectar pedidos nuevos sin cargar matching ni
    informacion adicional de negocio.
    """
    last_id = max(0, int(last_id or 0))
    limit = max(1, min(int(limit or 20), 50))

    sql = """
        SELECT
            o.id_order,
            o.date_add,
            c.firstname,
            c.lastname,
            o.payment,
            o.total_paid_tax_incl
        FROM ps_orders o
        INNER JOIN ps_customer c ON o.id_customer = c.id_customer
        WHERE o.id_order > %s
        ORDER BY o.id_order ASC
        LIMIT %s
    """
    async with conn.cursor() as cur:
        await cur.execute(sql, (last_id, limit))
        rows = await cur.fetchall()

    pedidos = []
    max_id = last_id
    for row in rows:
        id_order, date_add, firstname, lastname, payment, total = row
        id_order_int = int(id_order or 0)
        max_id = max(max_id, id_order_int)
        pedidos.append(
            {
                "id_order": id_order_int,
                "date_add": date_add.isoformat() if hasattr(date_add, "isoformat") else str(date_add or ""),
                "cliente": f"{firstname or ''} {lastname or ''}".strip(),
                "payment": str(payment or ""),
                "total": float(total or 0),
            }
        )

    if not pedidos:
        max_id = max(max_id, await obtener_max_id_pedido(conn))

    return {
        "hay_nuevos": bool(pedidos),
        "count": len(pedidos),
        "max_id": max_id,
        "pedidos": pedidos,
    }


async def obtener_cabecera_y_lineas_para_comprobacion_stock(conn: Connection, id_pedido: int) -> dict | None:
    """Lectura ligera para comprobar pago y lineas reales del pedido."""
    sql_cab = """
        SELECT
            o.id_order,
            o.reference,
            o.current_state,
            os.paid,
            osl.name,
            o.payment
        FROM ps_orders o
        INNER JOIN ps_order_state os
            ON os.id_order_state = o.current_state
        LEFT JOIN ps_order_state_lang osl
            ON osl.id_order_state = o.current_state
           AND osl.id_lang = 1
        WHERE o.id_order = %s
        LIMIT 1
    """
    sql_lineas = """
        SELECT
            od.id_order_detail,
            od.id_order,
            od.product_id,
            od.product_attribute_id,
            od.product_reference,
            od.product_name,
            od.product_quantity
        FROM ps_order_detail od
        WHERE od.id_order = %s
        ORDER BY od.id_order_detail ASC
    """
    async with conn.cursor() as cur:
        await cur.execute(sql_cab, (id_pedido,))
        cab = await cur.fetchone()
        if not cab:
            return None
        await cur.execute(sql_lineas, (id_pedido,))
        rows = await cur.fetchall()

    lineas = [
        {
            "id_order_detail": int(row[0] or 0),
            "id_order": int(row[1] or 0),
            "product_id": int(row[2] or 0),
            "product_attribute_id": int(row[3] or 0),
            "product_reference": str(row[4] or "").strip(),
            "product_name": str(row[5] or "").strip(),
            "product_quantity": int(row[6] or 0),
        }
        for row in rows
    ]
    return {
        "id_order": int(cab[0] or 0),
        "reference": str(cab[1] or "").strip(),
        "current_state": int(cab[2] or 0),
        "paid": bool(cab[3]),
        "state_name": str(cab[4] or "").strip(),
        "payment": str(cab[5] or "").strip(),
        "lineas": lineas,
    }


async def obtener_resumen_pedido_para_email(conn: Connection, id_pedido: int) -> dict | None:
    """Obtiene datos minimos del pedido para validar envio de email."""
    sql = """
        SELECT
            o.id_order,
            o.reference,
            o.date_add,
            o.total_paid_tax_incl,
            c.firstname,
            c.lastname,
            c.email,
            o.payment
        FROM ps_orders o
        INNER JOIN ps_customer c ON c.id_customer = o.id_customer
        WHERE o.id_order = %s
        LIMIT 1
    """
    async with conn.cursor() as cur:
        await cur.execute(sql, (id_pedido,))
        row = await cur.fetchone()
    if not row:
        return None
    return {
        "id_order": int(row[0] or 0),
        "reference": str(row[1] or "").strip(),
        "date_add": row[2],
        "total_paid_tax_incl": float(row[3] or 0),
        "firstname": str(row[4] or "").strip(),
        "lastname": str(row[5] or "").strip(),
        "email": str(row[6] or "").strip(),
        "payment": str(row[7] or "").strip(),
    }


async def obtener_lineas_pedido_para_email(conn: Connection, id_pedido: int) -> list[dict]:
    """Obtiene lineas de pedido con datos de producto para resumen visual de email."""
    sql = """
        SELECT
            od.product_name,
            od.product_reference,
            od.product_quantity,
            od.unit_price_tax_incl,
            od.total_price_tax_incl,
            COALESCE(img_attr.id_image, img_cover.id_image) AS id_image
        FROM ps_order_detail od
        LEFT JOIN (
            SELECT
                pai.id_product_attribute,
                MIN(pai.id_image) AS id_image
            FROM ps_product_attribute_image pai
            GROUP BY pai.id_product_attribute
        ) img_attr ON img_attr.id_product_attribute = od.product_attribute_id
        LEFT JOIN (
            SELECT
                i.id_product,
                MIN(i.id_image) AS id_image
            FROM ps_image i
            WHERE i.cover = 1
            GROUP BY i.id_product
        ) img_cover ON img_cover.id_product = od.product_id
        WHERE od.id_order = %s
        ORDER BY od.id_order_detail ASC
    """
    async with conn.cursor() as cur:
        await cur.execute(sql, (id_pedido,))
        rows = await cur.fetchall()

    result: list[dict] = []
    for row in rows:
        result.append(
            {
                "name": str(row[0] or "").strip(),
                "reference": str(row[1] or "").strip(),
                "quantity": int(row[2] or 0),
                "unit_price": float(row[3] or 0),
                "total_price": float(row[4] or 0),
                "id_image": int(row[5]) if row[5] is not None else None,
            }
        )
    return result


async def obtener_pedidos(
    conn: Connection, filtros: FiltrosPedidosDTO, *, include_messages: bool = True
) -> list[PedidoPSDTO]:
    """
    Consulta principal de pedidos con todos los JOINs necesarios.

    MEJORAS vs legacy:
    - Parámetros %s en lugar de f-string/concatenación
    - LEFT JOIN en ps_state (el original fallaba si no había provincia)
    - Mensajes NO se consultan aquí: se hace un solo batch query aparte
    - Devuelve lista de DTOs tipados, no dict plano
    """
    where_parts: list[str] = [
        "cld.id_lang = 1",
        "cli.id_lang = 1",
        "osl.id_lang = 1",
    ]
    params: list = []

    # Filtro fechas
    if filtros.fecha_desde:
        where_parts.append("o.date_add >= %s")
        params.append(f"{filtros.fecha_desde} 00:00:00")
    if filtros.fecha_hasta:
        where_parts.append("o.date_add <= %s")
        params.append(f"{filtros.fecha_hasta} 23:59:59")

    # Filtro ID único
    if filtros.id_pedido:
        ids_todos = [filtros.id_pedido] + filtros.ids_multiples
        placeholders = ",".join(["%s"] * len(ids_todos))
        where_parts.append(f"o.id_order IN ({placeholders})")
        params.extend(ids_todos)
    elif filtros.ids_multiples:
        # Ids múltiples sin id principal
        placeholders = ",".join(["%s"] * len(filtros.ids_multiples))
        where_parts.append(f"o.id_order IN ({placeholders})")
        params.extend(filtros.ids_multiples)

    # Filtro últimos N
    if filtros.ultimos_n and filtros.ultimos_n > 0:
        ids_ultimos = await obtener_ids_ultimos_pedidos(conn, filtros.ultimos_n)
        if ids_ultimos:
            placeholders = ",".join(["%s"] * len(ids_ultimos))
            where_parts.append(f"o.id_order IN ({placeholders})")
            params.extend(ids_ultimos)
        else:
            return []  # No hay pedidos

    # Filtro modos de pago
    if filtros.modos_pago:
        pago_parts = " OR ".join(["o.payment LIKE %s"] * len(filtros.modos_pago))
        where_parts.append(f"({pago_parts})")
        params.extend([f"%{p}%" for p in filtros.modos_pago])

    # Filtro estados de pedido
    if filtros.estados_pedido:
        placeholders = ",".join(["%s"] * len(filtros.estados_pedido))
        where_parts.append(f"o.current_state IN ({placeholders})")
        params.extend(filtros.estados_pedido)

    # Filtro estados internos auxiliares. El estado 1 incluye pedidos sin fila gp_*.
    if filtros.estados_internos:
        internal_parts: list[str] = []
        otros_estados = [st for st in filtros.estados_internos if st != 1]
        if 1 in filtros.estados_internos:
            internal_parts.append("(gois.id_internal_state = 1 OR gois.id_order IS NULL)")
        if otros_estados:
            placeholders = ",".join(["%s"] * len(otros_estados))
            internal_parts.append(f"gois.id_internal_state IN ({placeholders})")
            params.extend(otros_estados)
        if internal_parts:
            where_parts.append("(" + " OR ".join(internal_parts) + ")")

    where_sql = " AND ".join(where_parts)

    sql = f"""
        SELECT
            o.id_order              AS idPedido,
            o.reference             AS referenciaPedido,
            o.date_add              AS fechaPedido,
            o.invoice_date          AS fechaFactura,
            o.payment               AS pagoPedido,
            o.total_paid_real       AS totalPagado,
            o.total_paid_tax_excl   AS totalSinIva,
            o.total_paid_tax_incl   AS totalConIva,
            o.current_state         AS estadoPedido,
            o.id_customer           AS idCliente,
            o.id_address_delivery   AS idDirEnvio,
            o.id_address_invoice    AS idDirFactura,
            c.firstname             AS nombreCliente,
            c.lastname              AS apellidosCliente,
            c.email                 AS emailCliente,
            -- Dirección envío
            ad.firstname            AS nomEnv, ad.lastname AS apEnv,
            ad.address1             AS dir1Env, ad.address2 AS dir2Env,
            ad.dni                  AS dniEnv,
            ad.city                 AS ciudadEnv, ad.postcode AS postalEnv,
            ad.company              AS empresaEnv,
            ad.phone_mobile         AS movilEnv, ad.phone AS telEnv,
            ad.other                AS otrosEnv,
            cld.name                AS paisEnv,
            cd.id_country           AS idPaisEnv,
            cd.iso_code             AS codPaisEnv,
            IFNULL(sd.name,'')      AS provEnv,
            -- Dirección factura
            ai.firstname            AS nomFact, ai.lastname AS apFact,
            ai.address1             AS dir1Fact, ai.address2 AS dir2Fact,
            ai.dni                  AS dniFact,
            ai.city                 AS ciudadFact, ai.postcode AS postalFact,
            ai.company              AS empresaFact,
            ai.phone_mobile         AS movilFact, ai.phone AS telFact,
            ai.other                AS otrosFact,
            cli.name                AS paisFact,
            ci.id_country           AS idPaisFact,
            ci.iso_code             AS codPaisFact,
            IFNULL(si.name,'')      AS provFact,
            -- Estado
            osl.name                AS nombreEstado,
            os.color                AS colorEstado,
            -- Estado interno auxiliar
            COALESCE(gois.id_internal_state, 1) AS internalStateId,
            COALESCE(gis.code, 'nuevo_pedido') AS internalStateCode,
            COALESCE(gis.name, 'Nuevo Pedido') AS internalStateName,
            COALESCE(gis.color, '#2563eb') AS internalStateColor
        FROM
            ps_orders o
            INNER JOIN ps_customer c         ON o.id_customer = c.id_customer
            INNER JOIN ps_address ad          ON o.id_address_delivery = ad.id_address
            INNER JOIN ps_country cd          ON ad.id_country = cd.id_country
            INNER JOIN ps_country_lang cld    ON cd.id_country = cld.id_country AND cld.id_lang = 1
            LEFT  JOIN ps_state sd            ON ad.id_state = sd.id_state
            INNER JOIN ps_address ai          ON o.id_address_invoice = ai.id_address
            INNER JOIN ps_country ci          ON ai.id_country = ci.id_country
            INNER JOIN ps_country_lang cli    ON ci.id_country = cli.id_country AND cli.id_lang = 1
            LEFT  JOIN ps_state si            ON ai.id_state = si.id_state
            INNER JOIN ps_order_state os      ON o.current_state = os.id_order_state
            INNER JOIN ps_order_state_lang osl ON o.current_state = osl.id_order_state
            LEFT JOIN gp_order_internal_state gois ON gois.id_order = o.id_order
            LEFT JOIN gp_internal_order_states gis ON gis.id_internal_state = gois.id_internal_state
        WHERE {where_sql}
        ORDER BY o.id_order DESC
        LIMIT 150
    """

    logger.debug("SQL pedidos con %d parámetros", len(params))
    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        rows = await cur.fetchall()
        cols = [d[0] for d in cur.description]

    if not rows:
        logger.info("Búsqueda de pedidos: 0 resultados")
        return []

    dicts = [dict(zip(cols, row)) for row in rows]
    ids_pedidos = [d["idPedido"] for d in dicts]

    mensajes_batch: dict[int, list[MensajePedidoDTO]] = {}
    if include_messages:
        # Carga batch de mensajes (1 query para todos los pedidos)
        mensajes_batch = await _cargar_mensajes_batch(conn, ids_pedidos)

    pedidos: list[PedidoPSDTO] = []
    for d in dicts:
        pedido = _mapear_pedido(d, mensajes_batch)
        pedidos.append(pedido)

    logger.info("Búsqueda pedidos: %d resultados", len(pedidos))
    return pedidos


async def _cargar_mensajes_batch(
    conn: Connection, ids_pedidos: list[int]
) -> dict[int, list[MensajePedidoDTO]]:
    """
    Carga todos los mensajes de la lista de pedidos en UNA sola consulta.
    MEJORA vs legacy: el PHP hacía un SELECT por pedido (N+1).
    """
    if not ids_pedidos:
        return {}
    placeholders = ",".join(["%s"] * len(ids_pedidos))
    sql = f"""
        SELECT id_order, message, id_customer, date_add
        FROM ps_message
        WHERE id_order IN ({placeholders})
        ORDER BY id_order, date_add DESC
    """
    async with conn.cursor() as cur:
        await cur.execute(sql, ids_pedidos)
        rows = await cur.fetchall()

    resultado: dict[int, list[MensajePedidoDTO]] = {}
    for row in rows:
        id_order, message, id_customer, date_add = row
        if id_order not in resultado:
            resultado[id_order] = []
        resultado[id_order].append(
            MensajePedidoDTO(
                mensaje=message or "",
                fecha=_normalizar_datetime_legacy(date_add),
                id_cliente=id_customer,
            )
        )
    return resultado


def _mapear_pedido(
    d: dict, mensajes: dict[int, list[MensajePedidoDTO]]
) -> PedidoPSDTO:
    """Convierte un row dict en PedidoPSDTO."""
    id_pedido = d["idPedido"]
    total_sin_iva = float(d["totalSinIva"] or 0)
    total_con_iva = float(d["totalConIva"] or 0)
    tiene_iva = abs(total_con_iva - total_sin_iva) > 0.01

    dir_env = DireccionDTO(
        nombre=d["nomEnv"] or "",
        apellidos=d["apEnv"] or "",
        empresa=d["empresaEnv"] or "",
        linea1=d["dir1Env"] or "",
        linea2=d["dir2Env"] or "",
        dni=d["dniEnv"] or "",
        dni_numerico=_solo_digitos(d.get("dniEnv", "")),
        ciudad=d["ciudadEnv"] or "",
        postal=d["postalEnv"] or "",
        provincia=d["provEnv"] or "",
        pais=d["paisEnv"] or "",
        cod_pais=(d.get("codPaisEnv") or "").strip().upper(),
        id_pais=d["idPaisEnv"] or 0,
        telefono=d["telEnv"] or "",
        movil=d["movilEnv"] or "",
        otros=d["otrosEnv"] or "",
    )
    dir_fact = DireccionDTO(
        nombre=d["nomFact"] or "",
        apellidos=d["apFact"] or "",
        empresa=d["empresaFact"] or "",
        linea1=d["dir1Fact"] or "",
        linea2=d["dir2Fact"] or "",
        dni=d["dniFact"] or "",
        dni_numerico=_solo_digitos(d.get("dniFact", "")),
        ciudad=d["ciudadFact"] or "",
        postal=d["postalFact"] or "",
        provincia=d["provFact"] or "",
        pais=d["paisFact"] or "",
        cod_pais=(d.get("codPaisFact") or "").strip().upper(),
        id_pais=d["idPaisFact"] or 0,
        telefono=d["telFact"] or "",
        movil=d["movilFact"] or "",
        otros=d["otrosFact"] or "",
    )

    fecha_pedido = _normalizar_datetime_legacy(d.get("fechaPedido"))
    fecha_factura = _normalizar_datetime_legacy(d.get("fechaFactura"))

    return PedidoPSDTO(
        id_pedido=id_pedido,
        referencia=d.get("referenciaPedido") or "",
        fecha_pedido=fecha_pedido,
        fecha_factura=fecha_factura,
        modo_pago=d["pagoPedido"] or "",
        total_pagado=float(d["totalPagado"] or 0),
        total_sin_iva=total_sin_iva,
        total_con_iva=total_con_iva,
        tiene_iva=tiene_iva,
        estado_nombre=d["nombreEstado"] or "",
        estado_id=d.get("estadoPedido"),
        color_estado=d.get("colorEstado") or "#cccccc",
        internal_state_id=int(d.get("internalStateId") or 1),
        internal_state_code=d.get("internalStateCode") or "nuevo_pedido",
        internal_state_name=d.get("internalStateName") or "Nuevo Pedido",
        internal_state_color=d.get("internalStateColor") or "#2563eb",
        id_cliente=d["idCliente"],
        nombre_cliente=d["nombreCliente"] or "",
        apellidos_cliente=d["apellidosCliente"] or "",
        email_cliente=d["emailCliente"] or "",
        id_direccion_envio=d["idDirEnvio"],
        id_direccion_factura=d["idDirFactura"],
        direccion_envio=dir_env,
        direccion_factura=dir_fact,
        mensajes=mensajes.get(id_pedido, []),
    )


def _solo_digitos(texto: str | None) -> str:
    return re.sub(r"[^0-9]", "", texto or "")


def _normalizar_estado_nombre(value: str | None) -> str:
    if not value:
        return ""
    txt = str(value).strip().lower()
    txt = _RE_MULTI_SPACE.sub(" ", txt)
    txt = unicodedata.normalize("NFD", txt)
    txt = "".join(ch for ch in txt if unicodedata.category(ch) != "Mn")
    return txt


def _normalizar_datetime_legacy(value) -> datetime | None:
    """
    Normaliza fechas legacy de PrestaShop.
    Trata como nulo: None, "", "0000-00-00", "0000-00-00 00:00:00".
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())

    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")

    if isinstance(value, str):
        raw = value.strip()
        if raw in {"", "0000-00-00", "0000-00-00 00:00:00"}:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue
        logger.warning("Fecha legacy invalida en PrestaShop: %r", value)
        return None

    logger.warning("Tipo de fecha no soportado en PrestaShop: %s (%r)", type(value), value)
    return None

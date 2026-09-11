"""
Repositorio de estados internos de pedidos.

Estas tablas gp_* son auxiliares de la aplicacion y no modifican el estado real
de PrestaShop (ps_orders.current_state).
"""
from __future__ import annotations

from aiomysql import Connection


DEFAULT_INTERNAL_STATE = {
    "id_internal_state": 1,
    "code": "nuevo_pedido",
    "name": "Nuevo Pedido",
    "color": "#2563eb",
}


async def list_internal_order_states(conn: Connection) -> list[dict]:
    sql = """
        SELECT id_internal_state, code, name, color
        FROM gp_internal_order_states
        WHERE active = 1
        ORDER BY sort_order ASC, id_internal_state ASC
    """
    async with conn.cursor() as cur:
        await cur.execute(sql)
        rows = await cur.fetchall()
    return [
        {
            "id_internal_state": int(row[0] or 0),
            "code": str(row[1] or "").strip(),
            "name": str(row[2] or "").strip(),
            "color": str(row[3] or "#64748b").strip() or "#64748b",
        }
        for row in rows
    ]


async def get_active_internal_order_state(conn: Connection, id_internal_state: int) -> dict | None:
    sql = """
        SELECT id_internal_state, code, name, color
        FROM gp_internal_order_states
        WHERE id_internal_state = %s
          AND active = 1
        LIMIT 1
    """
    async with conn.cursor() as cur:
        await cur.execute(sql, (id_internal_state,))
        row = await cur.fetchone()
    if not row:
        return None
    return {
        "id_internal_state": int(row[0] or 0),
        "code": str(row[1] or "").strip(),
        "name": str(row[2] or "").strip(),
        "color": str(row[3] or "#64748b").strip() or "#64748b",
    }


async def get_internal_states_for_orders(conn: Connection, order_ids: list[int]) -> dict[int, dict]:
    ids = [int(order_id) for order_id in order_ids if int(order_id or 0) > 0]
    if not ids:
        return {}
    placeholders = ",".join(["%s"] * len(ids))
    sql = f"""
        SELECT
            gois.id_order,
            COALESCE(gis.id_internal_state, 1) AS id_internal_state,
            COALESCE(gis.code, 'nuevo_pedido') AS code,
            COALESCE(gis.name, 'Nuevo Pedido') AS name,
            COALESCE(gis.color, '#2563eb') AS color
        FROM gp_order_internal_state gois
        LEFT JOIN gp_internal_order_states gis
            ON gis.id_internal_state = gois.id_internal_state
        WHERE gois.id_order IN ({placeholders})
    """
    async with conn.cursor() as cur:
        await cur.execute(sql, ids)
        rows = await cur.fetchall()
    return {
        int(row[0] or 0): {
            "id_internal_state": int(row[1] or 1),
            "code": str(row[2] or DEFAULT_INTERNAL_STATE["code"]).strip(),
            "name": str(row[3] or DEFAULT_INTERNAL_STATE["name"]).strip(),
            "color": str(row[4] or DEFAULT_INTERNAL_STATE["color"]).strip(),
        }
        for row in rows
    }


async def prestashop_order_exists(conn: Connection, id_order: int) -> bool:
    sql = "SELECT 1 FROM ps_orders WHERE id_order = %s LIMIT 1"
    async with conn.cursor() as cur:
        await cur.execute(sql, (id_order,))
        row = await cur.fetchone()
    return bool(row)


async def set_internal_order_state(
    conn: Connection,
    id_order: int,
    id_internal_state: int,
    updated_by: str | None = None,
) -> None:
    sql = """
        INSERT INTO gp_order_internal_state (id_order, id_internal_state, updated_by)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
            id_internal_state = VALUES(id_internal_state),
            updated_by = VALUES(updated_by),
            updated_at = CURRENT_TIMESTAMP
    """
    async with conn.cursor() as cur:
        await cur.execute(sql, (id_order, id_internal_state, updated_by))

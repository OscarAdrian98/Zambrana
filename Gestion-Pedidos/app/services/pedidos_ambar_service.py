"""
services/pedidos_ambar_service.py - Lectura y decision de pedido Ambar por pedido PS.
Separa:
- visualizacion de pedidos existentes
- permiso de alta de pedido nuevo
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, date

from app.db import sqlserver_ambar
from app.repositories import ambar_pedidos_repository as rp
from app.schemas.cliente import ClienteAmbarDTO
from app.schemas.pedido import PedidoPSDTO

logger = logging.getLogger(__name__)


def _clientes_validos_lectura(candidatos: list[ClienteAmbarDTO]) -> list[ClienteAmbarDTO]:
    return [c for c in candidatos if not c.baja]


def _seleccionar_cliente_para_pedido(
    candidatos: list[ClienteAmbarDTO],
    cliente_manual_id: int | None = None,
) -> tuple[ClienteAmbarDTO | None, str]:
    if cliente_manual_id is not None:
        elegido = next((c for c in candidatos if c.numero_cliente == int(cliente_manual_id)), None)
        if elegido is None:
            return None, "El cliente Ambar seleccionado no pertenece a los candidatos del pedido."
        if elegido.baja:
            return None, "El cliente Ambar seleccionado esta de baja. Reactivalo antes de continuar."
        return elegido, ""

    activos = [c for c in candidatos if not c.baja]
    if not activos:
        return None, "No hay cliente Ambar valido para crear pedido."
    if len(activos) > 1:
        return None, "Hay multiples clientes Ambar candidatos. Seleccion manual pendiente."
    return activos[0], ""


def _es_referencia_web(linea_info: str, id_pedido_ps: int, referencia_ps: str) -> bool:
    info = (linea_info or "").upper()
    id_txt = str(id_pedido_ps or "").strip()
    ref = (referencia_ps or "").strip().upper()
    if not info:
        return False
    if id_txt and f"PEDIDO WEB ID {id_txt}" in info:
        return True
    if ref and (f"PEDIDO WEB REF {ref}" in info or f"PEDIDO WEB REF. {ref}" in info):
        return True
    return False


def _es_referencia_por_id(linea_info: str, id_pedido_ps: int) -> bool:
    info = (linea_info or "").upper()
    id_txt = str(id_pedido_ps or "").strip()
    return bool(info and id_txt and f"PEDIDO WEB ID {id_txt}" in info)


def _es_referencia_por_ref(linea_info: str, referencia_ps: str) -> bool:
    info = (linea_info or "").upper()
    ref = (referencia_ps or "").strip().upper()
    if not info or not ref:
        return False
    return f"PEDIDO WEB REF {ref}" in info or f"PEDIDO WEB REF. {ref}" in info


def _es_probable_equivalente(pedido_ambar: dict, pedido_ps: PedidoPSDTO) -> bool:
    try:
        fecha_ambar = datetime.strptime(pedido_ambar.get("fecha", ""), "%Y-%m-%d").date()
    except ValueError:
        return False
    fecha_ps = pedido_ps.fecha_pedido.date() if pedido_ps.fecha_pedido else date.today()
    delta_dias = abs((fecha_ambar - fecha_ps).days)
    if delta_dias > 10:
        return False
    return abs(float(pedido_ambar.get("importe_total", 0)) - float(pedido_ps.total_con_iva)) <= 0.50


def _ordenar_pedidos_desc(pedidos: list[dict]) -> list[dict]:
    def _key(p: dict):
        try:
            fecha = datetime.strptime(p.get("fecha", "") or "", "%Y-%m-%d")
        except ValueError:
            fecha = datetime.min
        return (fecha, int(p.get("codigo", 0) or 0))

    return sorted(pedidos, key=_key, reverse=True)


def _preparar_contexto_pedidos_sync(
    pedidos: list[PedidoPSDTO],
    matches_por_pedido: dict[int, list[ClienteAmbarDTO]],
    seleccion_manual_por_pedido: dict[int, int] | None = None,
) -> dict[int, dict]:
    contexto: dict[int, dict] = {}
    cliente_ids: set[int] = set()

    for pedido in pedidos:
        candidatos = matches_por_pedido.get(pedido.id_pedido, [])
        clientes_lectura = _clientes_validos_lectura(candidatos)
        requiere_seleccion_manual = len(clientes_lectura) > 1
        cliente_manual = (seleccion_manual_por_pedido or {}).get(pedido.id_pedido)
        cliente, motivo_cli = _seleccionar_cliente_para_pedido(candidatos, cliente_manual_id=cliente_manual)
        puede_crear = True
        puede_mostrar_accion = True
        motivo = ""

        if not clientes_lectura:
            puede_crear = False
            puede_mostrar_accion = False
            motivo = "No hay cliente Ambar valido para crear pedido."
        elif cliente is None:
            puede_crear = False
            motivo = motivo_cli

        contexto[pedido.id_pedido] = {
            "cliente_id": cliente.numero_cliente if cliente else None,
            "clientes_lectura_ids": [c.numero_cliente for c in clientes_lectura],
            "requiere_seleccion_manual": requiere_seleccion_manual,
            "pedidos_existentes": [],
            "pedido_mas_reciente": None,
            "pedido_existente_exacto": None,
            "pedido_probable": None,
            "puede_mostrar_accion": puede_mostrar_accion,
            "puede_crear": puede_crear,
            "motivo_bloqueo": motivo,
        }
        for c in clientes_lectura:
            cliente_ids.add(c.numero_cliente)

    if not cliente_ids:
        return contexto

    with sqlserver_ambar.get_connection() as conn:
        pedidos_batch = rp.obtener_pedidos_recientes_clientes_batch(
            conn,
            sorted(cliente_ids),
            top_por_cliente=8,
        )

    for pedido in pedidos:
        row = contexto[pedido.id_pedido]
        lectura_ids = row["clientes_lectura_ids"]
        if not lectura_ids:
            continue
        existentes: list[dict] = []
        for cli_id in lectura_ids:
            existentes.extend(pedidos_batch.get(cli_id, []))
        existentes = _ordenar_pedidos_desc(existentes)
        row["pedidos_existentes"] = existentes
        row["pedido_mas_reciente"] = existentes[0] if existentes else None
        ref_raw = (pedido.referencia or "").strip()
        ref_norm = "" if ref_raw in {"", "-", "NULL", "null"} else ref_raw

        exacto = next(
            (
                x for x in existentes
                if _es_referencia_web(
                    x.get("linea_info", ""),
                    pedido.id_pedido,
                    ref_norm,
                )
            ),
            None,
        )
        exacto_por_id = next(
            (x for x in existentes if _es_referencia_por_id(x.get("linea_info", ""), pedido.id_pedido)),
            None,
        )
        exacto_por_ref = next(
            (x for x in existentes if _es_referencia_por_ref(x.get("linea_info", ""), ref_norm)),
            None,
        )
        if exacto:
            row["pedido_existente_exacto"] = exacto
            row["puede_mostrar_accion"] = False
            row["puede_crear"] = False
            row["motivo_bloqueo"] = f"El pedido ya existe en Ambar ({exacto.get('referencia')})."
        else:
            probable = next((x for x in existentes if _es_probable_equivalente(x, pedido)), None)
            if probable:
                row["pedido_probable"] = probable
                row["puede_mostrar_accion"] = False
                row["puede_crear"] = False
                row["motivo_bloqueo"] = (
                    "Existe pedido muy probable por cliente/fecha/importe "
                    f"({probable.get('referencia')})."
                )

        logger.debug(
            (
                "Debug pedido_ambar pedido_ps=%s ref_ps_raw=%s ref_ps_norm=%s cliente=%s "
                "exacto_id=%s exacto_ref=%s exacto_final=%s probable=%s ped_can=%s"
            ),
            pedido.id_pedido,
            ref_raw or "-",
            ref_norm or "-",
            row["cliente_id"],
            exacto_por_id.get("referencia") if exacto_por_id else "-",
            exacto_por_ref.get("referencia") if exacto_por_ref else "-",
            row["pedido_existente_exacto"].get("referencia") if row["pedido_existente_exacto"] else "-",
            row["pedido_probable"].get("referencia") if row["pedido_probable"] else "-",
            row["puede_crear"],
        )

    return contexto


async def preparar_contexto_pedidos(
    pedidos: list[PedidoPSDTO],
    matches_por_pedido: dict[int, list[ClienteAmbarDTO]],
    seleccion_manual_por_pedido: dict[int, int] | None = None,
) -> dict[int, dict]:
    if not pedidos:
        return {}
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _preparar_contexto_pedidos_sync,
        pedidos,
        matches_por_pedido,
        seleccion_manual_por_pedido,
    )

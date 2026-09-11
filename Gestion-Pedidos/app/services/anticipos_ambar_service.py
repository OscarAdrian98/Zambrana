"""
services/anticipos_ambar_service.py - Lectura y decision de anticipos Ambar por pedido.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, date

from app.db import sqlserver_ambar
from app.repositories import anticipos_repository as ra
from app.schemas.anticipo import AnticipoCabDTO
from app.schemas.cliente import ClienteAmbarDTO
from app.schemas.pedido import PedidoPSDTO
from app.services import anticipo_service
from app.utils.mapeo_pago import mapear_pago

logger = logging.getLogger(__name__)


def _clientes_validos_lectura(candidatos: list[ClienteAmbarDTO]) -> list[ClienteAmbarDTO]:
    return [c for c in candidatos if not c.baja]


def _seleccionar_cliente_para_anticipo(
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
        return None, "Cliente no existe en Ambar o esta de baja."
    if len(activos) > 1:
        return None, "Hay multiples clientes Ambar candidatos. Seleccion manual pendiente."
    # Legacy: el estado "bloqueado/aviso" no invalida por si mismo el registro de anticipo.
    # Solo bloqueamos por ausencia/ambiguedad de cliente, forma de pago o duplicado equivalente.
    return activos[0], ""


def _es_equivalente(anticipos: list[AnticipoCabDTO], importe_pedido: float, fecha_objetivo: date) -> AnticipoCabDTO | None:
    for a in anticipos:
        try:
            fecha_ant = datetime.strptime(a.fecha, "%Y-%m-%d").date() if a.fecha else None
        except ValueError:
            fecha_ant = None
        if fecha_ant == fecha_objetivo and abs(float(a.importe_entregado) - float(importe_pedido)) < 0.01:
            return a
    return None


def _cargar_anticipos_batch(conn, clientes_ids: set[int]) -> dict[int, list[AnticipoCabDTO]]:
    if not clientes_ids:
        return {}
    return ra.obtener_anticipos_clientes_batch(conn, sorted(clientes_ids), top_por_cliente=5)


def _ordenar_anticipos_desc(anticipos: list[AnticipoCabDTO]) -> list[AnticipoCabDTO]:
    def _key(a: AnticipoCabDTO):
        try:
            dt = datetime.strptime(a.fecha or "", "%Y-%m-%d")
        except ValueError:
            dt = datetime.min
        return (dt, int(a.codigo or 0))

    return sorted(anticipos, key=_key, reverse=True)


def _serializar_anticipo(anticipo: AnticipoCabDTO | None) -> dict | None:
    if anticipo is None:
        return None
    return {
        "codigo": int(anticipo.codigo),
        "cliente": int(anticipo.cliente),
        "fecha": anticipo.fecha,
        "importe_disponible": float(anticipo.importe_disponible),
        "importe_entregado": float(anticipo.importe_entregado),
        "forma_pago": anticipo.forma_pago,
        "banco": anticipo.banco,
        "fecha_utilizacion": anticipo.fecha_utilizacion,
    }


def _preparar_contexto_completo_sync(
    pedidos: list[PedidoPSDTO],
    matches_por_pedido: dict[int, list[ClienteAmbarDTO]],
    hora_fin_dia: str,
    seleccion_manual_por_pedido: dict[int, int] | None = None,
) -> dict[int, dict]:
    contexto: dict[int, dict] = {}
    clientes_ids: set[int] = set()

    for p in pedidos:
        candidatos = matches_por_pedido.get(p.id_pedido, [])
        clientes_lectura = _clientes_validos_lectura(candidatos)
        requiere_seleccion_manual = len(clientes_lectura) > 1
        cliente_manual = (seleccion_manual_por_pedido or {}).get(p.id_pedido)
        cliente, motivo_cli = _seleccionar_cliente_para_anticipo(candidatos, cliente_manual_id=cliente_manual)
        info_pago = mapear_pago(p.modo_pago)
        fecha_obj = (
            anticipo_service.calcular_fecha_anticipo(p.fecha_pedido, hora_fin_dia)
            if p.fecha_pedido else date.today()
        )

        puede = True
        puede_mostrar_accion = True
        motivo = ""
        if not clientes_lectura:
            puede = False
            puede_mostrar_accion = False
            motivo = "Cliente no existe en Ambar o esta de baja."
        elif not info_pago.permite_anticipo:
            puede = False
            puede_mostrar_accion = False
            motivo = "La forma de pago no permite anticipo segun reglas legacy."
        elif cliente is None:
            puede = False
            motivo = motivo_cli

        contexto[p.id_pedido] = {
            "cliente": cliente,
            "cliente_id": cliente.numero_cliente if cliente else None,
            "cc_cliente": cliente.cuenta_contable if cliente else "",
            "clientes_lectura_ids": [c.numero_cliente for c in clientes_lectura],
            "requiere_seleccion_manual": requiere_seleccion_manual,
            "forma_pago_ambar": info_pago.codigo_ambar,
            "cod_banco": info_pago.codigo_banco,
            "permite_anticipo_pago": info_pago.permite_anticipo,
            "fecha_objetivo": fecha_obj.strftime("%Y-%m-%d"),
            "anticipos": [],
            "anticipo_mas_reciente": None,
            "equivalente": None,
            "equivalentes_por_cliente": {},
            "anticipo_mas_reciente_por_cliente": {},
            "puede_mostrar_accion": puede_mostrar_accion,
            "puede_registrar": puede,
            "motivo_bloqueo": motivo,
            "importe_pedido": float(p.total_con_iva),
        }
        for c in clientes_lectura:
            clientes_ids.add(c.numero_cliente)

    with sqlserver_ambar.get_connection() as conn:
        anticipos_batch = _cargar_anticipos_batch(conn, clientes_ids)

    for p in pedidos:
        row = contexto[p.id_pedido]
        lectura_ids = row["clientes_lectura_ids"]
        if not lectura_ids:
            continue
        anticipos: list[AnticipoCabDTO] = []
        for cli_id in lectura_ids:
            anticipos.extend(anticipos_batch.get(cli_id, []))
        anticipos = _ordenar_anticipos_desc(anticipos)
        row["anticipos"] = anticipos
        row["anticipo_mas_reciente"] = anticipos[0] if anticipos else None
        equivalentes_por_cliente: dict[str, dict | None] = {}
        recientes_por_cliente: dict[str, dict | None] = {}
        for cli_id in lectura_ids:
            anticipos_cliente = _ordenar_anticipos_desc(anticipos_batch.get(cli_id, []))
            reciente = anticipos_cliente[0] if anticipos_cliente else None
            equivalente_cli = _es_equivalente(
                anticipos=anticipos_cliente,
                importe_pedido=row["importe_pedido"],
                fecha_objetivo=datetime.strptime(row["fecha_objetivo"], "%Y-%m-%d").date(),
            )
            recientes_por_cliente[str(cli_id)] = _serializar_anticipo(reciente)
            equivalentes_por_cliente[str(cli_id)] = _serializar_anticipo(equivalente_cli)
        row["anticipo_mas_reciente_por_cliente"] = recientes_por_cliente
        row["equivalentes_por_cliente"] = equivalentes_por_cliente
        if row["cliente_id"]:
            equivalente = _es_equivalente(
                anticipos=anticipos_batch.get(row["cliente_id"], []),
                importe_pedido=row["importe_pedido"],
                fecha_objetivo=datetime.strptime(row["fecha_objetivo"], "%Y-%m-%d").date(),
            )
            row["equivalente"] = equivalente
            if equivalente and row["puede_registrar"]:
                row["puede_registrar"] = False
                row["motivo_bloqueo"] = (
                    "Ya existe anticipo equivalente "
                    f"(cod {equivalente.codigo}, {equivalente.importe_entregado:.2f} EUR, {equivalente.fecha})."
                )
    return contexto


async def preparar_contexto_anticipos(
    pedidos: list[PedidoPSDTO],
    matches_por_pedido: dict[int, list[ClienteAmbarDTO]],
    hora_fin_dia: str,
    seleccion_manual_por_pedido: dict[int, int] | None = None,
) -> dict[int, dict]:
    if not pedidos:
        return {}
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _preparar_contexto_completo_sync,
        pedidos,
        matches_por_pedido,
        hora_fin_dia,
        seleccion_manual_por_pedido,
    )

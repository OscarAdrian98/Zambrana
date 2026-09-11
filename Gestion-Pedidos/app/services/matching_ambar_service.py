"""
services/matching_ambar_service.py - Matching lectura PrestaShop <-> Ambar.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time

from app.db import sqlserver_ambar
from app.repositories import clientes_repository
from app.schemas.pedido import PedidoPSDTO
from app.schemas.cliente import ClienteAmbarDTO

logger = logging.getLogger(__name__)


def _normalizar_email(value: str | None) -> str:
    return (value or "").strip().lower()


def _normalizar_nif(value: str | None) -> str:
    raw = (value or "").strip().upper()
    return re.sub(r"[^A-Z0-9]", "", raw)


def _construir_claves_pedidos(pedidos: list[PedidoPSDTO]) -> list[dict]:
    data: list[dict] = []
    for pedido in pedidos:
        data.append(
            {
                "id_pedido": pedido.id_pedido,
                "email": _normalizar_email(pedido.email_cliente),
                "dni_num_envio": _normalizar_nif(pedido.direccion_envio.dni),
                "dni_num_factura": _normalizar_nif(pedido.direccion_factura.dni),
            }
        )
    return data


def _buscar_matches_sync(pedidos_data: list[dict]) -> dict[int, list[ClienteAmbarDTO]]:
    with sqlserver_ambar.get_connection() as conn:
        return clientes_repository.buscar_clientes_batch(conn, pedidos_data)


async def buscar_matches_clientes(
    pedidos: list[PedidoPSDTO],
) -> dict[int, list[ClienteAmbarDTO]]:
    """
    Ejecuta matching contra Ambar por lote.
    """
    if not pedidos:
        return {}

    t_total_start = time.monotonic()
    t_prep_start = time.monotonic()
    pedidos_data = _construir_claves_pedidos(pedidos)
    t_prep_ms = (time.monotonic() - t_prep_start) * 1000
    n_emails = len({(p.get("email") or "") for p in pedidos_data if (p.get("email") or "")})
    n_nifs = len(
        {
            (p.get("dni_num_envio") or "")
            for p in pedidos_data
            if (p.get("dni_num_envio") or "")
        }.union(
            {
                (p.get("dni_num_factura") or "")
                for p in pedidos_data
                if (p.get("dni_num_factura") or "")
            }
        )
    )

    loop = asyncio.get_event_loop()
    matches = await loop.run_in_executor(None, _buscar_matches_sync, pedidos_data)
    t_total_ms = (time.monotonic() - t_total_start) * 1000
    n_candidatos = sum(len(v) for v in matches.values())
    logger.info(
        "Matching Ambar prep_keys_ms=%.2f total_ms=%.2f pedidos=%d claves_email=%d claves_nif=%d candidatos=%d",
        t_prep_ms,
        t_total_ms,
        len(pedidos),
        n_emails,
        n_nifs,
        n_candidatos,
    )
    return matches

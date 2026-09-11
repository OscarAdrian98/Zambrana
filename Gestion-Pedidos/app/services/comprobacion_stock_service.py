"""
services/comprobacion_stock_service.py - Comprobacion de stock y facturacion por pedido.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _tiene_stock_suficiente(stock_total: float, cantidad_pedida: int) -> bool:
    return stock_total >= 2 and stock_total >= cantidad_pedida


def construir_resultado_comprobacion_stock(
    *,
    pedido_ps: dict,
    stock_por_referencia: dict[str, dict],
) -> dict:
    lineas_resultado: list[dict] = []
    warnings: list[str] = []
    lineas_revisar = 0

    for linea in pedido_ps.get("lineas", []):
        ref = str(linea.get("product_reference") or "").strip()
        nombre = str(linea.get("product_name") or "").strip()
        cantidad = int(linea.get("product_quantity") or 0)
        id_order_detail = int(linea.get("id_order_detail") or 0)
        articulo = stock_por_referencia.get(ref) if ref else None

        if not ref or not articulo:
            estado = "Referencia no encontrada en Ambar / usaría SC"
            mensaje = "Referencia no encontrada en Ambar. Revisar artículo."
            stock_total = 0.0
            articulo_ambar = "SC"
            lineas_revisar += 1
            warnings.append(mensaje)
            logger.warning(
                "referencia no encontrada en Ambar id_pedido=%s ref=%s product_name=%s",
                pedido_ps["id_order"],
                ref or "-",
                nombre or "-",
            )
        else:
            articulo_ambar = articulo["articulo"]
            stock_total = float(articulo.get("stock_total") or 0)
            if stock_total <= 0:
                estado = "Sin stock"
                mensaje = "Sin stock."
            elif stock_total < cantidad:
                estado = "Stock bajo"
                mensaje = "Stock insuficiente para la cantidad pedida."
            elif stock_total < 2:
                estado = "Stock bajo"
                mensaje = "Stock inferior a 2."
            elif _tiene_stock_suficiente(stock_total, cantidad):
                estado = "OK"
                mensaje = "Stock suficiente."
            else:
                estado = "Revisar"
                mensaje = "Revisar stock del artículo."

            if estado != "OK":
                lineas_revisar += 1
                warnings.append(mensaje)
                logger.warning(
                    "stock insuficiente id_pedido=%s ref=%s cantidad=%s stock=%s",
                    pedido_ps["id_order"],
                    ref or "-",
                    cantidad,
                    stock_total,
                )

        lineas_resultado.append(
            {
                "id_order_detail": id_order_detail,
                "referencia_ps": ref,
                "nombre_producto": nombre,
                "cantidad_pedida": cantidad,
                "articulo_ambar": articulo_ambar,
                "stock_ambar_total": stock_total,
                "estado_linea": estado,
                "mensaje_linea": mensaje,
                "ok": estado == "OK",
            }
        )

    pagado = bool(pedido_ps.get("paid"))
    ok_global = pagado and lineas_revisar == 0

    mensajes_globales: list[str] = []
    if not pagado:
        mensajes_globales.append("El pedido no consta como pagado en PrestaShop.")
    if lineas_revisar == 0 and pagado:
        mensajes_globales.append("Pedido pagado y todos los productos tienen stock suficiente. OK para facturar.")
    elif lineas_revisar > 0:
        mensajes_globales.append(
            f"Revisar antes de facturar: {'el pedido no está pagado y ' if not pagado else ''}"
            f"hay {lineas_revisar} producto(s) que requieren comprobación."
        )

    return {
        "pedido": pedido_ps,
        "lineas": lineas_resultado,
        "pagado": pagado,
        "ok_global": ok_global,
        "resultado_global": "OK PARA FACTURAR" if ok_global else "REVISAR ANTES DE FACTURAR",
        "mensajes_globales": mensajes_globales,
        "lineas_revisar": lineas_revisar,
    }

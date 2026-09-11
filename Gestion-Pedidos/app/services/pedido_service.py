"""
services/pedido_service.py - Logica de negocio para crear pedidos en Ambar.
Separa lectura PS de insercion final defensiva en Ambar.
"""
from __future__ import annotations

import logging
from datetime import datetime

import pyodbc
from aiomysql import Connection as MySQLConn

from app.repositories import ambar_pedidos_repository as rpv
from app.schemas.anticipo import CrearPedidoAmbarRequestDTO, CrearPedidoAmbarResponseDTO
from app.utils.mapeo_pago import mapear_pago
from app.utils.paises import es_portugal, iva_para_pais, requiere_dua

logger = logging.getLogger(__name__)


def crear_pedido_ambar_desde_datos(
    ambar_conn: pyodbc.Connection,
    req: CrearPedidoAmbarRequestDTO,
    datos_ps: dict,
    strict_production: bool = False,
) -> CrearPedidoAmbarResponseDTO:
    """
    Insercion real en Ambar con comprobaciones defensivas finales.
    """
    try:
        if not datos_ps:
            return CrearPedidoAmbarResponseDTO(
                ok=False,
                mensaje=f"Pedido {req.id_pedido_ps} no encontrado en PrestaShop.",
            )

        if req.id_cliente_ambar <= 0:
            return CrearPedidoAmbarResponseDTO(ok=False, mensaje="Cliente Ambar invalido para crear pedido.")

        if float(datos_ps.get("total_con_iva") or 0) <= 0:
            return CrearPedidoAmbarResponseDTO(ok=False, mensaje="Importe total invalido para crear pedido.")

        if not datos_ps.get("lineas_productos"):
            return CrearPedidoAmbarResponseDTO(ok=False, mensaje="El pedido no tiene lineas de producto.")

        referencia_ps_raw = str(datos_ps.get("referencia") or datos_ps.get("reference") or "").strip()
        referencia_ps_norm = "" if referencia_ps_raw in {"", "-", "NULL", "null"} else referencia_ps_raw
        id_pedido_ps = int(req.id_pedido_ps)
        if not referencia_ps_norm:
            referencia_ps_norm = str(id_pedido_ps)
        logger.debug(
            "Alta pedido check exacto pedido_ps=%s ref_ps_raw=%s ref_ps_norm=%s",
            id_pedido_ps,
            referencia_ps_raw or "-",
            referencia_ps_norm or "-",
        )

        # 1) Duplicado exacto por referencia web (red de seguridad fuerte).
        exacto_detalle = rpv.buscar_pedido_web_existente_detalle(
            ambar_conn,
            [req.id_cliente_ambar],
            id_pedido_ps=id_pedido_ps,
            referencia_ps=referencia_ps_norm,
        )
        ref_exacto = exacto_detalle["resultado_final"]
        logger.debug(
            "Alta pedido exacto pre id=%s ref=%s bloquear=%s",
            exacto_detalle["resultado_por_id"] or "-",
            exacto_detalle["resultado_por_ref"] or "-",
            exacto_detalle["bloquear"],
        )
        if ref_exacto:
            return CrearPedidoAmbarResponseDTO(
                ok=False,
                referencia=ref_exacto,
                mensaje=f"Pedido web ya registrado en Ambar: {ref_exacto}",
            )

        # 2) Duplicado probable por fecha+importe+cliente.
        ref_probable = rpv.pedido_ya_existe(
            ambar_conn,
            [req.id_cliente_ambar],
            str(datos_ps.get("fecha_pedido") or ""),
            float(datos_ps.get("total_con_iva") or 0),
        )
        if ref_probable:
            return CrearPedidoAmbarResponseDTO(
                ok=False,
                referencia=ref_probable,
                mensaje=f"Ya existe un pedido equivalente en Ambar: {ref_probable}",
            )

        if strict_production and not referencia_ps_norm:
            return CrearPedidoAmbarResponseDTO(
                ok=False,
                mensaje="En produccion se exige referencia web valida para crear pedido.",
            )

        codigo_pedido = rpv.obtener_proximo_codigo_pedido(ambar_conn)

        iva_pct = iva_para_pais(datos_ps["id_pais_entrega"])
        tiene_iva = bool(datos_ps["tiene_iva"])
        total_con_iva = float(datos_ps["total_con_iva"])
        total_sin_iva_real = (
            round(total_con_iva / (iva_pct / 100 + 1), 2)
            if tiene_iva and iva_pct > 0
            else float(datos_ps["total_sin_iva"])
        )
        cuota_iva = round(total_con_iva - total_sin_iva_real, 2) if tiene_iva else 0.0
        venta_oss = "S" if es_portugal(datos_ps["nombre_pais_entrega"]) else "N"

        cabecera = {
            "id_cliente": req.id_cliente_ambar,
            "id_pedido_ps": id_pedido_ps,
            "referencia_ps": referencia_ps_norm,
            "porcentaje_iva": iva_pct,
            "base_sin_iva": total_sin_iva_real,
            "total_con_iva": total_con_iva,
            "cuota_iva": cuota_iva,
            "tiene_iva": tiene_iva,
            "modo_pago_ambar": mapear_pago(datos_ps["modo_pago"]).codigo_ambar,
            "nombre_entrega": datos_ps["nombre_entrega"],
            "direccion_entrega": datos_ps["direccion_entrega"],
            "postal_entrega": datos_ps["postal_entrega"],
            "ciudad_entrega": datos_ps["ciudad_entrega"],
            "provincia_entrega": datos_ps["provincia_entrega"],
            "telefono_entrega": datos_ps["telefono_entrega"],
            "venta_oss": venta_oss,
        }

        lineas = construir_lineas_pedido(datos_ps, iva_pct, tiene_iva)
        # Relectura defensiva final justo antes de insertar para cerrar ventana de duplicado.
        exacto_detalle_final = rpv.buscar_pedido_web_existente_detalle(
            ambar_conn,
            [req.id_cliente_ambar],
            id_pedido_ps=id_pedido_ps,
            referencia_ps=referencia_ps_norm,
        )
        logger.debug(
            "Alta pedido exacto pre-insert id=%s ref=%s bloquear=%s",
            exacto_detalle_final["resultado_por_id"] or "-",
            exacto_detalle_final["resultado_por_ref"] or "-",
            exacto_detalle_final["bloquear"],
        )
        if exacto_detalle_final["bloquear"]:
            ref_block = exacto_detalle_final["resultado_final"] or "-"
            return CrearPedidoAmbarResponseDTO(
                ok=False,
                referencia=ref_block,
                mensaje=f"Pedido web ya registrado en Ambar: {ref_block}",
            )
        codigo = rpv.insertar_pedido_completo(ambar_conn, codigo_pedido, cabecera, lineas)

        return CrearPedidoAmbarResponseDTO(
            ok=True,
            serie="W",
            codigo=codigo,
            referencia=f"W-{codigo}",
            mensaje=f"Pedido registrado correctamente: W-{codigo}",
        )
    except Exception as exc:
        logger.error("Error creando pedido Ambar para PS #%d: %s", req.id_pedido_ps, exc)
        return CrearPedidoAmbarResponseDTO(ok=False, mensaje=f"Error: {exc}")


async def leer_pedido_prestashop_para_ambar(conn: MySQLConn, id_pedido: int) -> dict | None:
    """Lee todos los datos de PrestaShop necesarios para crear pedido Ambar."""
    sql_cab = """
        SELECT
            o.reference, o.id_carrier, o.payment,
            o.total_paid AS total_pagado,
            o.total_paid_tax_excl AS total_sin_iva,
            o.total_paid_tax_incl AS total_con_iva,
            o.total_products_wt AS total_prod_con_iva,
            o.total_products AS total_prod_sin_iva,
            o.total_shipping_tax_incl AS total_envio_con_iva,
            o.total_shipping_tax_excl AS total_envio_sin_iva,
            SUM(od.total_shipping_price_tax_incl * od.product_quantity) AS portes_adicionales,
            CASE WHEN o.module='cashondeliveryplus'
                 THEN CAST(cfg.value AS DECIMAL(10,2)) ELSE 0 END AS portes_reembolso,
            (o.total_shipping_tax_incl
             - SUM(od.total_shipping_price_tax_incl * od.product_quantity)
             - CASE WHEN o.module='cashondeliveryplus'
                    THEN CAST(cfg.value AS DECIMAL(10,2)) ELSE 0 END) AS portes_transportista,
            o.date_add AS fecha_pedido,
            o.payment_fee AS impuesto_paypal,
            ca.name AS nombre_transporte,
            CONCAT(a.lastname,' ',a.firstname) AS nombre_entrega,
            a.address1 AS direccion_entrega,
            a.postcode AS postal_entrega,
            a.city AS ciudad_entrega,
            IFNULL(s.name,'') AS provincia_entrega,
            cl.id_country AS id_pais_entrega,
            cl.name AS nombre_pais_entrega,
            a.phone_mobile AS telefono_entrega
        FROM ps_orders o
        INNER JOIN ps_carrier ca ON o.id_carrier=ca.id_carrier
        INNER JOIN ps_address a ON o.id_address_delivery=a.id_address
        INNER JOIN ps_order_detail od ON o.id_order=od.id_order
        INNER JOIN ps_country_lang cl ON a.id_country=cl.id_country AND cl.id_lang=1
        LEFT JOIN ps_state s ON a.id_state=s.id_state
        LEFT JOIN ps_configuration cfg ON cfg.name='COD_FEE'
        WHERE o.id_order=%s
        GROUP BY o.id_order
    """
    sql_lineas = """
        SELECT
            od.id_order_detail AS id_order_detail,
            od.product_reference AS referencia,
            od.product_name AS nombre,
            od.product_quantity AS cantidad,
            od.reduction_percent AS dcto_pct,
            od.unit_price_tax_excl AS precio_sin_iva,
            od.unit_price_tax_incl AS precio_con_iva,
            od.total_price_tax_excl AS total_sin_iva,
            od.total_price_tax_incl AS total_con_iva,
            od.total_shipping_price_tax_excl AS portes_sin_iva,
            od.total_shipping_price_tax_incl AS portes_con_iva
        FROM ps_order_detail od WHERE od.id_order=%s
    """
    sql_desc = """
        SELECT name AS nombre, value AS valor,
               value_tax_excl AS valor_sin_iva, free_shipping
        FROM ps_order_cart_rule WHERE id_order=%s
    """
    async with conn.cursor() as cur:
        await cur.execute(sql_cab, (id_pedido,))
        row_cab = await cur.fetchone()
        if not row_cab:
            return None
        cols = [d[0] for d in cur.description]
        cab = dict(zip(cols, row_cab))

        await cur.execute(sql_lineas, (id_pedido,))
        rows_lin = await cur.fetchall()
        cols_lin = [d[0] for d in cur.description]
        lineas = [dict(zip(cols_lin, r)) for r in rows_lin]

        await cur.execute(sql_desc, (id_pedido,))
        rows_desc = await cur.fetchall()
        cols_desc = [d[0] for d in cur.description]
        descuentos = [dict(zip(cols_desc, r)) for r in rows_desc]

    total_prod_con = float(cab["total_prod_con_iva"] or 0)
    total_prod_sin = float(cab["total_prod_sin_iva"] or 0)
    tiene_iva = abs(total_prod_con - total_prod_sin) > 0.01

    fecha_pedido = cab["fecha_pedido"]
    fecha_iso = fecha_pedido.strftime("%Y-%m-%d") if fecha_pedido else datetime.now().strftime("%Y-%m-%d")
    return {
        **{
            k: (float(v) if isinstance(v, (int, float)) else v)
            for k, v in cab.items()
        },
        "fecha_pedido": fecha_iso,
        "modo_pago": cab.get("payment") or "",
        "tiene_iva": tiene_iva,
        "lineas_productos": lineas,
        "descuentos": descuentos,
    }


def construir_lineas_pedido(datos: dict, iva_pct: int, tiene_iva: bool) -> list[dict]:
    """Construye lineas de pedido en orden legacy."""
    lineas: list[dict] = []
    divisor_iva = (iva_pct / 100 + 1) if iva_pct > 0 else 1

    for lin in datos.get("lineas_productos", []):
        referencia = str(lin.get("referencia") or "").strip()
        precio_sin = float(lin["precio_sin_iva"] or 0)
        total_sin = float(lin["total_sin_iva"] or 0)
        portes_sin = float(lin["portes_sin_iva"] or 0)
        cantidad = int(lin["cantidad"] or 1)
        precio_con = float(lin["precio_con_iva"] or 0)
        portes_sin_real = portes_sin if precio_con == precio_sin else portes_sin / divisor_iva
        nombre = (lin["nombre"] or "").replace("'", " ").replace('"', " ")

        lineas.append(
            {
                "tipo": "producto",
                "id_order_detail": int(lin.get("id_order_detail") or 0),
                "referencia": referencia,
                "nombre": nombre[:80],
                "cantidad": cantidad,
                "precio_unitario_sin_iva": precio_sin,
                "total_sin_iva": total_sin,
                "iva": iva_pct,
                "portes_sin_iva": portes_sin_real,
            }
        )

    for desc in datos.get("descuentos", []):
        valor_sin_iva = abs(float(desc["valor_sin_iva"] or 0))
        if valor_sin_iva <= 0:
            continue
        lineas.append(
            {
                "tipo": "descuento",
                "nombre": (desc["nombre"] or "DESCUENTO WEB")[:60],
                "valor_sin_iva": valor_sin_iva,
                "iva": iva_pct,
            }
        )

    impuesto_paypal = float(datos.get("impuesto_paypal") or 0)
    if "paypal" in (datos.get("payment") or datos.get("modo_pago", "")).lower() and impuesto_paypal > 0:
        lineas.append(
            {
                "tipo": "paypal",
                "iva": iva_pct,
                "importe_con_iva": impuesto_paypal,
                "importe_sin_iva": round(impuesto_paypal / divisor_iva, 2),
            }
        )

    modo_pago = (datos.get("payment") or datos.get("modo_pago", "")).lower()
    portes_reembolso = float(datos.get("portes_reembolso") or 0)
    total_envio = float(datos.get("total_envio_con_iva") or 0)
    if "reembolso" in modo_pago and total_envio > 0:
        precio_reembolso = round(portes_reembolso / divisor_iva, 2) if portes_reembolso > 0 else 0
        lineas.append({"tipo": "reembolso", "iva": iva_pct, "precio_sin_iva": precio_reembolso})

    lineas.append({"tipo": "separador"})

    portes_transportista = float(datos.get("portes_transportista") or 0)
    precio_transp_sin = round(portes_transportista / divisor_iva, 2) if portes_transportista > 0 else 0
    nombre_transp = (datos.get("nombre_transporte") or "TRANSPORTE").upper()
    lineas.append(
        {
            "tipo": "transporte",
            "codigo_transportista": "PW",
            "nombre_transportista": nombre_transp[:60],
            "iva": iva_pct,
            "precio_sin_iva": precio_transp_sin,
        }
    )

    if requiere_dua(datos.get("id_pais_entrega", 0)):
        lineas.append({"tipo": "dua", "iva": iva_pct})

    return lineas

"""
repositories/ambar_pedidos_repository.py - Insercion de pedidos de venta en Ambar.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import pyodbc

logger = logging.getLogger(__name__)

SERIE_PEDIDOS_WEB = "W"


def _resolver_articulo_producto(
    cursor: pyodbc.Cursor,
    *,
    pedido_ps: int,
    id_order_detail: int,
    referencia_ps: str | None,
    product_name: str,
    cantidad: float,
) -> tuple[str, str, bool]:
    referencia = str(referencia_ps or "").strip()
    product_name_up = str(product_name or "").strip().upper()[:80]

    if referencia:
        cursor.execute(
            """
            SELECT TOP 1 [Artículo], [Descripción]
            FROM [Artículos]
            WHERE [Artículo] = ?
            """,
            (referencia,),
        )
        row = cursor.fetchone()
        if row:
            articulo = str(row[0] or "").strip() or referencia
            descripcion = str(row[1] or "").strip() or product_name_up
            logger.info(
                (
                    "Alta pedido línea producto pedido_ps=%s id_order_detail=%s "
                    "ref_ps=%s articulo_ambar=%s existe_ambar=True"
                ),
                pedido_ps,
                id_order_detail,
                referencia,
                articulo,
            )
            return articulo, descripcion[:80], True

    if referencia:
        cursor.execute(
            "SELECT COUNT(1) FROM [Artículos] WHERE [Artículo] = ?",
            (referencia,),
        )
        existe_ref = int((cursor.fetchone() or [0])[0]) > 0
        if existe_ref:
            raise RuntimeError(
                f"Resolucion invalida de articulo: la referencia '{referencia}' existe en Ambar pero se iba a usar SC."
            )

    logger.warning(
        (
            "Alta pedido línea producto pedido_ps=%s id_order_detail=%s ref_ps=%s "
            "articulo_ambar=SC existe_ambar=False fallback=SC product_name=%s cantidad=%s "
            "motivo=referencia no encontrada en Ambar, se usa SC"
        ),
        pedido_ps,
        id_order_detail,
        referencia or "-",
        product_name_up or "-",
        cantidad,
    )
    return "SC", product_name_up, False


def _log_insert_step(step: str, columnas: int, valores: int) -> None:
    logger.debug("Alta pedido SQL paso=%s columnas=%d valores=%d", step, columnas, valores)


def _raise_step_error(step: str, exc: Exception) -> None:
    raise RuntimeError(f"Paso SQL '{step}' fallo: {exc}") from exc


def _execute_step(
    cursor: pyodbc.Cursor,
    step: str,
    sql: str,
    params: tuple | list | None = None,
    columnas: int | None = None,
    valores: int | None = None,
) -> None:
    if columnas is not None and valores is not None:
        _log_insert_step(step, columnas, valores)
    try:
        if params is None:
            cursor.execute(sql)
        else:
            cursor.execute(sql, params)
    except Exception as exc:
        _raise_step_error(step, exc)


def obtener_pedidos_recientes_clientes_batch(
    conn: pyodbc.Connection,
    numeros_cliente: list[int],
    top_por_cliente: int = 8,
) -> dict[int, list[dict]]:
    if not numeros_cliente:
        return {}

    placeholders = ",".join(["?"] * len(numeros_cliente))
    sql = f"""
        WITH ped AS (
            SELECT
                pvc.Cliente,
                pvc.Serie,
                pvc.Codigo,
                pvc.Fecha,
                pvc.ImporteTotalE,
                pvc.FormaPago,
                ROW_NUMBER() OVER (
                    PARTITION BY pvc.Cliente
                    ORDER BY pvc.Fecha DESC, pvc.Codigo DESC
                ) AS rn
            FROM PedidosVentaCab pvc
            WHERE pvc.Cliente IN ({placeholders})
        )
        SELECT
            p.Cliente,
            p.Serie,
            p.Codigo,
            p.Fecha,
            p.ImporteTotalE,
            p.FormaPago,
            ISNULL(pvl.[Descripción], '') AS linea_info
        FROM ped p
        LEFT JOIN PedidosVentaLin pvl
               ON pvl.Serie = p.Serie
              AND pvl.Codigo = p.Codigo
              AND pvl.Linea = 1
        WHERE p.rn <= ?
        ORDER BY p.Cliente, p.Fecha DESC, p.Codigo DESC
    """
    cursor = conn.cursor()
    cursor.execute(sql, [*numeros_cliente, top_por_cliente])
    rows = cursor.fetchall()

    resultado: dict[int, list[dict]] = {}
    for row in rows:
        cliente, serie, codigo, fecha, importe_total, forma_pago, linea_info = row
        if isinstance(fecha, datetime):
            fecha_str = fecha.strftime("%Y-%m-%d")
        elif fecha:
            fecha_str = fecha.strftime("%Y-%m-%d")
        else:
            fecha_str = ""
        resultado.setdefault(int(cliente), []).append(
            {
                "cliente": int(cliente),
                "serie": str(serie or ""),
                "codigo": int(codigo or 0),
                "referencia": f"{serie}-{codigo}",
                "fecha": fecha_str,
                "importe_total": float(importe_total or 0),
                "forma_pago": str(forma_pago or ""),
                "linea_info": str(linea_info or ""),
            }
        )
    return resultado


def obtener_stock_articulos_batch(
    conn: pyodbc.Connection,
    referencias: list[str],
) -> dict[str, dict]:
    referencias_norm = [str(ref or "").strip() for ref in referencias if str(ref or "").strip()]
    if not referencias_norm:
        return {}

    logger.info("Comprobación stock Ambar refs=%s", ",".join(referencias_norm))
    placeholders = ",".join(["?"] * len(referencias_norm))
    sql = f"""
        SELECT
            LTRIM(RTRIM(a.[Artículo])) AS articulo,
            a.[Descripción],
            COALESCE(MAX(s.StockUd1), 0) AS stock_total
        FROM [Artículos] a
        LEFT JOIN [Stocks] s
            ON LTRIM(RTRIM(s.[Artículo])) = LTRIM(RTRIM(a.[Artículo]))
        WHERE LTRIM(RTRIM(a.[Artículo])) IN ({placeholders})
        GROUP BY LTRIM(RTRIM(a.[Artículo])), a.[Descripción]
    """
    cursor = conn.cursor()
    cursor.execute(sql, referencias_norm)
    rows = cursor.fetchall()
    resultado = {
        str(row[0] or "").strip(): {
            "articulo": str(row[0] or "").strip(),
            "descripcion": str(row[1] or "").strip(),
            "stock_total": float(row[2] or 0),
        }
        for row in rows
    }
    for ref in referencias_norm:
        row = resultado.get(ref)
        if row:
            logger.info(
                "Comprobación stock Ambar ref=%s existe_ambar=True stock_ud1=%s",
                ref,
                row["stock_total"],
            )
        else:
            logger.info(
                "Comprobación stock Ambar ref=%s existe_ambar=False stock_ud1=0",
                ref,
            )
    return resultado


def buscar_pedido_web_existente(
    conn: pyodbc.Connection,
    numeros_cliente: list[int],
    id_pedido_ps: int | None = None,
    referencia_ps: str | None = None,
) -> Optional[str]:
    detalle = buscar_pedido_web_existente_detalle(
        conn=conn,
        numeros_cliente=numeros_cliente,
        id_pedido_ps=id_pedido_ps,
        referencia_ps=referencia_ps,
    )
    return detalle["resultado_final"]


def buscar_pedido_web_existente_detalle(
    conn: pyodbc.Connection,
    numeros_cliente: list[int],
    id_pedido_ps: int | None = None,
    referencia_ps: str | None = None,
) -> dict:
    ref_raw = (referencia_ps or "").strip()
    ref_norm = "" if ref_raw in {"", "-", "NULL", "null"} else ref_raw
    id_ps = int(id_pedido_ps) if id_pedido_ps else None
    if not numeros_cliente or (not ref_norm and not id_ps):
        return {
            "ref_raw": ref_raw,
            "ref_norm": ref_norm,
            "id_pedido_ps": id_ps,
            "resultado_por_id": None,
            "resultado_por_ref": None,
            "resultado_final": None,
            "bloquear": False,
        }

    placeholders = ",".join(["?"] * len(numeros_cliente))
    sql_base = f"""
        SELECT TOP 1 pvc.Serie + '-' + CAST(pvc.Codigo AS VARCHAR) AS ref
        FROM PedidosVentaCab pvc
        INNER JOIN PedidosVentaLin pvl
                ON pvl.Serie = pvc.Serie
               AND pvl.Codigo = pvc.Codigo
               AND pvl.Linea = 1
        WHERE pvc.Cliente IN ({placeholders})
          AND {{cond}}
        ORDER BY pvc.Fecha DESC, pvc.Codigo DESC
    """
    cursor = conn.cursor()
    resultado_id: Optional[str] = None
    resultado_ref: Optional[str] = None

    if id_ps:
        sql_id = sql_base.format(cond="UPPER(ISNULL(pvl.[Descripción], '')) LIKE UPPER(?)")
        cursor.execute(sql_id, [*numeros_cliente, f"%PEDIDO WEB ID {id_ps}%"])
        row = cursor.fetchone()
        resultado_id = row[0] if row else None

    if ref_norm:
        sql_ref = sql_base.format(
            cond=(
                "UPPER(ISNULL(pvl.[Descripción], '')) LIKE UPPER(?) "
                "OR UPPER(ISNULL(pvl.[Descripción], '')) LIKE UPPER(?)"
            )
        )
        cursor.execute(
            sql_ref,
            [*numeros_cliente, f"%PEDIDO WEB REF {ref_norm}%", f"%PEDIDO WEB REF. {ref_norm}%"],
        )
        row = cursor.fetchone()
        resultado_ref = row[0] if row else None

    resultado_final = resultado_id or resultado_ref
    bloquear = bool(resultado_final)
    logger.debug(
        (
            "Busqueda pedido exacto detalle cliente=%s pedido_ps=%s ref_raw=%s ref_norm=%s "
            "exacto_id=%s exacto_ref=%s bloquear=%s resultado=%s"
        ),
        ",".join(str(x) for x in numeros_cliente[:5]),
        id_ps or "-",
        ref_raw or "-",
        ref_norm or "-",
        resultado_id or "-",
        resultado_ref or "-",
        bloquear,
        resultado_final or "-",
    )
    return {
        "ref_raw": ref_raw,
        "ref_norm": ref_norm,
        "id_pedido_ps": id_ps,
        "resultado_por_id": resultado_id,
        "resultado_por_ref": resultado_ref,
        "resultado_final": resultado_final,
        "bloquear": bloquear,
    }


def pedido_ya_existe(
    conn: pyodbc.Connection,
    numeros_cliente: list[int],
    fecha_pedido_str: str,
    importe_total: float,
) -> Optional[str]:
    if not numeros_cliente:
        return None
    placeholders = ",".join(["?"] * len(numeros_cliente))
    sql = f"""
        SELECT TOP 1 Serie + '-' + CAST(Codigo AS VARCHAR) AS ref
        FROM PedidosVentaCab
        WHERE Cliente IN ({placeholders})
          AND Fecha BETWEEN DATEADD(DAY, -10, CONVERT(DATE, ?))
                       AND DATEADD(DAY,  10, CONVERT(DATE, ?))
          AND ImporteTotalE BETWEEN ? AND ?
        ORDER BY Fecha DESC
    """
    try:
        cursor = conn.cursor()
        cursor.execute(
            sql,
            [
                *numeros_cliente,
                fecha_pedido_str,
                fecha_pedido_str,
                importe_total - 0.5,
                importe_total + 0.5,
            ],
        )
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception as exc:
        logger.error("Error verificando pedido duplicado: %s", exc)
        return None


def obtener_proximo_codigo_pedido(conn: pyodbc.Connection) -> int:
    sql = """
        SELECT Valor FROM Config
        WHERE Grupo = 'CONTADORES DE DOCUMENTOS'
          AND Variable = 'PEDIDO DE VENTA W'
    """
    cursor = conn.cursor()
    cursor.execute(sql)
    row = cursor.fetchone()
    if not row:
        raise RuntimeError("No se encontro el contador de pedidos en Config")
    return int(row[0]) + 1


def _verificar_post_insert(cursor: pyodbc.Cursor, codigo_pedido: int) -> None:
    try:
        cursor.execute(
            "SELECT COUNT(1) FROM PedidosVentaCab WHERE Serie=? AND Codigo=?",
            (SERIE_PEDIDOS_WEB, codigo_pedido),
        )
        existe_cab = int((cursor.fetchone() or [0])[0])

        cursor.execute(
            "SELECT COUNT(1) FROM PedidosVentaLin WHERE Serie=? AND Codigo=?",
            (SERIE_PEDIDOS_WEB, codigo_pedido),
        )
        num_lineas = int((cursor.fetchone() or [0])[0])

        cursor.execute(
            """
            SELECT Valor FROM Config
            WHERE Grupo = 'CONTADORES DE DOCUMENTOS'
              AND Variable = 'PEDIDO DE VENTA W'
            """
        )
        row = cursor.fetchone()
        valor_contador = int(row[0]) if row and row[0] is not None else 0

        cursor.execute(
            """
            SELECT TOP 1
                ISNULL(Serie, ''),
                ISNULL(CAST(Codigo AS VARCHAR(20)), ''),
                ISNULL(Facturado, ''),
                ISNULL(Servido, ''),
                ISNULL(Pagado, ''),
                ISNULL(TipoDocumento, ''),
                ISNULL(FormaPago, ''),
                ISNULL(CAST(Cliente AS VARCHAR(20)), ''),
                ISNULL(CAST(ImporteTotalE AS VARCHAR(40)), ''),
                ISNULL(CAST(BaseE1 AS VARCHAR(40)), ''),
                ISNULL(CAST(CuotaIvaE1 AS VARCHAR(40)), '')
            FROM PedidosVentaCab
            WHERE Serie = ? AND Codigo = ?
            """,
            (SERIE_PEDIDOS_WEB, codigo_pedido),
        )
        cab_row = cursor.fetchone()
        if not cab_row:
            raise RuntimeError("cabecera no legible tras insercion")
        (
            serie_chk,
            codigo_chk,
            facturado_chk,
            servido_chk,
            pagado_chk,
            tipo_doc_chk,
            forma_pago_chk,
            cliente_chk,
            importe_chk,
            base_chk,
            cuota_iva_chk,
        ) = cab_row

        logger.info(
            "Alta pedido verificacion codigo=%s cabecera=%s lineas=%s contador=%s",
            codigo_pedido,
            existe_cab,
            num_lineas,
            valor_contador,
        )
        logger.info(
            (
                "Alta pedido verificacion cabecera serie=%s codigo=%s cliente=%s "
                "facturado=%s servido=%s pagado=%s tipo_doc=%s forma_pago=%s "
                "base=%s cuota_iva=%s total=%s"
            ),
            serie_chk,
            codigo_chk,
            cliente_chk,
            facturado_chk,
            servido_chk,
            pagado_chk,
            tipo_doc_chk,
            forma_pago_chk,
            base_chk,
            cuota_iva_chk,
            importe_chk,
        )
        if existe_cab != 1:
            raise RuntimeError("cabecera no encontrada tras insercion")
        if num_lineas <= 0:
            raise RuntimeError("sin lineas tras insercion")
        if valor_contador < codigo_pedido:
            raise RuntimeError("contador no actualizado correctamente")
        if str(facturado_chk).strip().upper() != "N":
            raise RuntimeError("pedido no queda en estado facturable esperado (Facturado != 'N')")
        if str(servido_chk).strip().upper() != "N":
            raise RuntimeError("pedido no queda en estado facturable esperado (Servido != 'N')")
        if str(pagado_chk).strip().upper() != "N":
            raise RuntimeError("pedido no queda en estado facturable esperado (Pagado != 'N')")
    except Exception as exc:
        _raise_step_error("verificacion_post_insert", exc)


def insertar_pedido_completo(
    conn: pyodbc.Connection,
    codigo_pedido: int,
    cabecera: dict,
    lineas: list[dict],
) -> int:
    cursor = conn.cursor()

    sql_cab = """
        INSERT INTO PedidosVentaCab (
            [Serie],[Codigo],[Fecha],[Cliente],
            [ClienteNombre],[ClienteNIF],[ClienteDirección],[ClientePoblación],
            [ClienteProvincia],[ClienteCP],[ClienteTeléfono],[ClienteFax],[ClienteEmail],
            [Almacén],[Iva1],[Rec1],[BaseE1],[ImporteTotalE],[CuotaIvaE1],[CuotaRecE1],
            [Servido],[Pagado],[FormaPago],[Vendedor],[Facturado],[IvaIncluido],
            [Creacion],[TipoDocumento],[ServirPedidoCompleto],[RecalcularPreciosServir],
            [VersionId],[FechaCreacion],
            [EntregaNombre],[EntregaDireccion],[EntregaCP],
            [EntregaPoblacion],[EntregaProvincia],[EntregaTelefono],[VentaOSS]
        ) VALUES (
            ?,?,CONVERT(Date,GETDATE()),?,
            (SELECT [Nombre] FROM Clientes WHERE Cliente=?),
            (SELECT [NIF] FROM Clientes WHERE Cliente=?),
            (SELECT [Dirección] FROM Clientes WHERE Cliente=?),
            (SELECT [Población] FROM Clientes WHERE Cliente=?),
            (SELECT [Provincia] FROM Clientes WHERE Cliente=?),
            (SELECT [CP] FROM Clientes WHERE Cliente=?),
            (SELECT [Teléfono] FROM Clientes WHERE Cliente=?),
            (SELECT [Fax] FROM Clientes WHERE Cliente=?),
            (SELECT [email] FROM Clientes WHERE Cliente=?),
            '1',?,0,?,?,?,0,'N','N',?,2,'N','N',
            CONCAT('WEB|',FORMAT(GETDATE(),'dd/MM/yyyy HH:mm:ss')),
            'N','N','N',0,GETDATE(),
            ?,?,?,?,?,?,?
        )
    """
    c = cabecera
    id_cli = c["id_cliente"]
    id_pedido_ps = int(c.get("id_pedido_ps") or 0)
    logger.info(
        (
            "Alta pedido cabecera serie=%s codigo=%s cliente=%s pedido_ps=%s ref_ps=%s "
            "base=%.2f cuota_iva=%.2f total=%.2f forma_pago=%s iva=%s venta_oss=%s"
        ),
        SERIE_PEDIDOS_WEB,
        codigo_pedido,
        id_cli,
        id_pedido_ps or "-",
        c.get("referencia_ps") or "-",
        float(c["base_sin_iva"] or 0),
        float(c["cuota_iva"] or 0),
        float(c["total_con_iva"] or 0),
        c.get("modo_pago_ambar") or "-",
        c.get("porcentaje_iva") or 0,
        c.get("venta_oss") or "-",
    )
    params_cab = (
        SERIE_PEDIDOS_WEB,
        codigo_pedido,
        id_cli,
        id_cli,
        id_cli,
        id_cli,
        id_cli,
        id_cli,
        id_cli,
        id_cli,
        id_cli,
        id_cli,
        c["porcentaje_iva"],
        c["base_sin_iva"],
        c["total_con_iva"],
        c["cuota_iva"],
        c["modo_pago_ambar"],
        c["nombre_entrega"],
        c["direccion_entrega"],
        c["postal_entrega"],
        c["ciudad_entrega"],
        c["provincia_entrega"],
        c["telefono_entrega"],
        c["venta_oss"],
    )
    _execute_step(cursor, "cabecera", sql_cab, params_cab, columnas=39, valores=39)

    contador_lineas = 0
    contador_lineas += 1
    linea_info_text = f"--- PEDIDO WEB REF. {c['referencia_ps']} ---"
    logger.debug("Alta pedido SQL linea_informativa_text=%s", linea_info_text)
    _execute_step(
        cursor,
        "linea_informativa",
        "INSERT INTO [PedidosVentaLin] ([Serie],[Codigo],[Linea],[Descripción]) VALUES (?,?,?,?)",
        (SERIE_PEDIDOS_WEB, codigo_pedido, contador_lineas, linea_info_text),
        columnas=4,
        valores=4,
    )

    sql_linea = """
        INSERT INTO [PedidosVentaLin] (
            [Serie],[Codigo],[Linea],[Almacén],[Artículo],[Descripción],
            [Cantidad],[Cantidad2],[Dcto],[Iva],[CantidadServida],[Servido],
            [PrecioE],[TotalE]
        ) VALUES (
            ?,?,?,1,
            ?,?,
            ?,0,0,?,0,'N',?,?
        )
    """
    sql_suplem = """
        INSERT INTO [PedidosVentaLin] (
            [Serie],[Codigo],[Linea],[Almacén],[Artículo],[Descripción],
            [Cantidad],[Cantidad2],[Dcto],[Iva],[CantidadServida],[Servido],
            [PrecioE],[TotalE]
        ) VALUES (?,?,?,1,'SC','SUPLEMENTO POR VOLUMEN',?,0,0,?,0,'N',?,?)
    """

    for lin in lineas:
        if lin["tipo"] == "producto":
            contador_lineas += 1
            total_linea_sin_iva = round(float(lin["precio_unitario_sin_iva"]) * float(lin["cantidad"]), 2)
            articulo_ambar, descripcion_ambar, _ = _resolver_articulo_producto(
                cursor,
                pedido_ps=id_pedido_ps,
                id_order_detail=int(lin.get("id_order_detail") or 0),
                referencia_ps=lin.get("referencia"),
                product_name=lin.get("nombre") or "",
                cantidad=float(lin.get("cantidad") or 0),
            )
            _execute_step(
                cursor,
                "linea_producto",
                sql_linea,
                (
                    SERIE_PEDIDOS_WEB,
                    codigo_pedido,
                    contador_lineas,
                    articulo_ambar,
                    descripcion_ambar,
                    lin["cantidad"],
                    lin["iva"],
                    lin["precio_unitario_sin_iva"],
                    total_linea_sin_iva,
                ),
                columnas=14,
                valores=14,
            )
            if lin.get("portes_sin_iva", 0) > 0:
                contador_lineas += 1
                _execute_step(
                    cursor,
                    "linea_suplemento",
                    sql_suplem,
                    (
                        SERIE_PEDIDOS_WEB,
                        codigo_pedido,
                        contador_lineas,
                        lin["cantidad"],
                        lin["iva"],
                        lin["portes_sin_iva"],
                        lin["portes_sin_iva"] * lin["cantidad"],
                    ),
                    columnas=14,
                    valores=14,
                )

        elif lin["tipo"] == "descuento":
            contador_lineas += 1
            _execute_step(
                cursor,
                "linea_descuento",
                """
                INSERT INTO [PedidosVentaLin]
                    ([Serie],[Codigo],[Linea],[Almacén],[Artículo],[Descripción],
                     [Cantidad],[Cantidad2],[Dcto],[Iva],[CantidadServida],[Servido],
                     [PrecioE],[TotalE])
                VALUES (?,?,?,1,'SC',UPPER(?),1,0,0,?,0,'N',?,?)
                """,
                (
                    SERIE_PEDIDOS_WEB,
                    codigo_pedido,
                    contador_lineas,
                    f"CUPON WEB: {lin['nombre']}",
                    lin["iva"],
                    -lin["valor_sin_iva"],
                    -lin["valor_sin_iva"],
                ),
                columnas=14,
                valores=14,
            )

        elif lin["tipo"] == "paypal":
            contador_lineas += 1
            _execute_step(
                cursor,
                "linea_paypal",
                """
                INSERT INTO [PedidosVentaLin]
                    ([Serie],[Codigo],[Linea],[Almacén],[Artículo],[Descripción],
                     [Cantidad],[Cantidad2],[Dcto],[Iva],[CantidadServida],[Servido],
                     [PrecioE],[TotalE])
                VALUES (?,?,?,1,'PAYPAL','RECARGO PAGO POR PAYPAL',1,0,0,?,0,'N',
                    (SELECT CASE WHEN [IvaRégimen]='N' THEN ? ELSE ? END
                     FROM [Clientes] WHERE [Cliente]=?),
                    (SELECT CASE WHEN [IvaRégimen]='N' THEN ? ELSE ? END
                     FROM [Clientes] WHERE [Cliente]=?))
                """,
                (
                    SERIE_PEDIDOS_WEB,
                    codigo_pedido,
                    contador_lineas,
                    lin["iva"],
                    lin["importe_con_iva"],
                    lin["importe_sin_iva"],
                    id_cli,
                    lin["importe_con_iva"],
                    lin["importe_sin_iva"],
                    id_cli,
                ),
                columnas=14,
                valores=14,
            )

        elif lin["tipo"] == "reembolso":
            contador_lineas += 1
            _execute_step(
                cursor,
                "linea_reembolso",
                """
                INSERT INTO [PedidosVentaLin]
                    ([Serie],[Codigo],[Linea],[Almacén],[Artículo],[Descripción],
                     [Cantidad],[Cantidad2],[Dcto],[Iva],[CantidadServida],[Servido],
                     [PrecioE],[TotalE])
                VALUES (?,?,?,1,'RE','GASTOS DE REEMBOLSO',1,0,0,?,0,'N',?,?)
                """,
                (
                    SERIE_PEDIDOS_WEB,
                    codigo_pedido,
                    contador_lineas,
                    lin["iva"],
                    lin["precio_sin_iva"],
                    lin["precio_sin_iva"],
                ),
                columnas=14,
                valores=14,
            )

        elif lin["tipo"] == "separador":
            contador_lineas += 1
            _execute_step(
                cursor,
                "linea_separador",
                "INSERT INTO [PedidosVentaLin] ([Serie],[Codigo],[Linea]) VALUES (?,?,?)",
                (SERIE_PEDIDOS_WEB, codigo_pedido, contador_lineas),
                columnas=3,
                valores=3,
            )

        elif lin["tipo"] == "transporte":
            contador_lineas += 1
            _execute_step(
                cursor,
                "linea_transporte",
                """
                INSERT INTO [PedidosVentaLin]
                    ([Serie],[Codigo],[Linea],[Almacén],[Artículo],[Descripción],
                     [Cantidad],[Cantidad2],[Dcto],[Iva],[CantidadServida],[Servido],
                     [PrecioE],[TotalE])
                VALUES (?,?,?,1,?,?,1,0,0,?,0,'N',?,?)
                """,
                (
                    SERIE_PEDIDOS_WEB,
                    codigo_pedido,
                    contador_lineas,
                    lin["codigo_transportista"],
                    lin["nombre_transportista"],
                    lin["iva"],
                    lin["precio_sin_iva"],
                    lin["precio_sin_iva"],
                ),
                columnas=14,
                valores=14,
            )

        elif lin["tipo"] == "dua":
            contador_lineas += 1
            _execute_step(
                cursor,
                "linea_dua",
                """
                INSERT INTO [PedidosVentaLin]
                    ([Serie],[Codigo],[Linea],[Almacén],[Artículo],[Descripción],
                     [Cantidad],[Cantidad2],[Dcto],[Iva],[CantidadServida],[Servido],
                     [PrecioE],[TotalE])
                VALUES (?,?,?,1,'DUA',
                    '--- T2LF - MERCANCIA SIN DUA DE EXPEDICION (INCLUIDO EN PORTES) ---',
                    1,0,0,?,0,'N',0,0)
                """,
                (SERIE_PEDIDOS_WEB, codigo_pedido, contador_lineas, lin["iva"]),
                columnas=14,
                valores=14,
            )

    _execute_step(
        cursor,
        "actualizar_contador",
        """
        UPDATE [Config] SET [Valor] = ?
        WHERE [Grupo] = 'CONTADORES DE DOCUMENTOS'
          AND [Variable] = 'PEDIDO DE VENTA W'
        """,
        (str(codigo_pedido),),
    )

    tiene_iva = cabecera.get("tiene_iva", True)
    iva_pct = cabecera["porcentaje_iva"]
    _ejecutar_recalculo_reciclaje(cursor, codigo_pedido, tiene_iva, iva_pct)
    _verificar_post_insert(cursor, codigo_pedido)

    conn.commit()
    logger.info("Pedido Ambar W-%d creado (%d lineas)", codigo_pedido, contador_lineas)
    return codigo_pedido


def _ejecutar_recalculo_reciclaje(
    cursor: pyodbc.Cursor,
    codigo_pedido: int,
    tiene_iva: bool,
    iva_pct: int,
) -> None:
    if tiene_iva:
        sql_update_reciclaje = f"""
            UPDATE PedidosVentaCab SET
                IvaLibre1   = {iva_pct},
                RecLibre1   = 5.2,
                IvaLibre2   = {iva_pct},
                RecLibre2   = 5.2,
                CuotaRecDivisa1 = 0
            WHERE Serie='W' AND Codigo=?
        """
    else:
        sql_update_reciclaje = """
            UPDATE PedidosVentaCab SET
                IvaLibre1   = 0,
                RecLibre1   = 0,
                IvaLibre2   = 0,
                RecLibre2   = 0,
                CuotaRecDivisa1 = 0
            WHERE Serie='W' AND Codigo=?
        """

    sql_reciclaje = f"""
        DECLARE @imp FLOAT;
        SET @imp = (
            SELECT TOP 1 acum FROM (
                SELECT SUM(Importe) AS acum
                FROM Categorias c
                INNER JOIN [Artículos] a ON c.Categoria = a.CategoriaReciclaje
                INNER JOIN PedidosVentaLin pvl ON a.[Artículo] = pvl.[Artículo]
                WHERE pvl.Serie='W' AND pvl.Codigo={codigo_pedido}
                GROUP BY pvl.Serie, pvl.Codigo
                UNION SELECT 0
            ) tmp ORDER BY acum DESC
        );
        SET @imp = ROUND(@imp, 2);
        IF @imp >= 0.01
        BEGIN
            UPDATE PedidosVentaCab
            SET ImporteLibreE2 = @imp, DescuentoE1 = @imp
            WHERE Serie='W' AND Codigo={codigo_pedido};
        END
    """
    try:
        _execute_step(cursor, "recalculo_reciclaje", sql_reciclaje)
        _execute_step(cursor, "actualizar_iva_libre", sql_update_reciclaje, (codigo_pedido,))
    except Exception as exc:
        logger.warning("Advertencia recalculando reciclaje: %s", exc)

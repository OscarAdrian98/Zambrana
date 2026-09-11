import logging
import hashlib
import json
from datetime import date, datetime, timedelta
from app.database.db import get_connection
from app.services.eventos_service import registrar_evento
from app.services.productos_service import ajustar_stock
import calendar


# ==========================================================
# GENERAR HASH DE INTEGRIDAD
# ==========================================================
def generar_hash_documento(documento_id, cursor):
    cursor.execute(
        """
        SELECT numero_legal, fecha, cliente_id, total
        FROM documentos
        WHERE id = ?
        """,
        (documento_id,),
    )
    cabecera = cursor.fetchone()

    if not cabecera:
        raise Exception(f"No se encontró documento ID {documento_id} para hash")

    cursor.execute(
        """
        SELECT descripcion, cantidad, precio, iva, total
        FROM documento_lineas
        WHERE documento_id = ?
        ORDER BY id
        """,
        (documento_id,),
    )
    lineas = cursor.fetchall()

    data = {
        "numero_legal": cabecera[0],
        "fecha": cabecera[1],
        "cliente_id": cabecera[2],
        "total": cabecera[3],
        "lineas": lineas,
    }

    data_str = json.dumps(data, sort_keys=True)
    return hashlib.sha256(data_str.encode()).hexdigest()


# ==========================================================
# GENERAR NÚMERO LEGAL DE FACTURA
# ==========================================================
def generar_numero_legal(tipo_documento="FACTURA"):
    año = date.today().year
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN IMMEDIATE")

        cursor.execute(
            "SELECT ultimo FROM numeracion WHERE tipo = ? AND año = ?",
            (tipo_documento, año),
        )
        row = cursor.fetchone()

        if row:
            siguiente = row[0] + 1
            cursor.execute(
                "UPDATE numeracion SET ultimo = ? WHERE tipo = ? AND año = ?",
                (siguiente, tipo_documento, año),
            )
        else:
            siguiente = 1
            cursor.execute(
                "INSERT INTO numeracion (tipo, año, ultimo) VALUES (?, ?, ?)",
                (tipo_documento, año, siguiente),
            )

        conn.commit()

        prefijo = "F" if tipo_documento == "FACTURA" else "R"
        numero = f"{prefijo}-{año}-{siguiente:06d}"

        logging.info(f"Número legal generado: {numero}")
        return numero

    except Exception:
        conn.rollback()
        logging.exception("Error al generar número legal")
        raise
    finally:
        conn.close()


# ==========================================================
# CALCULAR FECHA DE VENCIMIENTO
# ==========================================================
def calcular_fecha_vencimiento(fecha_factura, tipo_vencimiento="30D", dia_pago=None):

    dias_map = {
        "10D": 10,
        "15D": 15,
        "30D": 30,
        "60D": 60,
        "90D": 90,
    }

    dias = dias_map.get(tipo_vencimiento, 30)

    fecha = datetime.strptime(fecha_factura, "%Y-%m-%d")
    fecha_base = fecha + timedelta(days=dias)

    # Si no hay día de pago → comportamiento actual
    if not dia_pago:
        return fecha_base.strftime("%Y-%m-%d")

    año = fecha_base.year
    mes = fecha_base.month

    ultimo_dia = calendar.monthrange(año, mes)[1]

    # Si el día de pago es mayor que el último día del mes
    dia = min(int(dia_pago), ultimo_dia)

    fecha_final = fecha_base.replace(day=dia)

    return fecha_final.strftime("%Y-%m-%d")


# ==========================================================
# PROCESAR STOCK SEGÚN LÍNEAS
# ==========================================================
def _procesar_stock_documento(cursor, documento_id, tipo_movimiento):
    """
    tipo_movimiento:
        'SALIDA'  -> resta stock
        'ENTRADA' -> suma stock
    """

    cursor.execute(
        """
        SELECT producto_id, cantidad
        FROM documento_lineas
        WHERE documento_id = ?
          AND producto_id IS NOT NULL
        """,
        (documento_id,),
    )

    lineas = cursor.fetchall()

    for producto_id, cantidad in lineas:

        if tipo_movimiento == "SALIDA":
            ajustar_stock(
                producto_id,
                -cantidad,
                "SALIDA",
                f"Factura ID {documento_id}",
                cursor_externo=cursor,  # AQUÍ ESTÁ EL CAMBIO
            )

        elif tipo_movimiento == "ENTRADA":
            ajustar_stock(
                producto_id,
                cantidad,
                "ENTRADA",
                f"Rectificativa ID {documento_id}",
                cursor_externo=cursor,
            )


# ==========================================================
# ACTUALIZAR FORMA DE PAGO
# ==========================================================
def actualizar_pago_factura(factura_id, forma_pago, tipo_vencimiento=None):

    if factura_bloqueada(factura_id):
        raise Exception("Factura bloqueada. No se puede modificar.")

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT d.cliente_id, d.fecha
            FROM documentos d
            WHERE d.id = ? AND d.tipo = 'FACTURA'
            """,
            (factura_id,),
        )
        row = cursor.fetchone()

        if not row:
            raise Exception("Factura no encontrada")

        cliente_id, fecha_factura = row

        if forma_pago == "DOMICILIACION":
            if not tipo_vencimiento:
                tipo_vencimiento = "30D"

            fecha_vencimiento = calcular_fecha_vencimiento(
                fecha_factura, tipo_vencimiento
            )

            cursor.execute("SELECT iban FROM clientes WHERE id = ?", (cliente_id,))
            row_iban = cursor.fetchone()
            iban = row_iban[0] if row_iban and row_iban[0] else None

            if not iban:
                raise Exception(
                    "El cliente no tiene IBAN. No se puede asignar domiciliación."
                )

            cursor.execute(
                """
                UPDATE documentos
                SET forma_pago = ?,
                    tipo_vencimiento = ?,
                    fecha_vencimiento = ?,
                    iban = ?,
                    estado_cobro = 'PENDIENTE'
                WHERE id = ? AND tipo = 'FACTURA'
                """,
                (
                    forma_pago,
                    tipo_vencimiento,
                    fecha_vencimiento,
                    iban,
                    factura_id,
                ),
            )
        else:
            cursor.execute(
                """
                UPDATE documentos
                SET forma_pago = ?,
                    tipo_vencimiento = NULL,
                    iban = NULL
                WHERE id = ? AND tipo = 'FACTURA'
                """,
                (forma_pago, factura_id),
            )

        conn.commit()
        registrar_evento(factura_id, "FACTURA", "FORMA_PAGO_ACTUALIZADA", forma_pago)

    except Exception:
        conn.rollback()
        logging.exception(f"Error al actualizar forma de pago factura ID={factura_id}")
        raise
    finally:
        conn.close()


# ==========================================================
# CONVERTIR ALBARÁN EN FACTURA
# ==========================================================
def convertir_albaran_a_factura(
    albaran_id,
    tipo_vencimiento="30D",
    forma_pago="CONTADO",
    iban=None,
):

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # ==================================================
        # Obtener datos albarán
        # ==================================================
        cursor.execute(
            """
            SELECT cliente_id, total, bloqueada
            FROM documentos
            WHERE id = ? AND tipo = 'ALBARAN'
            """,
            (albaran_id,),
        )

        albaran = cursor.fetchone()

        if not albaran:
            return None

        cliente_id, total, bloqueada = albaran

        if bloqueada:
            raise Exception("Este albarán ya está facturado.")

        fecha = date.today().isoformat()
        numero_legal = generar_numero_legal()
        fecha_vencimiento = calcular_fecha_vencimiento(fecha, tipo_vencimiento)

        # ==================================================
        # Crear FACTURA
        # ==================================================
        cursor.execute(
            """
            INSERT INTO documentos (
                tipo, numero, numero_legal, fecha, fecha_vencimiento,
                cliente_id, total, estado, forma_pago,
                tipo_vencimiento, iban, estado_cobro, creado_en
            )
            VALUES (
                'FACTURA',
                ?, ?, ?, ?, ?, ?,
                'PENDIENTE',
                ?, ?, ?,
                'PENDIENTE',
                ?
            )
            """,
            (
                numero_legal,
                numero_legal,
                fecha,
                fecha_vencimiento,
                cliente_id,
                total,
                forma_pago,
                tipo_vencimiento,
                iban,
                fecha,
            ),
        )

        factura_id = cursor.lastrowid

        # ==================================================
        # Copiar líneas (CON producto_id)
        # ==================================================
        cursor.execute(
            """
            SELECT producto_id, descripcion, cantidad, precio, iva, total
            FROM documento_lineas
            WHERE documento_id = ?
            """,
            (albaran_id,),
        )

        lineas = cursor.fetchall()

        for producto_id, desc, cant, precio, iva, total_linea in lineas:

            cursor.execute(
                """
                INSERT INTO documento_lineas
                (documento_id, producto_id, descripcion, cantidad, precio, iva, total)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (factura_id, producto_id, desc, cant, precio, iva, total_linea),
            )

        # ==================================================
        # DESCONTAR STOCK (sistema centralizado)
        # ==================================================
        _procesar_stock_documento(cursor, factura_id, "SALIDA")

        # ==================================================
        # Bloquear albarán
        # ==================================================
        cursor.execute(
            """
            UPDATE documentos
            SET bloqueada = 1
            WHERE id = ? AND tipo = 'ALBARAN'
            """,
            (albaran_id,),
        )

        # ==================================================
        # HASH INTEGRIDAD
        # ==================================================
        hash_val = generar_hash_documento(factura_id, cursor)
        cursor.execute(
            "UPDATE documentos SET hash = ? WHERE id = ?",
            (hash_val, factura_id),
        )

        conn.commit()

        registrar_evento(
            factura_id,
            "FACTURA",
            "CREADA_DESDE_ALBARAN",
            f"Origen ID {albaran_id}",
        )

        return factura_id

    except Exception:
        conn.rollback()
        logging.exception(f"Error al convertir albarán ID={albaran_id} en factura")
        raise

    finally:
        conn.close()


# ==========================================================
# CREAR FACTURA DIRECTA (SIN ALBARÁN)
# ==========================================================
def crear_factura_directa(
    cliente_id,
    lineas,
    forma_pago="CONTADO",
    tipo_vencimiento="30D",
    fecha=None,
    dia_pago=None,
):
    """
    lineas: lista de dicts con:
        producto_id (opcional)
        descripcion
        cantidad
        precio
        iva
    """

    from datetime import date, datetime

    if not lineas:
        raise Exception("No se puede crear una factura sin líneas.")

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # ==================================================
        # VALIDAR FECHA (FORMATO INTERNO ISO YYYY-MM-DD)
        # ==================================================
        if not fecha:
            fecha_iso = date.today().isoformat()
        else:
            try:
                fecha_obj = datetime.strptime(fecha, "%Y-%m-%d")
                fecha_iso = fecha_obj.strftime("%Y-%m-%d")
            except ValueError:
                raise Exception("Formato de fecha inválido. Usa YYYY-MM-DD")

        numero_legal = generar_numero_legal("FACTURA")

        # NUEVO → cálculo con día de pago
        fecha_vencimiento = calcular_fecha_vencimiento(
            fecha_iso, tipo_vencimiento, dia_pago
        )

        total_factura = 0

        # ==================================================
        # CALCULAR TOTAL
        # ==================================================
        for l in lineas:
            if l["cantidad"] <= 0:
                raise Exception("La cantidad debe ser mayor que 0.")

            total_linea = l["cantidad"] * l["precio"] * (1 + l["iva"] / 100)
            total_factura += total_linea

        # ==================================================
        # CREAR FACTURA
        # ==================================================
        cursor.execute(
            """
            INSERT INTO documentos (
                tipo, numero, numero_legal, fecha, fecha_vencimiento,
                cliente_id, total, estado, forma_pago,
                tipo_vencimiento, dia_pago, estado_cobro, creado_en
            )
            VALUES (
                'FACTURA',
                ?, ?, ?, ?, ?, ?,
                'PENDIENTE',
                ?, ?, ?, 'PENDIENTE',
                ?
            )
            """,
            (
                numero_legal,
                numero_legal,
                fecha_iso,
                fecha_vencimiento,
                cliente_id,
                total_factura,
                forma_pago,
                tipo_vencimiento,
                dia_pago,
                fecha_iso,
            ),
        )

        factura_id = cursor.lastrowid

        # ==================================================
        # INSERTAR LÍNEAS
        # ==================================================
        for l in lineas:

            total_linea = l["cantidad"] * l["precio"] * (1 + l["iva"] / 100)

            cursor.execute(
                """
                INSERT INTO documento_lineas
                (documento_id, producto_id, descripcion, cantidad, precio, iva, total)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    factura_id,
                    l.get("producto_id"),
                    l["descripcion"],
                    l["cantidad"],
                    l["precio"],
                    l["iva"],
                    total_linea,
                ),
            )

        # ==================================================
        # CONTROL STOCK CENTRALIZADO
        # ==================================================
        _procesar_stock_documento(cursor, factura_id, "SALIDA")

        # ==================================================
        # HASH INTEGRIDAD
        # ==================================================
        hash_val = generar_hash_documento(factura_id, cursor)
        cursor.execute(
            "UPDATE documentos SET hash = ? WHERE id = ?",
            (hash_val, factura_id),
        )

        conn.commit()

        registrar_evento(
            factura_id,
            "FACTURA",
            "CREADA_DIRECTA",
            f"Factura creada directa - Fecha {fecha_iso}",
        )

        return factura_id

    except Exception:
        conn.rollback()
        logging.exception("Error al crear factura directa")
        raise

    finally:
        conn.close()


# ==========================================================
# CREAR FACTURA RECTIFICATIVA
# ==========================================================
def crear_factura_rectificativa(
    factura_original_id,
    motivo,
    lineas_rectificar,
    fecha=None,
):

    from datetime import datetime, date

    if not lineas_rectificar:
        raise Exception("No hay líneas para rectificar.")

    conn = get_connection()
    cursor = conn.cursor()

    try:

        # ================================
        # OBTENER FACTURA ORIGINAL
        # ================================
        cursor.execute(
            """
            SELECT cliente_id, estado, forma_pago, tipo_vencimiento, iban
            FROM documentos
            WHERE id = ? AND tipo = 'FACTURA'
            """,
            (factura_original_id,),
        )

        original = cursor.fetchone()

        if not original:
            raise Exception("Factura original no encontrada.")

        (
            cliente_id,
            estado_orig,
            forma_pago_orig,
            tipo_vencimiento,
            iban,
        ) = original

        # ================================
        # VALIDAR FECHA (ES o ISO)
        # ================================
        if not fecha:
            fecha_iso = date.today().isoformat()
        else:
            try:
                # formato español
                fecha_iso = datetime.strptime(fecha, "%d/%m/%Y").strftime("%Y-%m-%d")
            except ValueError:
                try:
                    # formato ISO
                    fecha_iso = datetime.strptime(fecha, "%Y-%m-%d").strftime(
                        "%Y-%m-%d"
                    )
                except ValueError:
                    raise Exception("Formato de fecha inválido. Usa DD/MM/YYYY")

        numero_legal = generar_numero_legal("RECTIFICATIVA")

        estado = "PAGADA" if estado_orig == "PAGADA" else "PENDIENTE"

        # ================================
        # CALCULAR TOTAL RECTIFICATIVA
        # ================================
        total_rectificativa = 0

        for l in lineas_rectificar:

            if "cantidad" not in l or "precio" not in l or "iva" not in l:
                raise Exception("Línea de rectificación inválida.")

            cantidad = float(l["cantidad"])
            precio = float(l["precio"])
            iva = float(l["iva"])

            total_linea = cantidad * precio * (1 + iva / 100)

            total_rectificativa += total_linea

        # asegurar total negativo
        total_rectificativa = -abs(total_rectificativa)

        # ================================
        # CREAR DOCUMENTO RECTIFICATIVO
        # ================================
        cursor.execute(
            """
            INSERT INTO documentos (
                tipo, numero, numero_legal, fecha, cliente_id, total,
                estado, forma_pago, tipo_vencimiento,
                iban, estado_cobro, factura_rectificada_id,
                motivo_rectificacion, creado_en
            )
            VALUES (
                'FACTURA',
                ?, ?, ?, ?, ?,
                ?, ?, ?,
                ?, 'PENDIENTE', ?, ?, ?
            )
            """,
            (
                numero_legal,
                numero_legal,
                fecha_iso,
                cliente_id,
                total_rectificativa,
                estado,
                forma_pago_orig,
                tipo_vencimiento,
                iban,
                factura_original_id,
                motivo,
                fecha_iso,
            ),
        )

        rectificativa_id = cursor.lastrowid

        # ================================
        # INSERTAR LÍNEAS RECTIFICADAS
        # ================================
        for l in lineas_rectificar:

            cantidad = float(l["cantidad"])
            precio = float(l["precio"])
            iva = float(l["iva"])

            total_linea = cantidad * precio * (1 + iva / 100)

            cursor.execute(
                """
                INSERT INTO documento_lineas
                (documento_id, producto_id, descripcion, cantidad, precio, iva, total)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rectificativa_id,
                    l.get("producto_id"),
                    l["descripcion"],
                    -cantidad,
                    precio,
                    iva,
                    -abs(total_linea),
                ),
            )

        # ================================
        # DEVOLVER STOCK
        # ================================
        _procesar_stock_documento(cursor, rectificativa_id, "ENTRADA")

        # ================================
        # HASH DE INTEGRIDAD
        # ================================
        hash_val = generar_hash_documento(rectificativa_id, cursor)

        cursor.execute(
            "UPDATE documentos SET hash = ? WHERE id = ?",
            (hash_val, rectificativa_id),
        )

        conn.commit()

        # ================================
        # REGISTRAR EVENTO
        # ================================
        registrar_evento(
            rectificativa_id,
            "FACTURA",
            "RECTIFICATIVA_PARCIAL_CREADA",
            motivo,
        )

        return rectificativa_id

    except Exception:

        conn.rollback()

        logging.exception(
            f"Error al crear factura rectificativa de {factura_original_id}"
        )

        raise

    finally:
        conn.close()


# ==========================================================
# OBTENER FACTURAS
# ==========================================================
def obtener_facturas(
    numero=None,
    cliente=None,
    cliente_id=None,
    fecha_desde=None,
    fecha_hasta=None,
    estado=None,
    estado_cobro=None,
    limit=10,
    offset=0,
):
    conn = get_connection()
    cursor = conn.cursor()

    sql = """
        SELECT
            d.id,
            d.numero_legal,
            d.fecha,
            d.fecha_vencimiento,
            c.nombre,
            d.total,
            CASE
                WHEN d.factura_rectificada_id IS NOT NULL THEN 'RECTIFICATIVA'
                ELSE d.estado
            END AS estado_visual,
            d.factura_rectificada_id
        FROM documentos d
        JOIN clientes c ON c.id = d.cliente_id
        WHERE d.tipo = 'FACTURA'
    """

    params = []

    # =========================
    # FILTRO Nº FACTURA
    # =========================
    if numero:
        sql += " AND d.numero_legal LIKE ?"
        params.append(f"%{numero}%")

    # =========================
    # FILTRO CLIENTE
    # =========================
    if cliente:
        sql += " AND c.nombre LIKE ?"
        params.append(f"%{cliente}%")

    # =========================
    # FILTRO ID CLIENTE
    # =========================
    if cliente_id and str(cliente_id).isdigit():
        sql += " AND d.cliente_id = ?"
        params.append(int(cliente_id))

    # =========================
    # FILTRO FECHAS
    # =========================
    if fecha_desde:
        sql += " AND d.fecha >= ?"
        params.append(fecha_desde)

    if fecha_hasta:
        sql += " AND d.fecha <= ?"
        params.append(fecha_hasta)

    # =========================
    # FILTRO ESTADO
    # =========================
    if estado:
        if estado == "RECTIFICATIVA":
            sql += " AND d.factura_rectificada_id IS NOT NULL"
        else:
            sql += " AND d.factura_rectificada_id IS NULL AND d.estado = ?"
            params.append(estado)

    # =========================
    # FILTRO ESTADO COBRO
    # =========================
    if estado_cobro:
        sql += " AND d.estado_cobro = ?"
        params.append(estado_cobro)

    # =========================
    # ORDEN + PAGINACIÓN
    # =========================
    sql += " ORDER BY d.fecha DESC, d.id DESC"
    sql += " LIMIT ? OFFSET ?"

    params.append(limit)
    params.append(offset)

    try:
        cursor.execute(sql, params)
        return cursor.fetchall()

    except Exception:
        logging.exception("Error al obtener facturas")
        return []

    finally:
        conn.close()


# ==========================================================
# LÍNEAS DE FACTURA
# ==========================================================
def obtener_lineas_factura(factura_id):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            SELECT producto_id, descripcion, cantidad, precio, iva, total
            FROM documento_lineas
            WHERE documento_id = ?
            """,
            (factura_id,),
        )

        return cursor.fetchall()

    except Exception:

        logging.exception(f"Error al obtener líneas de factura ID={factura_id}")

        return []

    finally:

        conn.close()


# ==========================================================
# ACTUALIZAR ESTADO AUTOMÁTICO
# ==========================================================
def actualizar_estado_factura(factura_id):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT fecha_vencimiento, fecha_pago
            FROM documentos
            WHERE id = ? AND tipo = 'FACTURA'
            """,
            (factura_id,),
        )

        fila = cursor.fetchone()
        if not fila:
            return

        fecha_venc, fecha_pago = fila
        hoy = date.today().isoformat()

        if fecha_pago:
            estado = "PAGADA"
        elif fecha_venc and hoy > fecha_venc:
            estado = "VENCIDA"
        else:
            estado = "PENDIENTE"

        cursor.execute(
            "UPDATE documentos SET estado = ? WHERE id = ?",
            (estado, factura_id),
        )

        conn.commit()

    except Exception:
        conn.rollback()
        logging.exception(f"Error al actualizar estado factura ID={factura_id}")
    finally:
        conn.close()


# ==========================================================
# MARCAR FACTURA COMO PAGADA
# ==========================================================
def marcar_factura_pagada(factura_id, forma_pago="CONTADO", fecha_pago=None):

    hoy = date.today().isoformat()

    if not fecha_pago:
        fecha_pago = hoy

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            UPDATE documentos
            SET fecha_pago = ?,
                forma_pago = ?,
                estado = 'PAGADA',
                estado_cobro = 'COBRADO'
            WHERE id = ? AND tipo = 'FACTURA'
            """,
            (fecha_pago, forma_pago, factura_id),
        )

        conn.commit()

        registrar_evento(
            factura_id,
            "FACTURA",
            "PAGADA",
            f"Forma: {forma_pago} | Fecha pago: {fecha_pago}",
        )

    except Exception:
        conn.rollback()
        logging.exception(f"Error al marcar factura como pagada ID={factura_id}")
        raise
    finally:
        conn.close()


# ==========================================================
# COMPROBAR BLOQUEO
# ==========================================================
def factura_bloqueada(documento_id):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT bloqueada
            FROM documentos
            WHERE id = ? AND tipo = 'FACTURA'
            """,
            (documento_id,),
        )
        row = cursor.fetchone()

        if not row:
            return True

        return bool(row[0])

    finally:
        conn.close()


def obtener_factura_por_id(factura_id):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT
                d.numero_legal,
                d.fecha,
                d.fecha_vencimiento,
                d.estado,
                d.cliente_id,
                c.nombre,
                d.total,
                d.fecha_pago
            FROM documentos d
            JOIN clientes c ON c.id = d.cliente_id
            WHERE d.id = ?
            """,
            (factura_id,),
        )

        return cursor.fetchone()

    except Exception:
        logging.exception("Error al obtener factura")
        return None

    finally:
        conn.close()

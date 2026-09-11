import logging
from datetime import date
from app.database.db import get_connection


# ==========================================================
# CREAR FACTURA DE COMPRA
# ==========================================================
def crear_factura_compra(
    proveedor_id,
    numero_factura,
    fecha,
    fecha_vencimiento,
    forma_pago=None,
):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO documentos_compras (
                proveedor_id,
                numero_factura,
                fecha,
                fecha_vencimiento,
                total,
                estado_pago,
                forma_pago,
                creado_en
            )
            VALUES (?, ?, ?, ?, 0, 'PENDIENTE', ?, ?)
            """,
            (
                proveedor_id,
                numero_factura,
                fecha,
                fecha_vencimiento,
                forma_pago,
                date.today().isoformat(),
            ),
        )

        factura_id = cursor.lastrowid
        conn.commit()

        logging.info(
            f"Factura de compra creada ID={factura_id} | Proveedor={proveedor_id} | Nº={numero_factura}"
        )

        return factura_id

    except Exception:
        conn.rollback()
        logging.exception("Error al crear factura de compra")
        raise

    finally:
        conn.close()


# ==========================================================
# OBTENER FACTURA DE COMPRA POR ID
# ==========================================================
def obtener_factura_compra_por_id(factura_id):

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT
                dc.id,
                dc.numero_factura,
                dc.fecha,
                dc.fecha_vencimiento,
                dc.total,
                dc.estado_pago,
                dc.forma_pago,
                p.id,
                p.nombre
            FROM documentos_compras dc
            JOIN proveedores p ON p.id = dc.proveedor_id
            WHERE dc.id = ?
            """,
            (factura_id,),
        )

        return cursor.fetchone()

    except Exception:
        logging.exception(f"Error al obtener factura de compra ID={factura_id}")
        return None

    finally:
        conn.close()


# ==========================================================
# OBTENER FACTURAS DE COMPRA (LISTADO)
# ==========================================================
def obtener_facturas_compras(
    proveedor=None,
    numero=None,
    estado=None,
    fecha_desde=None,
    fecha_hasta=None,
    limit=None,
    offset=0,
):

    conn = get_connection()
    cursor = conn.cursor()

    sql = """
        SELECT
            dc.id,
            dc.numero_factura,
            dc.fecha,
            dc.fecha_vencimiento,
            p.nombre,
            dc.total,
            dc.estado_pago
        FROM documentos_compras dc
        JOIN proveedores p ON p.id = dc.proveedor_id
        WHERE 1=1
    """

    params = []

    if proveedor:
        sql += " AND p.nombre LIKE ?"
        params.append(f"%{proveedor}%")

    if numero:
        sql += " AND dc.numero_factura LIKE ?"
        params.append(f"%{numero}%")

    if estado:
        sql += " AND dc.estado_pago = ?"
        params.append(estado)

    if fecha_desde:
        sql += " AND dc.fecha >= ?"
        params.append(fecha_desde)

    if fecha_hasta:
        sql += " AND dc.fecha <= ?"
        params.append(fecha_hasta)

    sql += " ORDER BY dc.fecha DESC, dc.id DESC"

    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.append(limit)
        params.append(offset)

    try:
        cursor.execute(sql, params)
        filas = cursor.fetchall()

        logging.info("Facturas de compra obtenidas correctamente")

        return filas

    except Exception:
        logging.exception("Error al obtener facturas de compra")
        return []

    finally:
        conn.close()


# ==========================================================
# OBTENER LINEAS DE FACTURA DE COMPRA
# ==========================================================
def obtener_lineas_factura_compra(factura_id):

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT
                id,
                descripcion,
                cantidad,
                precio,
                iva,
                total
            FROM documento_compras_lineas
            WHERE documento_compra_id = ?
            """,
            (factura_id,),
        )

        return cursor.fetchall()

    except Exception:
        logging.exception(
            f"Error al obtener líneas de factura de compra ID={factura_id}"
        )

        return []

    finally:
        conn.close()


# ==========================================================
# AÑADIR LINEA A FACTURA DE COMPRA
# ==========================================================
def añadir_linea_factura_compra(
    factura_id,
    descripcion,
    cantidad,
    precio,
    iva,
):

    conn = get_connection()
    cursor = conn.cursor()

    total = round(cantidad * precio * (1 + iva / 100), 2)

    try:
        cursor.execute(
            """
            INSERT INTO documento_compras_lineas (
                documento_compra_id,
                descripcion,
                cantidad,
                precio,
                iva,
                total
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (factura_id, descripcion, cantidad, precio, iva, total),
        )

        # recalcular total factura
        cursor.execute(
            """
            UPDATE documentos_compras
            SET total = (
                SELECT IFNULL(SUM(total),0)
                FROM documento_compras_lineas
                WHERE documento_compra_id = ?
            )
            WHERE id = ?
            """,
            (factura_id, factura_id),
        )

        conn.commit()

        logging.info(
            f"Linea añadida factura compra ID={factura_id} | {descripcion} | total={total}"
        )

    except Exception:
        conn.rollback()
        logging.exception("Error al añadir linea factura compra")
        raise

    finally:
        conn.close()


# ==========================================================
# BORRAR LINEA FACTURA COMPRA
# ==========================================================
def borrar_linea_factura_compra(linea_id, factura_id):

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            DELETE FROM documento_compras_lineas
            WHERE id = ?
            """,
            (linea_id,),
        )

        cursor.execute(
            """
            UPDATE documentos_compras
            SET total = (
                SELECT IFNULL(SUM(total),0)
                FROM documento_compras_lineas
                WHERE documento_compra_id = ?
            )
            WHERE id = ?
            """,
            (factura_id, factura_id),
        )

        conn.commit()

        logging.info(f"Linea eliminada factura compra ID={factura_id}")

    except Exception:
        conn.rollback()
        logging.exception("Error al borrar linea factura compra")
        raise

    finally:
        conn.close()


# ==========================================================
# BORRAR FACTURA DE COMPRA
# ==========================================================
def borrar_factura_compra(factura_id):

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "DELETE FROM documento_compras_lineas WHERE documento_compra_id = ?",
            (factura_id,),
        )

        cursor.execute(
            "DELETE FROM documentos_compras WHERE id = ?",
            (factura_id,),
        )

        conn.commit()

        logging.info(f"Factura de compra eliminada ID={factura_id}")

    except Exception:
        conn.rollback()
        logging.exception("Error al borrar factura compra")
        raise

    finally:
        conn.close()


# ==========================================================
# MARCAR FACTURA COMO PAGADA
# ==========================================================
def marcar_factura_compra_pagada(factura_id):

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            UPDATE documentos_compras
            SET estado_pago = 'PAGADA',
                fecha_pago = ?
            WHERE id = ?
            """,
            (date.today().isoformat(), factura_id),
        )

        conn.commit()

        logging.info(f"Factura de compra marcada como PAGADA ID={factura_id}")

    except Exception:
        conn.rollback()
        logging.exception("Error al marcar factura compra pagada")
        raise

    finally:
        conn.close()

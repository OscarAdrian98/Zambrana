import logging
from datetime import datetime
from app.database.db import get_connection


# ==================================================
# OBTENER PRODUCTOS (CON FILTROS) → SOLO ACTIVOS
# ==================================================
def obtener_productos(
    nombre=None,
    referencia=None,
    precio_min=None,
    precio_max=None,
    iva=None,
    limit=None,
    offset=0,
):
    conn = get_connection()
    cursor = conn.cursor()

    sql = """
        SELECT id, referencia, ean, nombre, precio, iva, stock, control_stock
        FROM productos
        WHERE activo = 1
    """

    params = []

    if nombre:
        sql += " AND nombre LIKE ?"
        params.append(f"%{nombre}%")

    if referencia:
        sql += " AND referencia LIKE ?"
        params.append(f"%{referencia}%")

    if precio_min is not None:
        sql += " AND precio >= ?"
        params.append(precio_min)

    if precio_max is not None:
        sql += " AND precio <= ?"
        params.append(precio_max)

    if iva is not None:
        sql += " AND iva = ?"
        params.append(iva)

    sql += " ORDER BY nombre, id"

    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.append(limit)
        params.append(offset)

    try:
        cursor.execute(sql, params)
        return cursor.fetchall()

    except Exception:
        logging.exception("Error al obtener productos")
        return []

    finally:
        conn.close()


# ==================================================
# OBTENER PRODUCTO POR ID
# ==================================================
def obtener_producto_por_id(producto_id):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT id, referencia, ean, nombre, precio, iva, stock, control_stock
            FROM productos
            WHERE id = ? AND activo = 1
            """,
            (producto_id,),
        )

        return cursor.fetchone()

    finally:
        conn.close()


# ==================================================
# OBTENER PRODUCTO POR REFERENCIA O EAN
# (MUY IMPORTANTE PARA IMPORTACIONES)
# ==================================================
def obtener_producto_por_ref_o_ean(referencia=None, ean=None):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        if referencia:
            cursor.execute(
                """
                SELECT id, referencia, ean, nombre, precio, iva, stock, control_stock
                FROM productos
                WHERE referencia = ? AND activo = 1
                """,
                (referencia,),
            )

            row = cursor.fetchone()
            if row:
                return row

        if ean:
            cursor.execute(
                """
                SELECT id, referencia, ean, nombre, precio, iva, stock, control_stock
                FROM productos
                WHERE ean = ? AND activo = 1
                """,
                (ean,),
            )

            return cursor.fetchone()

        return None

    finally:
        conn.close()


# ==================================================
# CREAR PRODUCTO
# ==================================================
def crear_producto(
    nombre,
    precio,
    iva,
    referencia=None,
    ean=None,
    stock_inicial=0,
    control_stock=1,
):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO productos
            (referencia, ean, nombre, precio, iva, stock, control_stock, activo)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (referencia, ean, nombre, precio, iva, stock_inicial, control_stock),
        )

        producto_id = cursor.lastrowid

        # registrar stock inicial
        if control_stock == 1 and stock_inicial > 0:

            cursor.execute(
                """
                INSERT INTO movimientos_stock
                (producto_id, tipo, cantidad, fecha, detalle)
                VALUES (?, 'ENTRADA', ?, ?, ?)
                """,
                (
                    producto_id,
                    stock_inicial,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Stock inicial",
                ),
            )

        conn.commit()

        logging.info(
            f"Producto creado ID={producto_id} | {nombre} | Stock={stock_inicial}"
        )

        return producto_id

    except Exception:
        conn.rollback()
        logging.exception("Error al crear producto")
        raise

    finally:
        conn.close()


# ==================================================
# ACTUALIZAR PRODUCTO
# ==================================================
def actualizar_producto(
    producto_id,
    nombre,
    precio,
    iva,
    referencia,
    ean,
    control_stock,
):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            UPDATE productos
            SET referencia = ?,
                ean = ?,
                nombre = ?,
                precio = ?,
                iva = ?,
                control_stock = ?
            WHERE id = ? AND activo = 1
            """,
            (referencia, ean, nombre, precio, iva, control_stock, producto_id),
        )

        conn.commit()

        logging.info(f"Producto actualizado ID={producto_id}")

        return True

    except Exception:
        conn.rollback()
        logging.exception(f"Error al actualizar producto ID={producto_id}")
        raise

    finally:
        conn.close()


# ==================================================
# AJUSTAR STOCK (FUNCIÓN CENTRAL ERP)
# ==================================================
def ajustar_stock(
    producto_id,
    cantidad,
    tipo="AJUSTE",
    detalle=None,
    cursor_externo=None,
):

    conn = None

    try:

        if cursor_externo:
            cursor = cursor_externo
        else:
            conn = get_connection()
            cursor = conn.cursor()

        cursor.execute(
            """
            SELECT stock, control_stock
            FROM productos
            WHERE id = ? AND activo = 1
            """,
            (producto_id,),
        )

        row = cursor.fetchone()

        if not row:
            raise Exception("Producto no encontrado")

        stock_actual, control_stock = row

        if control_stock != 1:
            logging.info(f"Producto {producto_id} sin control de stock")
            return

        nuevo_stock = stock_actual + cantidad

        if nuevo_stock < 0:
            raise Exception(
                f"Stock insuficiente. Actual={stock_actual} | Intento={cantidad}"
            )

        cursor.execute(
            """
            UPDATE productos
            SET stock = ?
            WHERE id = ?
            """,
            (nuevo_stock, producto_id),
        )

        cursor.execute(
            """
            INSERT INTO movimientos_stock
            (producto_id, tipo, cantidad, fecha, detalle)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                producto_id,
                tipo,
                cantidad,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                detalle,
            ),
        )

        if conn:
            conn.commit()

        logging.info(
            f"Stock actualizado producto={producto_id} | {stock_actual} → {nuevo_stock}"
        )

    except Exception:

        if conn:
            conn.rollback()

        logging.exception("Error al ajustar stock")
        raise

    finally:

        if conn:
            conn.close()


# ==================================================
# OBTENER STOCK DE PRODUCTO
# ==================================================
def obtener_stock_producto(producto_id):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            SELECT stock
            FROM productos
            WHERE id = ? AND activo = 1
            """,
            (producto_id,),
        )

        row = cursor.fetchone()

        if not row:
            return 0

        return row[0]

    finally:
        conn.close()


# ==================================================
# HISTORIAL DE MOVIMIENTOS DE STOCK
# ==================================================
def obtener_movimientos_stock(producto_id):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            SELECT tipo, cantidad, fecha, detalle
            FROM movimientos_stock
            WHERE producto_id = ?
            ORDER BY fecha DESC
            """,
            (producto_id,),
        )

        return cursor.fetchall()

    except Exception:
        logging.exception("Error al obtener movimientos de stock")
        return []

    finally:
        conn.close()


# ==================================================
# BORRADO LÓGICO PRODUCTO
# ==================================================
def borrar_producto(producto_id):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            UPDATE productos
            SET activo = 0
            WHERE id = ?
            """,
            (producto_id,),
        )

        conn.commit()

        logging.info(f"Producto desactivado ID={producto_id}")

        return True

    except Exception:

        conn.rollback()
        logging.exception(f"Error al desactivar producto ID={producto_id}")

        return False

    finally:
        conn.close()

import logging
from datetime import date
from app.database.db import get_connection
from app.utils.validators import validar_fecha


# ==================================================
# GENERAR NÚMERO DE ALBARÁN
# A-2026-000001
# ==================================================
def generar_numero_albaran():
    año = date.today().year
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT numero
            FROM documentos
            WHERE tipo = 'ALBARAN'
              AND numero LIKE ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (f"A-{año}-%",),
        )

        ultimo = cursor.fetchone()

        if not ultimo:
            contador = 1
        else:
            try:
                contador = int(ultimo[0].split("-")[-1]) + 1
            except Exception:
                contador = 1

        numero = f"A-{año}-{contador:06d}"

        logging.info(f"Número de albarán generado: {numero}")
        return numero

    except Exception:
        logging.exception("Error al generar número de albarán")
        raise
    finally:
        conn.close()


# ==================================================
# CREAR ALBARÁN
# ==================================================
def crear_albaran(cliente_id, fecha_str):

    if not cliente_id:
        raise Exception("Cliente inválido.")

    # limpiar
    fecha_str = (fecha_str or "").strip()

    # si no hay fecha usar hoy
    if not fecha_str:
        fecha = date.today().isoformat()

    else:

        # aceptar dd/mm/yyyy
        try:
            fecha = validar_fecha(fecha_str)

        except Exception:

            # aceptar yyyy-mm-dd
            try:
                from datetime import datetime

                fecha = datetime.strptime(fecha_str, "%Y-%m-%d").strftime("%Y-%m-%d")

            except Exception:
                raise Exception("La fecha debe tener formato dd/mm/yyyy.")

    conn = get_connection()
    cursor = conn.cursor()

    numero = generar_numero_albaran()

    try:

        cursor.execute(
            """
            INSERT INTO documentos
            (tipo, numero, fecha, cliente_id, total, creado_en)
            VALUES ('ALBARAN', ?, ?, ?, 0, ?)
            """,
            (
                numero,
                fecha,
                cliente_id,
                fecha,
            ),
        )

        albaran_id = cursor.lastrowid

        conn.commit()

        logging.info(
            f"Albarán creado ID={albaran_id} | Cliente ID={cliente_id} | Fecha={fecha}"
        )

        return albaran_id

    except Exception:

        conn.rollback()
        logging.exception("Error al crear albarán")
        raise

    finally:

        conn.close()


# ==================================================
# COMPROBAR SI UN ALBARÁN YA ESTÁ FACTURADO
# ==================================================
def albaran_facturado(albaran_id):

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT bloqueada
            FROM documentos
            WHERE id = ? AND tipo = 'ALBARAN'
            """,
            (albaran_id,),
        )

        row = cursor.fetchone()

        return bool(row and row[0])

    except Exception:
        logging.exception(f"Error comprobando estado del albarán ID={albaran_id}")
        return False
    finally:
        conn.close()


# ==================================================
# AÑADIR LÍNEA A ALBARÁN
# ==================================================
def añadir_linea(albaran_id, descripcion, cantidad, precio, iva, producto_id=None):

    if albaran_facturado(albaran_id):
        raise Exception("El albarán ya está facturado y no se puede modificar.")

    if cantidad <= 0:
        raise Exception("La cantidad debe ser mayor que 0.")

    if precio < 0:
        raise Exception("El precio no puede ser negativo.")

    total = cantidad * precio * (1 + iva / 100)

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO documento_lineas
            (documento_id, producto_id, descripcion, cantidad, precio, iva, total)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                albaran_id,
                producto_id,
                descripcion,
                cantidad,
                precio,
                iva,
                total,
            ),
        )

        cursor.execute(
            """
            UPDATE documentos
            SET total = total + ?
            WHERE id = ?
            """,
            (total, albaran_id),
        )

        conn.commit()

        logging.info(
            f"Línea añadida al albarán ID={albaran_id} | {descripcion} | Total={total:.2f}"
        )

    except Exception:
        conn.rollback()
        logging.exception(f"Error al añadir línea al albarán ID={albaran_id}")
        raise
    finally:
        conn.close()


# ==================================================
# OBTENER ALBARANES (CON FILTROS)
# ==================================================
def obtener_albaranes(
    numero=None,
    cliente=None,
    cliente_id=None,
    fecha_desde=None,
    fecha_hasta=None,
    limit=None,
    offset=0,
):

    conn = get_connection()
    cursor = conn.cursor()

    sql = """
        SELECT d.id, d.numero, d.fecha, c.nombre, d.total
        FROM documentos d
        JOIN clientes c ON c.id = d.cliente_id
        WHERE d.tipo = 'ALBARAN'
    """

    params = []

    if numero:
        sql += " AND d.numero LIKE ?"
        params.append(f"%{numero}%")

    if cliente:
        sql += " AND c.nombre LIKE ?"
        params.append(f"%{cliente}%")

    if cliente_id:
        sql += " AND d.cliente_id = ?"
        params.append(cliente_id)

    if fecha_desde:
        sql += " AND d.fecha >= ?"
        params.append(fecha_desde)

    if fecha_hasta:
        sql += " AND d.fecha <= ?"
        params.append(fecha_hasta)

    sql += " ORDER BY d.fecha DESC, d.id DESC"

    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.append(limit)
        params.append(offset)

    try:

        cursor.execute(sql, params)
        albaranes = cursor.fetchall()

        logging.info("Albaranes obtenidos correctamente")

        return albaranes

    except Exception:
        logging.exception("Error al obtener albaranes")
        return []

    finally:
        conn.close()


# ==================================================
# LÍNEAS DEL ALBARÁN
# ==================================================
def obtener_lineas_albaran(albaran_id):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            SELECT id, producto_id, descripcion, cantidad, precio, iva, total
            FROM documento_lineas
            WHERE documento_id = ?
            ORDER BY id ASC
            """,
            (albaran_id,),
        )

        lineas = cursor.fetchall()

        logging.info(f"Líneas obtenidas para albarán ID={albaran_id}")

        return lineas

    except Exception:
        logging.exception(f"Error al obtener líneas del albarán ID={albaran_id}")
        return []
    finally:
        conn.close()


# ==================================================
# BORRAR LÍNEA DEL ALBARÁN
# ==================================================
def borrar_linea(linea_id):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            SELECT documento_id, total
            FROM documento_lineas
            WHERE id = ?
            """,
            (linea_id,),
        )

        row = cursor.fetchone()

        if not row:
            return False

        documento_id, total_linea = row

        if albaran_facturado(documento_id):
            raise Exception("El albarán ya está facturado y no se puede modificar.")

        cursor.execute(
            "DELETE FROM documento_lineas WHERE id = ?",
            (linea_id,),
        )

        cursor.execute(
            """
            UPDATE documentos
            SET total = total - ?
            WHERE id = ?
            """,
            (total_linea, documento_id),
        )

        conn.commit()

        logging.info(f"Línea borrada ID={linea_id} | Albarán ID={documento_id}")

        return True

    except Exception:
        conn.rollback()
        logging.exception(f"Error al borrar línea ID={linea_id}")
        return False
    finally:
        conn.close()


# ==================================================
# BORRAR ALBARÁN ENTERO
# ==================================================
def borrar_albaran(albaran_id):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            SELECT bloqueada
            FROM documentos
            WHERE id = ? AND tipo = 'ALBARAN'
            """,
            (albaran_id,),
        )

        row = cursor.fetchone()

        if not row:
            return False

        if row[0]:
            logging.warning(f"Intento de borrar albarán bloqueado ID={albaran_id}")
            return False

        cursor.execute(
            """
            DELETE FROM documento_lineas
            WHERE documento_id = ?
            """,
            (albaran_id,),
        )

        cursor.execute(
            """
            DELETE FROM documentos
            WHERE id = ? AND tipo = 'ALBARAN'
            """,
            (albaran_id,),
        )

        conn.commit()

        logging.info(f"Albarán eliminado ID={albaran_id}")

        return True

    except Exception:
        conn.rollback()
        logging.exception(f"Error al borrar albarán ID={albaran_id}")
        return False
    finally:
        conn.close()


# ==================================================
# ACTUALIZAR LINEA
# ==================================================
def actualizar_linea(linea_id, descripcion, cantidad, precio, iva):

    if cantidad <= 0:
        raise Exception("La cantidad debe ser mayor que 0.")

    if precio < 0:
        raise Exception("El precio no puede ser negativo.")

    total = cantidad * precio * (1 + iva / 100)

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            SELECT documento_id, total
            FROM documento_lineas
            WHERE id = ?
            """,
            (linea_id,),
        )

        row = cursor.fetchone()

        if not row:
            raise Exception("Línea no encontrada")

        documento_id, total_anterior = row

        if albaran_facturado(documento_id):
            raise Exception("El albarán está facturado y no se puede modificar.")

        cursor.execute(
            """
            UPDATE documento_lineas
            SET descripcion = ?, cantidad = ?, precio = ?, iva = ?, total = ?
            WHERE id = ?
            """,
            (
                descripcion,
                cantidad,
                precio,
                iva,
                total,
                linea_id,
            ),
        )

        diferencia = total - total_anterior

        cursor.execute(
            """
            UPDATE documentos
            SET total = total + ?
            WHERE id = ?
            """,
            (diferencia, documento_id),
        )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

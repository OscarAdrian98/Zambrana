from datetime import date
from app.database.db import get_connection
import logging


# ==========================================================
# OBTENER FACTURAS DOMICILIADAS
# ==========================================================
def obtener_domiciliaciones(
    cliente=None,
    estado_cobro=None,
    vencidas=False,
):

    logging.info(
        f"[DOMICILIACIONES] Buscar cliente={cliente} estado={estado_cobro} vencidas={vencidas}"
    )

    conn = None

    try:

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
                d.estado_cobro,
                d.iban,
                d.tipo_vencimiento
            FROM documentos d
            JOIN clientes c ON c.id = d.cliente_id
            WHERE d.tipo = 'FACTURA'
              AND d.forma_pago = 'DOMICILIACION'
        """

        params = []

        # ==========================
        # FILTRO CLIENTE
        # ==========================
        if cliente:
            sql += " AND c.nombre LIKE ?"
            params.append(f"%{cliente}%")

        # ==========================
        # FILTRO ESTADO / VENCIDAS
        # ==========================
        if vencidas:

            sql += """
                AND d.fecha_vencimiento < ?
                AND d.estado_cobro = 'PENDIENTE'
            """

            params.append(date.today().isoformat())

        elif estado_cobro:

            sql += " AND d.estado_cobro = ?"
            params.append(estado_cobro)

        # ==========================
        # ORDEN
        # ==========================
        sql += " ORDER BY d.fecha_vencimiento ASC, d.fecha ASC"

        cursor.execute(sql, params)

        filas = cursor.fetchall()

        logging.info(f"[DOMICILIACIONES] {len(filas)} domiciliaciones encontradas")

        return filas

    except Exception:

        logging.exception("[DOMICILIACIONES] Error al obtener domiciliaciones")

        return []

    finally:

        if conn:
            conn.close()


# ==========================================================
# MARCAR COBRO DOMICILIADO
# ==========================================================
def marcar_cobro_domiciliacion(factura_id):

    logging.info(f"[DOMICILIACIONES] Marcar cobro domiciliado factura_id={factura_id}")

    conn = None

    try:

        conn = get_connection()
        cursor = conn.cursor()

        hoy = date.today().isoformat()

        cursor.execute(
            """
            UPDATE documentos
            SET
                estado_cobro = 'COBRADO',
                estado = 'PAGADA',
                fecha_pago = ?
            WHERE id = ?
              AND tipo = 'FACTURA'
              AND forma_pago = 'DOMICILIACION'
            """,
            (hoy, factura_id),
        )

        # ==========================
        # VALIDAR UPDATE
        # ==========================
        if cursor.rowcount == 0:
            raise ValueError("No se encontró la factura domiciliada o no es válida.")

        conn.commit()

        logging.info(
            f"[DOMICILIACIONES] Cobro domiciliado marcado correctamente factura_id={factura_id}"
        )

    except Exception:

        logging.exception(
            f"[DOMICILIACIONES] Error al marcar cobro domiciliado factura_id={factura_id}"
        )

        if conn:
            conn.rollback()

        raise

    finally:

        if conn:
            conn.close()


# ==========================================================
# MARCAR DEVOLUCIÓN DOMICILIACIÓN
# ==========================================================
def marcar_devolucion_domiciliacion(factura_id):

    logging.info(
        f"[DOMICILIACIONES] Marcar devolución domiciliación factura_id={factura_id}"
    )

    conn = None

    try:

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE documentos
            SET estado_cobro = 'DEVUELTO'
            WHERE id = ?
              AND tipo = 'FACTURA'
              AND forma_pago = 'DOMICILIACION'
            """,
            (factura_id,),
        )

        # ==========================
        # VALIDAR UPDATE
        # ==========================
        if cursor.rowcount == 0:
            raise ValueError("No se encontró la factura domiciliada o no es válida.")

        conn.commit()

        logging.info(
            f"[DOMICILIACIONES] Devolución domiciliación marcada factura_id={factura_id}"
        )

    except Exception:

        logging.exception(
            f"[DOMICILIACIONES] Error al marcar devolución domiciliación factura_id={factura_id}"
        )

        if conn:
            conn.rollback()

        raise

    finally:

        if conn:
            conn.close()

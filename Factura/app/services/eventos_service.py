from datetime import datetime
from app.database.db import get_connection
import logging


# ==========================================================
# REGISTRAR EVENTO DE DOCUMENTO
# ==========================================================
def registrar_evento(
    documento_id,
    tipo_documento,
    evento,
    detalle=None,
):
    """
    Registra un evento en la tabla eventos_documentos.

    Parámetros:
    - documento_id: ID del documento afectado
    - tipo_documento: 'FACTURA' o 'ALBARAN'
    - evento: texto corto del evento (ej: CREADA, PAGADA, RECTIFICATIVA)
    - detalle: información adicional opcional
    """

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO eventos_documentos
            (documento_id, tipo_documento, evento, fecha, detalle)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                documento_id,
                tipo_documento,
                evento,
                datetime.now().isoformat(),
                detalle,
            ),
        )

        conn.commit()

        logging.info(
            f"Evento registrado → DocID={documento_id} | "
            f"Tipo={tipo_documento} | Evento={evento}"
        )

    except Exception:
        conn.rollback()
        logging.exception(f"Error registrando evento en documento ID={documento_id}")
        raise

    finally:
        conn.close()


# ==========================================================
# OBTENER EVENTOS DE UN DOCUMENTO
# ==========================================================
def obtener_eventos_documento(documento_id):
    """
    Devuelve todos los eventos asociados a un documento,
    ordenados por fecha ascendente.
    """

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT evento, fecha, detalle
            FROM eventos_documentos
            WHERE documento_id = ?
            ORDER BY fecha ASC
            """,
            (documento_id,),
        )

        return cursor.fetchall()

    except Exception:
        logging.exception(f"Error obteniendo eventos de documento ID={documento_id}")
        return []

    finally:
        conn.close()

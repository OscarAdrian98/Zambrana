import logging
from app.database.db import get_connection
from app.services.facturas_service import generar_hash_documento


# ==========================================================
# VERIFICAR INTEGRIDAD DE TODAS LAS FACTURAS
# ==========================================================
def verificar_integridad():

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT id, hash
            FROM documentos
            WHERE tipo = 'FACTURA'
            """
        )

        documentos = cursor.fetchall()

        for doc_id, hash_guardado in documentos:

            # Si no tiene hash (facturas antiguas), saltamos
            if not hash_guardado:
                continue

            # 🔥 PASAMOS EL MISMO CURSOR
            hash_actual = generar_hash_documento(doc_id, cursor)

            if hash_actual != hash_guardado:
                logging.critical(f"ERROR DE INTEGRIDAD EN FACTURA ID={doc_id}")
                raise Exception(
                    f"ERROR DE INTEGRIDAD: Factura ID {doc_id} ha sido manipulada."
                )

        logging.info("Verificación de integridad completada correctamente.")

    finally:
        conn.close()

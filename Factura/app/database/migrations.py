# app/database/migrations.py


def migrar_documentos_vencimientos():
    from app.database.db import get_connection

    conn = get_connection()
    cursor = conn.cursor()

    # Añadir fecha_vencimiento si no existe
    try:
        cursor.execute("ALTER TABLE documentos ADD COLUMN fecha_vencimiento TEXT")
    except Exception:
        pass  # ya existe

    # Añadir fecha_pago si no existe
    try:
        cursor.execute("ALTER TABLE documentos ADD COLUMN fecha_pago TEXT")
    except Exception:
        pass  # ya existe

    # Añadir forma_pago si no existe
    try:
        cursor.execute("ALTER TABLE documentos ADD COLUMN forma_pago TEXT")
    except Exception:
        pass  # ya existe

    # ✅ NUEVO: referencia a factura original (para rectificativas)
    try:
        cursor.execute(
            "ALTER TABLE documentos ADD COLUMN factura_rectificada_id INTEGER"
        )
    except Exception:
        pass  # ya existe

    # ✅ NUEVO: motivo de la rectificación
    try:
        cursor.execute("ALTER TABLE documentos ADD COLUMN motivo_rectificacion TEXT")
    except Exception:
        pass  # ya existe

    conn.commit()
    conn.close()

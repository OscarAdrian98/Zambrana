import logging
from app.database.db import get_connection


# ==================================================
# OBTENER PROVEEDORES (CON FILTROS)
# ==================================================
def obtener_proveedores(
    nombre=None,
    cif=None,
    solo_activos=True,
    limit=None,
    offset=0,
):

    conn = get_connection()
    cursor = conn.cursor()

    sql = """
        SELECT
            id,
            nombre,
            cif,
            email,
            telefono,
            direccion,
            codigo_postal,
            poblacion,
            provincia,
            pais,
            iban
        FROM proveedores
        WHERE 1=1
    """

    params = []

    if solo_activos:
        sql += " AND activo = 1"

    if nombre:
        sql += " AND nombre LIKE ?"
        params.append(f"%{nombre}%")

    if cif:
        sql += " AND cif LIKE ?"
        params.append(f"%{cif}%")

    sql += " ORDER BY nombre ASC, id DESC"

    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.append(limit)
        params.append(offset)

    try:
        cursor.execute(sql, params)
        proveedores = cursor.fetchall()
        logging.info("Proveedores obtenidos correctamente")
        return proveedores

    except Exception:
        logging.exception("Error al obtener proveedores")
        return []

    finally:
        conn.close()


# ==================================================
# CREAR PROVEEDOR
# ==================================================
def crear_proveedor(
    nombre,
    cif,
    email,
    telefono,
    direccion,
    codigo_postal,
    poblacion,
    provincia,
    pais,
    iban,
):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO proveedores (
                nombre,
                cif,
                email,
                telefono,
                direccion,
                codigo_postal,
                poblacion,
                provincia,
                pais,
                iban,
                activo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                nombre,
                cif,
                email,
                telefono,
                direccion,
                codigo_postal,
                poblacion,
                provincia,
                pais,
                iban,
            ),
        )

        conn.commit()

        logging.info(f"Proveedor creado: {nombre} ({cif})")

    except Exception:
        conn.rollback()
        logging.exception(f"Error al crear proveedor: {nombre}")
        raise

    finally:
        conn.close()


# ==================================================
# ACTUALIZAR PROVEEDOR
# ==================================================
def actualizar_proveedor(
    proveedor_id,
    nombre,
    cif,
    email,
    telefono,
    direccion,
    codigo_postal,
    poblacion,
    provincia,
    pais,
    iban,
):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            UPDATE proveedores
            SET
                nombre = ?,
                cif = ?,
                email = ?,
                telefono = ?,
                direccion = ?,
                codigo_postal = ?,
                poblacion = ?,
                provincia = ?,
                pais = ?,
                iban = ?
            WHERE id = ?
            """,
            (
                nombre,
                cif,
                email,
                telefono,
                direccion,
                codigo_postal,
                poblacion,
                provincia,
                pais,
                iban,
                proveedor_id,
            ),
        )

        conn.commit()

        logging.info(f"Proveedor actualizado ID={proveedor_id} | {nombre} ({cif})")

    except Exception:
        conn.rollback()
        logging.exception(f"Error al actualizar proveedor ID={proveedor_id}")
        raise

    finally:
        conn.close()


# ==================================================
# DESACTIVAR PROVEEDOR (NO BORRAR)
# ==================================================
def borrar_proveedor(proveedor_id):
    """
    No borra físicamente.
    Siempre se desactiva para mantener integridad histórica.
    Devuelve True si NO tenía facturas de compra asociadas.
    """

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            "SELECT COUNT(*) FROM documentos_compras WHERE proveedor_id = ?",
            (proveedor_id,),
        )

        usados = cursor.fetchone()[0]

        cursor.execute(
            "UPDATE proveedores SET activo = 0 WHERE id = ?",
            (proveedor_id,),
        )

        conn.commit()

        if usados > 0:
            logging.warning(f"Proveedor ID={proveedor_id} desactivado (tenía facturas)")
        else:
            logging.info(f"Proveedor ID={proveedor_id} desactivado (sin facturas)")

        return usados == 0

    except Exception:
        conn.rollback()
        logging.exception(f"Error al desactivar proveedor ID={proveedor_id}")
        raise

    finally:
        conn.close()

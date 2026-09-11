import logging
from app.database.db import get_connection


# ==================================================
# OBTENER CLIENTES (CON FILTROS)
# SOLO ACTIVOS
# ==================================================
def obtener_clientes(
    nombre=None,
    email=None,
    telefono=None,
    dni=None,
    limit=None,
    offset=0,
):
    conn = get_connection()
    cursor = conn.cursor()

    sql = """
        SELECT id, nombre, dni, email, telefono,
               direccion, codigo_postal, poblacion, provincia, pais, iban
        FROM clientes
        WHERE activo = 1
    """
    params = []

    if nombre:
        sql += " AND nombre LIKE ?"
        params.append(f"%{nombre}%")

    if email:
        sql += " AND email LIKE ?"
        params.append(f"%{email}%")

    if telefono:
        sql += " AND telefono LIKE ?"
        params.append(f"%{telefono}%")

    if dni:
        sql += " AND dni LIKE ?"
        params.append(f"%{dni}%")

    sql += " ORDER BY nombre ASC, id DESC"

    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.append(limit)
        params.append(offset)

    try:
        cursor.execute(sql, params)
        clientes = cursor.fetchall()
        logging.info("Clientes obtenidos correctamente")
        return clientes
    except Exception:
        logging.exception("Error al obtener clientes")
        return []
    finally:
        conn.close()


# ==================================================
# CREAR CLIENTE (CON CONTROL DUPLICADOS)
# ==================================================
def crear_cliente(
    nombre,
    dni,
    email,
    telefono,
    direccion,
    codigo_postal=None,
    poblacion=None,
    provincia=None,
    pais=None,
    iban=None,
):

    if not nombre:
        raise ValueError("El nombre es obligatorio")

    conn = get_connection()
    cursor = conn.cursor()

    try:

        if dni:
            cursor.execute(
                "SELECT id FROM clientes WHERE dni = ? AND activo = 1",
                (dni,),
            )
            if cursor.fetchone():
                raise ValueError("Ya existe un cliente con ese DNI")

        if email:
            cursor.execute(
                """
                SELECT id FROM clientes
                WHERE nombre = ? AND email = ? AND activo = 1
                """,
                (nombre, email),
            )
            if cursor.fetchone():
                raise ValueError("Ya existe un cliente con ese nombre y email")

        cursor.execute(
            """
            INSERT INTO clientes (
                nombre, dni, email, telefono,
                direccion, codigo_postal, poblacion, provincia, pais,
                iban, activo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                nombre,
                dni,
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
        logging.info(f"Cliente creado correctamente: {nombre}")
        return True

    except Exception:
        conn.rollback()
        logging.exception("Error al crear cliente")
        raise
    finally:
        conn.close()


# ==================================================
# ACTUALIZAR CLIENTE
# ==================================================
def actualizar_cliente(
    cliente_id,
    nombre,
    dni,
    email,
    telefono,
    direccion,
    codigo_postal=None,
    poblacion=None,
    provincia=None,
    pais=None,
    iban=None,
):

    if not cliente_id:
        raise ValueError("ID de cliente inválido")

    if not nombre:
        raise ValueError("El nombre es obligatorio")

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            "SELECT id FROM clientes WHERE id = ? AND activo = 1",
            (cliente_id,),
        )

        if not cursor.fetchone():
            raise ValueError("El cliente no existe o está desactivado")

        if dni:
            cursor.execute(
                """
                SELECT id FROM clientes
                WHERE dni = ? AND id != ? AND activo = 1
                """,
                (dni, cliente_id),
            )
            if cursor.fetchone():
                raise ValueError("Otro cliente ya tiene ese DNI")

        cursor.execute(
            """
            UPDATE clientes
            SET nombre = ?,
                dni = ?,
                email = ?,
                telefono = ?,
                direccion = ?,
                codigo_postal = ?,
                poblacion = ?,
                provincia = ?,
                pais = ?,
                iban = ?
            WHERE id = ? AND activo = 1
            """,
            (
                nombre,
                dni,
                email,
                telefono,
                direccion,
                codigo_postal,
                poblacion,
                provincia,
                pais,
                iban,
                cliente_id,
            ),
        )

        conn.commit()
        logging.info(f"Cliente actualizado correctamente ID={cliente_id}")
        return True

    except Exception:
        conn.rollback()
        logging.exception(f"Error al actualizar cliente ID={cliente_id}")
        raise
    finally:
        conn.close()


# ==================================================
# DESACTIVAR CLIENTE (BORRADO LÓGICO)
# ==================================================
def borrar_cliente(cliente_id):

    if not cliente_id:
        return False

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            UPDATE clientes
            SET activo = 0
            WHERE id = ?
            """,
            (cliente_id,),
        )

        conn.commit()
        logging.info(f"Cliente desactivado ID={cliente_id}")
        return True

    except Exception:
        conn.rollback()
        logging.exception(f"Error al desactivar cliente ID={cliente_id}")
        return False

    finally:
        conn.close()


# ==================================================
# OBTENER CLIENTE POR ID
# ==================================================
def obtener_cliente_por_id(cliente_id):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            SELECT id, nombre, dni, email, telefono,
                   direccion, codigo_postal, poblacion, provincia, pais, iban
            FROM clientes
            WHERE id = ? AND activo = 1
            """,
            (cliente_id,),
        )

        cliente = cursor.fetchone()

        if not cliente:
            return None

        return {
            "id": cliente[0],
            "nombre": cliente[1],
            "dni": cliente[2],
            "email": cliente[3],
            "telefono": cliente[4],
            "direccion": cliente[5],
            "codigo_postal": cliente[6],
            "poblacion": cliente[7],
            "provincia": cliente[8],
            "pais": cliente[9],
            "iban": cliente[10],
        }

    except Exception:
        logging.exception("Error al obtener cliente por ID")
        return None

    finally:
        conn.close()

# ==================================================
# OBTENER EMAIL CLIENTE (ATÓMICO)
# ==================================================
def obtener_email_cliente(cliente_id):
    if not cliente_id:
        return None

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT email FROM clientes WHERE id = ?", (cliente_id,))
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception:
        logging.exception(f"Error al obtener email del cliente {cliente_id}")
        return None
    finally:
        conn.close()

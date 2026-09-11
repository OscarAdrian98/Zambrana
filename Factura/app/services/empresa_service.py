from app.database.db import get_connection
import logging
import base64

# ==================================================
# OFUSCACIÓN SIMPLE (NO ES CIFRADO REAL)
# ==================================================
def _ofuscar_password(pwd: str) -> str:
    if not pwd:
        return pwd
    try:
        # Rotación básica en Base64 para que no se lea a simple vista
        # Nota: Esto es ofuscación, explícitamente no es cifrado militar.
        return base64.b64encode(pwd.encode('utf-8')).decode('utf-8')
    except:
        return pwd

def _desofuscar_password(pwd_b64: str) -> str:
    if not pwd_b64:
        return pwd_b64
    try:
        return base64.b64decode(pwd_b64.encode('utf-8')).decode('utf-8')
    except:
        return pwd_b64


# ==================================================
# OBTENER DATOS DE LA EMPRESA
# ==================================================
def obtener_empresa():
    logging.info("[EMPRESA] Obtener datos de empresa")

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                nombre,
                cif,
                direccion,
                codigo_postal,
                poblacion,
                provincia,
                pais,
                email,
                telefono,
                logo,
                iban_empresa,
                creditor_id,
                bic,
                color_factura,
                smtp_server,
                smtp_port,
                smtp_user,
                smtp_password,
                smtp_security
            FROM empresa
            WHERE id = 1
            """
        )

        empresa = cursor.fetchone()

        if not empresa:
            logging.warning("[EMPRESA] Empresa no configurada (tabla vacía)")
            return None

        # Desofuscar contraseña en memoria
        empresa_lista = list(empresa)
        if len(empresa_lista) > 17 and empresa_lista[17]:
            empresa_lista[17] = _desofuscar_password(empresa_lista[17])

        logging.info("[EMPRESA] Datos de empresa cargados correctamente")
        return tuple(empresa_lista)

    except Exception:
        logging.exception("[EMPRESA] Error al obtener datos de empresa")
        return None

    finally:
        if conn:
            conn.close()


# ==================================================
# GUARDAR / ACTUALIZAR DATOS DE LA EMPRESA
# ==================================================
def guardar_empresa(
    nombre,
    cif,
    direccion,
    codigo_postal,
    poblacion,
    provincia,
    pais,
    email,
    telefono,
    logo=None,
    iban_empresa=None,
    creditor_id=None,
    bic=None,
    color_factura="#2563EB",
    smtp_server=None,
    smtp_port=None,
    smtp_user=None,
    smtp_password=None,
    smtp_security=None,
):
    logging.info("[EMPRESA] Guardar datos de empresa")

    # Ofuscar antes de guardar
    pwd_ofuscado = _ofuscar_password(smtp_password) if smtp_password else None

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO empresa
            (
                id,
                nombre,
                cif,
                direccion,
                codigo_postal,
                poblacion,
                provincia,
                pais,
                email,
                telefono,
                logo,
                iban_empresa,
                creditor_id,
                bic,
                color_factura,
                smtp_server,
                smtp_port,
                smtp_user,
                smtp_password,
                smtp_security
            )
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                nombre,
                cif,
                direccion,
                codigo_postal,
                poblacion,
                provincia,
                pais,
                email,
                telefono,
                logo,
                iban_empresa,
                creditor_id,
                bic,
                color_factura,
                smtp_server,
                smtp_port,
                smtp_user,
                pwd_ofuscado,
                smtp_security,
            ),
        )

        conn.commit()

        logging.info("[EMPRESA] Datos de empresa guardados correctamente")

    except Exception:
        logging.exception("[EMPRESA] Error al guardar datos de empresa")
        if conn:
            conn.rollback()

    finally:
        if conn:
            conn.close()

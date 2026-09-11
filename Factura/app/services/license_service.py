import os
import hmac
import json
import hashlib
from datetime import datetime
from app.database.db import get_connection
from app.utils.config import LICENSE_PATH

# Credencial externa de la instalación autorizada.



# ==========================================================
# GENERAR FIRMA (INCLUYE EXPIRACIÓN)
# ==========================================================
def generar_firma(empresa, nif, expira):
    seed = os.environ.get('FACTURA_LICENSE_SECRET', '')
    if not seed or seed == 'change_me':
        raise RuntimeError('Configure FACTURA_LICENSE_SECRET outside the repository.')
    data = f"{empresa}{nif}{expira}{seed}"
    return hashlib.sha256(data.encode()).hexdigest()


# ==========================================================
# LEER ARCHIVO LICENSE.KEY
# ==========================================================
def leer_license_key():

    if not LICENSE_PATH.exists():
        raise Exception("No se encontró archivo de licencia.")

    with open(LICENSE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ==========================================================
# VALIDAR LICENCIA
# ==========================================================
def validar_licencia():

    licencia = leer_license_key()

    empresa_lic = licencia.get("empresa")
    nif_lic = licencia.get("nif")
    firma_lic = licencia.get("firma")
    expira = licencia.get("expira")
    version = licencia.get("version", "BASIC")

    # =========================
    # VALIDACIÓN FORMATO
    # =========================
    if not empresa_lic or not nif_lic or not firma_lic or not expira:
        raise Exception("Licencia inválida (faltan datos).")

    # =========================
    # VALIDAR EXPIRACIÓN
    # =========================
    try:
        fecha_exp = datetime.strptime(expira, "%Y-%m-%d")
    except Exception:
        raise Exception("Formato de fecha de licencia inválido.")

    if datetime.now() > fecha_exp:
        raise Exception("Licencia caducada.")

    # =========================
    # OBTENER DATOS EMPRESA BD
    # =========================
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT nombre, cif FROM empresa LIMIT 1")
    row = cursor.fetchone()

    conn.close()

    if not row:
        raise Exception(
            "Debe configurar los datos de la empresa antes de usar el programa."
        )

    empresa_bd, nif_bd = row

    if not empresa_bd or not nif_bd:
        raise Exception("La empresa debe tener nombre y CIF/NIF configurados.")

    # =========================
    # VALIDAR EMPRESA
    # =========================
    if empresa_bd != empresa_lic:
        raise Exception("La licencia no corresponde a esta empresa.")

    if nif_bd != nif_lic:
        raise Exception("El NIF/CIF no coincide con la licencia.")

    # =========================
    # VALIDAR FIRMA
    # =========================
    firma_calculada = generar_firma(empresa_lic, nif_lic, expira)

    if not hmac.compare_digest(firma_calculada, str(firma_lic)):
        raise Exception("Firma de licencia inválida.")

    # =========================
    # TODO OK
    # =========================
    return {"valida": True, "version": version, "expira": expira}

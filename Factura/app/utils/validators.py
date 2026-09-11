from datetime import datetime


# =====================================================
# VALIDACIONES GENERALES
# =====================================================


def validar_no_vacio(valor: str, nombre_campo: str) -> str:
    """
    Valida que un campo no esté vacío.
    """
    if not valor or not valor.strip():
        raise ValueError(f"El campo '{nombre_campo}' no puede estar vacío.")
    return valor.strip()


def validar_float(valor: str, nombre_campo: str, permitir_cero=False) -> float:
    """
    Valida que un valor sea numérico (float).
    """
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        raise ValueError(f"El campo '{nombre_campo}' debe ser un número válido.")

    if not permitir_cero and numero <= 0:
        raise ValueError(f"El campo '{nombre_campo}' debe ser mayor que 0.")

    if permitir_cero and numero < 0:
        raise ValueError(f"El campo '{nombre_campo}' no puede ser negativo.")

    return numero


def validar_entero(valor: str, nombre_campo: str, permitir_cero=False) -> int:
    """
    Valida que un valor sea entero.
    """
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        raise ValueError(f"El campo '{nombre_campo}' debe ser un número entero válido.")

    if not permitir_cero and numero <= 0:
        raise ValueError(f"El campo '{nombre_campo}' debe ser mayor que 0.")

    if permitir_cero and numero < 0:
        raise ValueError(f"El campo '{nombre_campo}' no puede ser negativo.")

    return numero


# =====================================================
# VALIDACIONES ESPECÍFICAS
# =====================================================


def validar_iva(valor: str) -> float:
    """
    Valida que el IVA sea correcto (0 - 100).
    """
    iva = validar_float(valor, "IVA", permitir_cero=True)

    if iva < 0 or iva > 100:
        raise ValueError("El IVA debe estar entre 0 y 100.")

    return iva


def validar_fecha(fecha_str: str) -> str:
    """
    Valida fecha en formato dd/mm/yyyy y devuelve formato SQL yyyy-mm-dd.
    """
    if not fecha_str:
        return None

    try:
        return datetime.strptime(fecha_str, "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError:
        raise ValueError("La fecha debe tener formato dd/mm/yyyy.")


def validar_fecha_sql(fecha_str: str) -> str:
    """
    Valida fecha en formato yyyy-mm-dd.
    """
    if not fecha_str:
        return None

    try:
        datetime.strptime(fecha_str, "%Y-%m-%d")
        return fecha_str
    except ValueError:
        raise ValueError("La fecha debe tener formato yyyy-mm-dd.")


# =====================================================
# VALIDACIONES FINANCIERAS
# =====================================================


def validar_importe(valor: str, nombre_campo: str) -> float:
    """
    Valida importes monetarios (precio, total, etc.).
    """
    importe = validar_float(valor, nombre_campo, permitir_cero=True)

    if importe < 0:
        raise ValueError(f"El campo '{nombre_campo}' no puede ser negativo.")

    return round(importe, 2)


# =====================================================
# VALIDACIONES IBAN BÁSICA
# =====================================================


def validar_iban(iban: str) -> str:
    """
    Validación básica de IBAN (no validación matemática completa).
    """
    if not iban:
        return None

    iban = iban.replace(" ", "").upper()

    if len(iban) < 15 or len(iban) > 34:
        raise ValueError("El IBAN no tiene un formato válido.")

    if not iban[:2].isalpha() or not iban[2:].isalnum():
        raise ValueError("El IBAN no tiene un formato válido.")

    return iban

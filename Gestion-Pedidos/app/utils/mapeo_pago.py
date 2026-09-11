"""
utils/mapeo_pago.py — Mapa centralizado de modos de pago PrestaShop → Ambar.

MEJORA vs legacy: en el PHP esta lógica estaba duplicada en matches.php
y insertPedido.php con if/elseif. Aquí es una única fuente de verdad.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class InfoPago:
    codigo_ambar: str       # Código forma de pago en Ambar
    codigo_banco: str       # Código banco en Ambar
    permite_anticipo: bool  # Si este pago puede generar anticipo inmediato
    descripcion: str


# Tabla de mapeo: clave = substring a buscar (lowercase) en payment de PS
MODOS_PAGO: list[tuple[str, InfoPago]] = [
    ("redsys",    InfoPago("TC", "8",  True,  "Tarjeta crédito/débito (Redsys)")),
    ("paypal",    InfoPago("PY", "2",  True,  "PayPal")),
    ("aplazame",  InfoPago("AP", "12", True,  "Aplazame")),
    ("bizum",     InfoPago("BZ", "8",  True,  "Bizum")),
    ("sequra",    InfoPago("SQ", "17", True,  "SeQura")),
    ("reembolso", InfoPago("RE", "1",  False, "Contrareembolso")),
]

# Fallback para pagos no reconocidos (ej: transferencia, pendiente)
PAGO_DEFECTO = InfoPago("PE", "1", False, "Pendiente / Otros")


def mapear_pago(payment_prestashop: str) -> InfoPago:
    """
    Devuelve la InfoPago correspondiente al modo de pago de PrestaShop.
    La comparación es case-insensitive y por substring.
    """
    lower = payment_prestashop.lower()
    for keyword, info in MODOS_PAGO:
        if keyword in lower:
            return info
    return PAGO_DEFECTO

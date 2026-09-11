"""
utils/paises.py — Constantes y helpers de países y fiscalidad.

Centraliza lógica de IVA por país, DUA, OSS e intracomunitario.
"""

# Países PrestaShop que requieren DUA al exportar
PAISES_DUA: dict[int, str] = {
    245: "España - Islas Canarias",
    248: "España - Ceuta y Melilla",
}

# IVA aplicable por id_country de PrestaShop
IVA_POR_PAIS: dict[int, int] = {
    245: 0,   # Canarias
    248: 0,   # Ceuta y Melilla
    249: 21,  # Baleares
    6:   21,  # España peninsular
    15:  23,  # Portugal
    247: 0,   # Portugal intracomunitario (sin IVA)
}

IVA_DEFECTO = 21  # Fallback si el país no está en la tabla


def iva_para_pais(id_pais: int) -> int:
    return IVA_POR_PAIS.get(id_pais, IVA_DEFECTO)


def requiere_dua(id_pais: int) -> bool:
    return id_pais in PAISES_DUA


def es_portugal(nombre_pais: str) -> bool:
    return "portugal" in (nombre_pais or "").lower()


def es_intracomunitario(id_pais: int) -> bool:
    """Portugal sin IVA = operador intracomunitario."""
    return id_pais == 247

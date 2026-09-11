"""Resolución centralizada del país y perfil fiscal de clientes Ambar."""
from __future__ import annotations

from dataclasses import dataclass
import unicodedata


class CountryResolutionError(ValueError):
    """El país de PrestaShop no puede convertirse de forma segura a Ambar."""


@dataclass(frozen=True)
class CountryProfile:
    pais_codigo: str
    pais_nombre: str


@dataclass(frozen=True)
class FiscalProfile:
    pais_codigo: str
    pais: str
    tipo_documento: str
    iva_regimen: str
    iva_clase: str


_COUNTRY_NAMES: dict[str, str] = {
    "DE": "ALEMANIA",
    "AT": "AUSTRIA",
    "BE": "BÉLGICA",
    "DK": "DINAMARCA",
    "GB": "REINO UNIDO",
    "ES": "ESPAÑA",
    "FR": "FRANCIA",
    "IT": "ITALIA",
    "LI": "LIECHTENSTEIN",
    "LU": "LUXEMBURGO",
    "MC": "MÓNACO",
    "NL": "PAÍSES BAJOS",
    "PL": "POLONIA",
    "PT": "PORTUGAL",
    "CZ": "REPÚBLICA CHECA",
    "SM": "SAN MARINO",
    "CH": "SUIZA",
    "VA": "VATICANO",
}

_GB_ZONE_NAMES: tuple[tuple[str, str], ...] = (
    ("IRLANDA DEL NORTE", "IRLANDA DEL NORTE"),
    ("NORTHERN IRELAND", "IRLANDA DEL NORTE"),
    ("INGLATERRA", "INGLATERRA"),
    ("ENGLAND", "INGLATERRA"),
    ("ESCOCIA", "ESCOCIA"),
    ("SCOTLAND", "ESCOCIA"),
    ("GALES", "GALES"),
    ("WALES", "GALES"),
)


def resolve_ambar_country(
    iso_code: str,
    prestashop_country_name: str,
) -> CountryProfile:
    """Resuelve un ISO real de PrestaShop a los campos de país de Ambar."""
    iso = (iso_code or "").strip().upper()
    if not iso:
        raise CountryResolutionError("ISO de país ausente en la dirección seleccionada")
    if iso not in _COUNTRY_NAMES:
        raise CountryResolutionError(f"país no soportado (ISO {iso})")

    pais_nombre = _COUNTRY_NAMES[iso]
    if iso == "GB":
        nombre_comparable = _normalizar_para_resolver(prestashop_country_name)
        for alias, nombre_ambar in _GB_ZONE_NAMES:
            if alias in nombre_comparable:
                pais_nombre = nombre_ambar
                break

    return CountryProfile(pais_codigo=iso, pais_nombre=pais_nombre)


def build_ambar_customer_fiscal_profile(
    iso_code: str,
    country_name: str,
    has_vat: bool,
) -> FiscalProfile:
    """Genera todos los valores fiscales usados por preview e INSERT."""
    country = resolve_ambar_country(iso_code, country_name)
    return FiscalProfile(
        pais_codigo=country.pais_codigo,
        pais=country.pais_nombre,
        tipo_documento="O",
        iva_regimen="S" if has_vat else "N",
        iva_clase="N" if country.pais_codigo == "ES" else "I",
    )


def _normalizar_para_resolver(value: str) -> str:
    normalized = unicodedata.normalize("NFD", (value or "").strip().upper())
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")

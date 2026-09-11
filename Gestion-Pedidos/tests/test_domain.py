import pytest
from app.services.normalizacion_service import normalizar_para_comparar, normalizar_nombre_ambar
from app.services.cliente_fiscal_service import (
    resolve_ambar_country, CountryResolutionError, build_ambar_customer_fiscal_profile,
)
from config import Settings

@pytest.mark.parametrize('value,expected', [
    (None, ''), ('  catálogo\u00a0  DEMO ', 'CATALOGO DEMO'),
    ('LÍNEA\n DE\tPRUEBA', 'LINEA DE PRUEBA'),
])
def test_normalization_for_matching(value, expected):
    assert normalizar_para_comparar(value) == expected

def test_names_preserve_enye_and_bound_erp_field():
    assert normalizar_nombre_ambar('Peña', 'Álvaro') == 'PEÑA ALVARO'
    assert len(normalizar_nombre_ambar('A'*90, 'B')) == 80

@pytest.mark.parametrize('iso', ['', 'ZZ'])
def test_unknown_country_is_not_silently_accepted(iso):
    with pytest.raises(CountryResolutionError):
        resolve_ambar_country(iso, 'País de ejemplo')

def test_country_resolution_and_fiscal_mapping():
    assert resolve_ambar_country('gb', 'Northern Ireland').pais_nombre == 'IRLANDA DEL NORTE'
    result = build_ambar_customer_fiscal_profile('ES', 'España', True)
    assert (result.iva_regimen, result.iva_clase) == ('S', 'N')

def test_settings_default_to_read_only_without_credentials():
    settings = Settings(_env_file=None)
    assert settings.app_read_only
    assert settings.ps_mysql_password == ''
    assert settings.ambar_sqlserver_password == ''

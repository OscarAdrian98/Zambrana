import pytest
from app.utils.validators import validar_no_vacio, validar_iva, validar_fecha, validar_importe
from app.services.license_service import generar_firma

@pytest.mark.parametrize('value', ['', '  '])
def test_required_fields(value):
    with pytest.raises(ValueError):
        validar_no_vacio(value, 'Campo sintético')

@pytest.mark.parametrize('value', ['-1', '101'])
def test_tax_percent_bounds(value):
    with pytest.raises(ValueError):
        validar_iva(value)

def test_date_and_amount_normalization():
    assert validar_fecha('29/02/2024') == '2024-02-29'
    assert validar_importe('12.345', 'Importe sintético') == 12.35

def test_impossible_date():
    with pytest.raises(ValueError):
        validar_fecha('29/02/2025')

def test_negative_amount_rejected():
    with pytest.raises(ValueError):
        validar_importe('-1', 'Importe sintético')

def test_license_seed_required(monkeypatch):
    monkeypatch.delenv('FACTURA_LICENSE_SECRET', raising=False)
    with pytest.raises(RuntimeError):
        generar_firma('Empresa de ejemplo', 'DEMO-ID', '2030-01-01')

def test_license_signature_depends_on_configured_seed(monkeypatch):
    monkeypatch.setenv('FACTURA_LICENSE_SECRET', 'test-only-seed-one')
    first = generar_firma('Empresa de ejemplo', 'DEMO-ID', '2030-01-01')
    monkeypatch.setenv('FACTURA_LICENSE_SECRET', 'test-only-seed-two')
    assert first != generar_firma('Empresa de ejemplo', 'DEMO-ID', '2030-01-01')

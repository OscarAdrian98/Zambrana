from decimal import Decimal
import pandas as pd
import pytest
from procesamiento.reglas import (
    normalizar_identificador, normalizar_ean, normalizar_stock,
    normalizar_serie_stock, calcular_disponibilidad,
)

@pytest.mark.parametrize('value,expected', [
    ('00120', '00120'), (120.0, '120'), (Decimal('120'), '120'),
    (None, None), (float('nan'), None),
])
def test_identifier_preserves_significant_zeroes(value, expected):
    assert normalizar_identificador(value) == expected

@pytest.mark.parametrize('value,expected', [('001234', '001234'), ('DEMO-X', None), ('１２３', None)])
def test_ean_accepts_only_ascii_digits(value, expected):
    assert normalizar_ean(value) == expected

@pytest.mark.parametrize('value,expected', [(None, 0), (-1, 0), ('0', 0), ('2,5', 1), ('sin stock', 0)])
def test_stock_availability(value, expected):
    assert normalizar_stock(value) == expected

def test_vectorized_stock_matches_scalar_rules():
    values = [None, 'sin stock', '0', '-3', '2,5', '1']
    assert normalizar_serie_stock(pd.Series(values)).tolist() == [normalizar_stock(v) for v in values]

@pytest.mark.parametrize('shop,supplier,expected', [(1, 0, 1), (0, 1, 1), (-1, 0, 0), ('invalid', 0, 0)])
def test_shop_or_supplier_can_supply(shop, supplier, expected):
    assert calcular_disponibilidad(shop, supplier) == expected

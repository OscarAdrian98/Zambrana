import pytest
from config.lote_validacion import _ids
from config.provider_rules import optional_provider_id

def test_scope_is_empty_until_explicitly_configured(monkeypatch):
    monkeypatch.delenv('STOCK_PROVIDER_IDS', raising=False)
    assert _ids('STOCK_PROVIDER_IDS') == ()

@pytest.mark.parametrize('value', ['1,1', '0', '-1'])
def test_invalid_scope_rejected(monkeypatch, value):
    monkeypatch.setenv('STOCK_PROVIDER_IDS', value)
    with pytest.raises(ValueError):
        _ids('STOCK_PROVIDER_IDS')

def test_special_rule_has_no_implicit_provider(monkeypatch):
    monkeypatch.delenv('STOCK_FTPS_PROVIDER_ID', raising=False)
    assert optional_provider_id('STOCK_FTPS_PROVIDER_ID') is None
    monkeypatch.setenv('STOCK_FTPS_PROVIDER_ID', '101')
    assert optional_provider_id('STOCK_FTPS_PROVIDER_ID') == 101

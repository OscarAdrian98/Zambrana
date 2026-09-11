"""Identificadores opcionales de capacidades por instalación."""
import os

def optional_provider_id(name):
    value = os.environ.get(name, '').strip()
    if not value:
        return None
    identifier = int(value)
    if identifier <= 0:
        raise ValueError(f'{name}: expected a positive identifier.')
    return identifier

OPEN_QUANTITY_PROVIDER_ID = optional_provider_id('STOCK_OPEN_QUANTITY_PROVIDER_ID')
FTPS_PROVIDER_ID = optional_provider_id('STOCK_FTPS_PROVIDER_ID')

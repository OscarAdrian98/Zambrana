"""Alcance explícito por instalación; no se distribuyen IDs empresariales."""
import os

def _ids(name):
    raw = os.environ.get(name, '')
    values = tuple(int(value.strip()) for value in raw.split(',') if value.strip())
    if any(value <= 0 for value in values) or len(set(values)) != len(values):
        raise ValueError(f'{name}: expected unique positive identifiers.')
    return values

PROVEEDORES_OPERATIVOS_VALIDACION = _ids('STOCK_PROVIDER_IDS')
PROVEEDORES_EXCLUIDOS_VALIDACION = _ids('STOCK_EXCLUDED_PROVIDER_IDS')
PROVEEDORES_GESTION_ID_SHOP = frozenset(_ids('STOCK_SHOP_MANAGEMENT_PROVIDER_IDS'))

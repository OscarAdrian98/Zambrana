"""Ejecuta una suite local con red bloqueada; no inicia servicios."""
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = {'fichaje': ROOT/'fichaje', 'pedidos': ROOT/'Gestion-Pedidos',
            'stock': ROOT/'Stock2.0'/'Stock', 'factura': ROOT/'Factura'}
if len(sys.argv) != 2 or sys.argv[1] not in PROJECTS:
    raise SystemExit('Usage: python tools/run_tests.py fichaje|pedidos|stock|factura')
project = PROJECTS[sys.argv[1]]
offline = ROOT/'tools'/'offline'
os.environ['PORTFOLIO_OFFLINE_TESTS'] = '1'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
os.environ['PYTHONPATH'] = str(offline) + os.pathsep + str(project)
os.environ.pop('APP_ENV_FILE', None)
os.environ.pop('STOCK_ENV', None)
if sys.argv[1] == 'fichaje':
    os.environ['FICHAJE_TESTING'] = '1'
runpy.run_path(str(offline/'sitecustomize.py'))
os.chdir(project)
sys.path.insert(0, str(project))
import pytest
raise SystemExit(pytest.main(['tests', '-q', '-p', 'no:cacheprovider', '--tb=short']))

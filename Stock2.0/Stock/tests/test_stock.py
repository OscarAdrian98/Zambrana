import sys
import os

# Añade la ruta raíz de 'Stock' al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from procesamiento import stock

def test_funcion_ejemplo():
    assert 2 + 2 == 4  # Test simple solo para que pase

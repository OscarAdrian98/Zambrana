"""Configuración de producción; no contiene ni carga credenciales versionadas."""
import os
from urllib.parse import quote_plus
from script_guards import flag_enabled

def required(name):
    value = os.environ.get(name, '').strip()
    if not value or value in {'change_me', 'your_api_key_here'}:
        raise RuntimeError(f'Configure {name} outside the repository.')
    return value

SQLALCHEMY_DATABASE_URI = (
    f"mysql+pymysql://{quote_plus(required('DB_USER'))}:"
    f"{quote_plus(required('DB_PASSWORD'))}@{required('DB_HOST')}:"
    f"{int(os.environ.get('DB_PORT', '3306'))}/{required('DB_NAME')}?charset=utf8mb4"
)
SQLALCHEMY_TRACK_MODIFICATIONS = False
SECRET_KEY = required('SECRET_KEY')
ALLOW_EMAILS = False
ALLOW_AUTOFICHAJE = flag_enabled('FICHAJE_ALLOW_AUTOFICHAJE', os.environ)
ALLOW_DISCORD = flag_enabled('FICHAJE_ALLOW_DISCORD', os.environ)
ALLOW_PUSH = flag_enabled('FICHAJE_ALLOW_PUSH', os.environ)

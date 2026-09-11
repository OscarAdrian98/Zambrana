"""Cifrado de credenciales de proveedores sin secretos predeterminados."""

import base64
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


ITERATIONS = 390000


def _derive_fernet_key(password: str, salt: str) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt.encode(),
        iterations=ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def _fernet_desde_entorno() -> Fernet:
    password = os.environ.get("SECRET_MASTER_PASSWORD", "")
    salt = os.environ.get("SECRET_SALT", "")
    if not password or not salt:
        raise RuntimeError(
            "Faltan SECRET_MASTER_PASSWORD o SECRET_SALT en el entorno"
        )
    return Fernet(_derive_fernet_key(password, salt))


def encrypt_password(plain_password: str) -> str | None:
    if plain_password is None:
        return None
    return _fernet_desde_entorno().encrypt(plain_password.encode()).decode()


def decrypt_password(enc_password: str) -> str | None:
    if not enc_password:
        return None
    try:
        return _fernet_desde_entorno().decrypt(enc_password.encode()).decode()
    except RuntimeError:
        raise
    except Exception:
        return None

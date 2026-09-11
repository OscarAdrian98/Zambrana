"""Validación y gestión de sesión para el acceso de empleados."""

import re
import unicodedata

from flask import session
from flask_login import login_user, logout_user

from app.services.csrf import renovar_token_csrf


LONGITUD_MINIMA_NOMBRE = 2
LONGITUD_MAXIMA_NOMBRE = 100
LONGITUD_MAXIMA_EMAIL = 100
LONGITUD_MINIMA_PASSWORD = 10
LONGITUD_MAXIMA_PASSWORD = 128

PUESTOS_PERMITIDOS = frozenset(
    {
        "Informático",
        "Mozo Almacén",
        "Administración",
        "Mostrador",
        "Taller",
        "Comercial",
    }
)

_CARACTERES_LOCALES_EMAIL = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+$"
)
_ETIQUETA_DOMINIO = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$")


class ErrorValidacionAutenticacion(ValueError):
    """Error de entrada que puede mostrarse al usuario sin revelar internals."""


def _contiene_caracteres_de_control(valor):
    return any(unicodedata.category(caracter).startswith("C") for caracter in valor)


def normalizar_email(valor):
    """Normaliza un email y aplica una validación estructural deliberadamente simple."""
    if not isinstance(valor, str):
        raise ErrorValidacionAutenticacion("Introduce un email válido.")
    if _contiene_caracteres_de_control(valor):
        raise ErrorValidacionAutenticacion("Introduce un email válido.")

    email = valor.strip()
    if not email:
        raise ErrorValidacionAutenticacion("El email es obligatorio.")
    if len(email) > LONGITUD_MAXIMA_EMAIL:
        raise ErrorValidacionAutenticacion(
            f"El email no puede superar {LONGITUD_MAXIMA_EMAIL} caracteres."
        )
    if any(caracter.isspace() for caracter in email):
        raise ErrorValidacionAutenticacion("Introduce un email válido.")
    if email.count("@") != 1:
        raise ErrorValidacionAutenticacion("Introduce un email válido.")

    parte_local, dominio = email.split("@")
    etiquetas = dominio.split(".")
    if (
        not parte_local
        or not dominio
        or "." not in dominio
        or parte_local.startswith(".")
        or parte_local.endswith(".")
        or ".." in parte_local
        or not _CARACTERES_LOCALES_EMAIL.fullmatch(parte_local)
        or any(not etiqueta for etiqueta in etiquetas)
        or any(not _ETIQUETA_DOMINIO.fullmatch(etiqueta) for etiqueta in etiquetas)
    ):
        raise ErrorValidacionAutenticacion("Introduce un email válido.")

    return email.lower()


def normalizar_nombre(valor):
    """Limpia espacios del nombre sin alterar su capitalización."""
    if not isinstance(valor, str):
        raise ErrorValidacionAutenticacion("El nombre es obligatorio.")
    if _contiene_caracteres_de_control(valor):
        raise ErrorValidacionAutenticacion(
            "El nombre no puede contener caracteres de control."
        )

    nombre = re.sub(r"\s+", " ", valor.strip())
    if len(nombre) < LONGITUD_MINIMA_NOMBRE:
        raise ErrorValidacionAutenticacion(
            f"El nombre debe tener al menos {LONGITUD_MINIMA_NOMBRE} caracteres."
        )
    if len(nombre) > LONGITUD_MAXIMA_NOMBRE:
        raise ErrorValidacionAutenticacion(
            f"El nombre no puede superar {LONGITUD_MAXIMA_NOMBRE} caracteres."
        )
    return nombre


def validar_password(password, confirmacion=None):
    """Aplica la política compartida de contraseña y, si procede, la confirmación."""
    if not isinstance(password, str) or not password:
        raise ErrorValidacionAutenticacion("La contraseña es obligatoria.")
    if len(password) < LONGITUD_MINIMA_PASSWORD:
        raise ErrorValidacionAutenticacion(
            "La contraseña debe tener al menos "
            f"{LONGITUD_MINIMA_PASSWORD} caracteres."
        )
    if len(password) > LONGITUD_MAXIMA_PASSWORD:
        raise ErrorValidacionAutenticacion(
            "La contraseña no puede superar "
            f"{LONGITUD_MAXIMA_PASSWORD} caracteres."
        )
    if not password.strip():
        raise ErrorValidacionAutenticacion(
            "La contraseña no puede estar formada sólo por espacios."
        )
    if confirmacion is None:
        raise ErrorValidacionAutenticacion("Debes confirmar la contraseña.")
    if password != confirmacion:
        raise ErrorValidacionAutenticacion("Las contraseñas no coinciden.")
    return password


def validar_puesto(valor):
    if not isinstance(valor, str):
        raise ErrorValidacionAutenticacion("Selecciona un puesto válido.")
    puesto = valor.strip()
    if puesto not in PUESTOS_PERMITIDOS:
        raise ErrorValidacionAutenticacion("Selecciona un puesto válido.")
    return puesto


def iniciar_sesion_limpia(usuario, recordar=False):
    """Elimina estado previo y crea una sesión autenticada con un CSRF nuevo."""
    session.clear()
    login_user(usuario, remember=recordar, fresh=True)
    renovar_token_csrf()


def refrescar_sesion_autenticada(usuario):
    """Limpia estado temporal sin invalidar una cookie remember ya emitida."""
    session.clear()
    login_user(usuario, fresh=True)
    renovar_token_csrf()


def cerrar_sesion_limpia():
    """Cierra la autenticación, conserva la orden de borrar remember y rota CSRF."""
    logout_user()
    accion_remember = session.get("_remember")
    session.clear()
    if accion_remember:
        session["_remember"] = accion_remember
    renovar_token_csrf()

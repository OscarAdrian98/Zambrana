"""Protección CSRF centralizada para todas las peticiones mutables."""

import hmac
import secrets

from flask import current_app, request, session


CAMPO_CSRF = "csrf_token"
CLAVE_SESION_CSRF = "_csrf_token"
METODOS_MUTABLES = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def generar_token_csrf():
    """Devuelve el token de la sesión y lo crea con entropía segura si falta."""
    token = session.get(CLAVE_SESION_CSRF)
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        session[CLAVE_SESION_CSRF] = token
    return token


def renovar_token_csrf():
    """Rota el token después de un cambio relevante de autenticación."""
    token = secrets.token_urlsafe(32)
    session[CLAVE_SESION_CSRF] = token
    return token


def _token_recibido():
    return (
        request.form.get(CAMPO_CSRF)
        or request.headers.get("X-CSRF-Token")
        or request.headers.get("X-CSRFToken")
    )


def _proteger_peticion_mutable():
    if request.method not in METODOS_MUTABLES:
        return None

    esperado = session.get(CLAVE_SESION_CSRF)
    recibido = _token_recibido()
    valido = (
        isinstance(esperado, str)
        and isinstance(recibido, str)
        and bool(esperado)
        and hmac.compare_digest(esperado, recibido)
    )
    if valido:
        return None

    current_app.logger.warning(
        "Petición mutable rechazada por validación CSRF: método=%s ruta=%s",
        request.method,
        request.path,
    )
    return "Solicitud no válida.", 400


def init_csrf(app):
    """Registra una única protección global y el helper de plantillas."""
    app.jinja_env.globals["csrf_token"] = generar_token_csrf
    app.before_request(_proteger_peticion_mutable)

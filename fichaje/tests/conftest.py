import os
import re
import sys
from html import unescape

import pytest
from flask.testing import FlaskClient
from werkzeug.security import generate_password_hash
from werkzeug.datastructures import MultiDict


# This must be set before importing app so the real configuration is never loaded.
os.environ["FICHAJE_TESTING"] = "1"

from app import app as flask_app
from app import db
from app.models import Usuario


# Abort test collection before any fixture can create tables or open a connection
# unless the isolated configuration is unquestionably active.
assert flask_app.config["TESTING"] is True
assert flask_app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:")
assert "config.config" not in sys.modules
assert "config.secret_config" not in sys.modules


def extraer_token_csrf(response):
    html = response.get_data(as_text=True)
    coincidencia = re.search(
        r'name="csrf_token"\s+value="([^"]+)"',
        html,
    )
    assert coincidencia is not None, "La página no contiene un token CSRF real"
    return unescape(coincidencia.group(1))


class ClienteConCSRF(FlaskClient):
    """Cliente de compatibilidad que atraviesa la protección CSRF real."""

    def post(self, *args, **kwargs):
        incluir_csrf = kwargs.pop("incluir_csrf", True)
        if incluir_csrf:
            datos = MultiDict(kwargs.get("data") or ())
            if "csrf_token" not in datos:
                datos.add("csrf_token", extraer_token_csrf(self.get("/login")))
            kwargs["data"] = datos
        return super().post(*args, **kwargs)


@pytest.fixture
def app():
    assert flask_app.config["TESTING"] is True
    assert flask_app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:")
    assert "config.config" not in sys.modules
    assert "config.secret_config" not in sys.modules

    with flask_app.app_context():
        db.session.remove()
        db.drop_all()
        db.create_all()

        yield flask_app

        db.session.rollback()
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return ClienteConCSRF(app)


@pytest.fixture
def usuario(app):
    user = Usuario(
        nombre="Usuario de prueba",
        email="usuario@example.test",
        password_hash=generate_password_hash("password-correcta"),
        admin=False,
        puesto="Administración",
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def administrador(app):
    user = Usuario(
        nombre="Administrador de prueba",
        email="admin@example.test",
        password_hash=generate_password_hash("password-correcta"),
        admin=True,
        puesto="Administración",
    )
    db.session.add(user)
    db.session.commit()
    return user

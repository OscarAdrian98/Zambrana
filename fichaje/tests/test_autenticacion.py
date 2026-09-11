import logging
import re
from html import unescape

import pytest
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from app.models import Modificacion, Usuario


PATRON_CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
PASSWORD_ACTUAL = "password-correcta"
PASSWORD_NUEVA = "frase nueva suficientemente larga"


def token_csrf(client, ruta):
    response = client.get(ruta)
    coincidencia = PATRON_CSRF.search(response.get_data(as_text=True))
    assert coincidencia is not None
    return unescape(coincidencia.group(1))


def post_sin_automatismo(client, ruta, datos, token=None, **kwargs):
    valores = dict(datos)
    if token is not None:
        valores["csrf_token"] = token
    return client.open(ruta, method="POST", data=valores, **kwargs)


def datos_registro(**cambios):
    datos = {
        "nombre": "Empleado de prueba",
        "email": "empleado.nuevo@example.test",
        "password": "frase segura de registro",
        "confirmar_password": "frase segura de registro",
        "puesto": "Administración",
    }
    datos.update(cambios)
    return datos


def registrar(client, **cambios):
    return post_sin_automatismo(
        client,
        "/registro",
        datos_registro(**cambios),
        token_csrf(client, "/registro"),
    )


def autenticar(
    client,
    usuario,
    password=PASSWORD_ACTUAL,
    email=None,
    recordar=False,
):
    datos = {
        "email": email if email is not None else usuario.email,
        "password": password,
    }
    if recordar:
        datos["remember"] = "on"
    return post_sin_automatismo(
        client,
        "/login",
        datos,
        token_csrf(client, "/login"),
    )


def cambiar_password(
    client,
    actual=PASSWORD_ACTUAL,
    nueva=PASSWORD_NUEVA,
    confirmar=PASSWORD_NUEVA,
    token=None,
    **kwargs,
):
    return post_sin_automatismo(
        client,
        "/cambiar-contrasena",
        {
            "contrasena_actual": actual,
            "nueva_contrasena": nueva,
            "confirmar_contrasena": confirmar,
        },
        token if token is not None else token_csrf(client, "/perfil"),
        **kwargs,
    )


def test_registro_publico_responde_y_explica_que_crea_cuenta(client):
    response = client.get("/registro")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Crea directamente tu cuenta de empleado" in html
    assert 'autocomplete="name"' in html
    assert html.count('autocomplete="new-password"') == 2


def test_anonimo_se_registra_queda_autenticado_y_no_es_admin(client):
    response = registrar(client)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/fichar")
    usuario = Usuario.query.filter_by(email="empleado.nuevo@example.test").one()
    assert usuario.admin is False
    assert client.get("/fichar").status_code == 200
    assert client.get("/admin/usuarios").headers["Location"].endswith("/fichar")


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("admin", "1"),
        ("is_admin", "true"),
        ("role", "admin"),
        ("rol", "administrador"),
        ("permissions", "all"),
    ],
)
def test_campos_de_privilegio_manipulados_no_conceden_admin(
    client, campo, valor
):
    response = registrar(client, **{campo: valor})

    assert response.status_code == 302
    assert Usuario.query.one().admin is False


def test_registro_normaliza_email_y_nombre(client):
    registrar(
        client,
        nombre="  María   del   Mar-O'Connor  ",
        email="  EMPLEADA.NUEVA@example.test  ",
    )

    usuario = Usuario.query.one()
    assert usuario.nombre == "María del Mar-O'Connor"
    assert usuario.email == "empleada.nueva@example.test"


@pytest.mark.parametrize(
    "email",
    [
        "",
        "sin-arroba.example.test",
        "dos@@example.test",
        "empleado@example",
        "empleado@-example.test",
        "empleado@example..test",
        "emple ado@example.test",
        "empleado@\nexample.test",
        "empleado@example.test\n",
        "empleado@\x00example.test",
        ("a" * 88) + "@example.test",
    ],
)
def test_registro_rechaza_emails_invalidos_sin_crear_usuario(client, email):
    response = registrar(client, email=email)

    assert response.status_code == 302
    assert Usuario.query.count() == 0


@pytest.mark.parametrize(
    "nombre",
    [
        "",
        " ",
        "A",
        "Empleado\nInyectado",
        "Empleado\x00Inyectado",
        "N" * 101,
    ],
)
def test_registro_rechaza_nombres_invalidos_sin_crear_usuario(client, nombre):
    response = registrar(client, nombre=nombre)

    assert response.status_code == 302
    assert Usuario.query.count() == 0


@pytest.mark.parametrize(
    ("password", "confirmacion"),
    [
        ("corta", "corta"),
        (" " * 10, " " * 10),
        ("frase suficientemente larga", "confirmación distinta"),
        ("frase suficientemente larga", None),
        ("x" * 129, "x" * 129),
    ],
)
def test_registro_rechaza_password_invalida(
    client, password, confirmacion
):
    registrar(
        client,
        password=password,
        confirmar_password=confirmacion,
    )

    assert Usuario.query.count() == 0


@pytest.mark.parametrize(
    "password",
    [
        "x" * 128,
        "esta es una frase de contraseña válida",
    ],
)
def test_registro_acepta_password_larga_o_frase(client, password):
    registrar(client, password=password, confirmar_password=password)

    usuario = Usuario.query.one()
    assert check_password_hash(usuario.password_hash, password)


@pytest.mark.parametrize(
    "email",
    [
        "empleado@example.test",
        "EMPLEADO@example.test",
        "  EMPLEADO@example.test  ",
    ],
)
def test_registro_rechaza_duplicados_normalizados(client, email):
    existente = Usuario(
        nombre="Histórico",
        email="Empleado@example.test",
        password_hash=generate_password_hash(PASSWORD_ACTUAL),
        admin=False,
        puesto="Administración",
    )
    db.session.add(existente)
    db.session.commit()

    response = registrar(client, email=email)

    assert response.status_code == 302
    assert Usuario.query.count() == 1
    assert existente.email == "Empleado@example.test"


@pytest.mark.parametrize(
    "error",
    [
        IntegrityError("insert", {}, RuntimeError("duplicado")),
        RuntimeError("fallo controlado"),
    ],
)
def test_fallo_de_commit_hace_rollback_y_no_deja_usuario(
    client, monkeypatch, error
):
    def fallar_commit():
        raise error

    monkeypatch.setattr(db.session, "commit", fallar_commit)
    response = registrar(client)

    assert response.status_code == 302
    assert Usuario.query.count() == 0
    assert db.session.is_active


def test_registro_exige_csrf(client):
    response = post_sin_automatismo(
        client,
        "/registro",
        datos_registro(),
    )

    assert response.status_code == 400
    assert Usuario.query.count() == 0


def test_registro_limpia_sesion_y_rota_csrf(client):
    token_anterior = token_csrf(client, "/registro")
    with client.session_transaction() as sesion:
        sesion["editar_tramo"] = {"dato": "antiguo"}

    response = post_sin_automatismo(
        client,
        "/registro",
        datos_registro(),
        token_anterior,
    )

    assert response.status_code == 302
    with client.session_transaction() as sesion:
        token_nuevo = sesion["_csrf_token"]
        assert token_nuevo != token_anterior
        assert "editar_tramo" not in sesion
        assert "_user_id" in sesion

    reutilizado = post_sin_automatismo(
        client,
        "/logout",
        {},
        token_anterior,
    )
    assert reutilizado.status_code == 400
    assert client.get("/fichar").status_code == 200

    logout = post_sin_automatismo(client, "/logout", {}, token_nuevo)
    assert logout.status_code == 302


def test_login_exacto_case_insensitive_y_con_espacios(client, usuario):
    for email in (
        usuario.email,
        usuario.email.upper(),
        f"  {usuario.email.upper()}  ",
    ):
        response = autenticar(client, usuario, email=email)
        assert response.status_code == 302
        assert client.get("/fichar").status_code == 200
        post_sin_automatismo(
            client,
            "/logout",
            {},
            token_csrf(client, "/fichar"),
        )


def test_login_historico_con_mayusculas_no_modifica_email(client, app):
    usuario = Usuario(
        nombre="Usuario histórico",
        email="Historico@example.test",
        password_hash=generate_password_hash(PASSWORD_ACTUAL),
        admin=False,
        puesto="Administración",
    )
    db.session.add(usuario)
    db.session.commit()
    email_original = usuario.email

    response = autenticar(
        client,
        usuario,
        email="  HISTORICO@example.test  ",
    )

    assert response.status_code == 302
    db.session.refresh(usuario)
    assert usuario.email == email_original


def test_login_no_enumera_cuentas(client, usuario):
    incorrecta = autenticar(client, usuario, password="incorrecta")
    inexistente = autenticar(
        client,
        usuario,
        email="no-existe@example.test",
        password="incorrecta",
    )

    for response in (incorrecta, inexistente):
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert html.count("Usuario o contraseña incorrectos") == 1


def test_login_invalido_no_falla_ni_crea_sesion(client, usuario):
    response = autenticar(
        client,
        usuario,
        email="email con espacios@example.test",
    )

    assert response.status_code == 200
    assert client.get("/fichar").status_code == 302
    with client.session_transaction() as sesion:
        assert "_user_id" not in sesion


def test_login_remember_limpia_sesion_rota_csrf_y_accede(client, usuario):
    token_anterior = token_csrf(client, "/login")
    with client.session_transaction() as sesion:
        sesion["editar_tramo"] = {"dato": "antiguo"}

    response = post_sin_automatismo(
        client,
        "/login",
        {
            "email": usuario.email,
            "password": PASSWORD_ACTUAL,
            "remember": "on",
        },
        token_anterior,
    )

    assert response.status_code == 302
    assert "remember_token=" in response.headers.get("Set-Cookie", "")
    assert client.get("/fichar").status_code == 200
    with client.session_transaction() as sesion:
        assert sesion["_csrf_token"] != token_anterior
        assert "editar_tramo" not in sesion
        assert set(sesion).issubset(
            {"_csrf_token", "_fresh", "_id", "_user_id", "_remember"}
        )


def test_csrf_anterior_de_login_falla_y_el_nuevo_funciona(client, usuario):
    token_anterior = token_csrf(client, "/login")
    post_sin_automatismo(
        client,
        "/login",
        {"email": usuario.email, "password": PASSWORD_ACTUAL},
        token_anterior,
    )
    token_nuevo = token_csrf(client, "/fichar")

    assert token_nuevo != token_anterior
    assert (
        post_sin_automatismo(client, "/logout", {}, token_anterior).status_code
        == 400
    )
    assert (
        post_sin_automatismo(client, "/logout", {}, token_nuevo).status_code
        == 302
    )


def test_login_no_guarda_password_en_navegador(client):
    html = client.get("/login").get_data(as_text=True)

    assert 'autocomplete="current-password"' in html
    assert 'setItem("rememberedPassword"' not in html
    assert "sessionStorage" not in html
    assert 'setItem("rememberedEmail"' in html


def test_cambio_password_correcto_mantiene_sesion_y_cookie_remember(
    client, usuario
):
    autenticar(client, usuario, recordar=True)
    assert client.get_cookie("remember_token") is not None

    response = cambiar_password(client)

    assert response.status_code == 302
    db.session.refresh(usuario)
    assert check_password_hash(usuario.password_hash, PASSWORD_NUEVA)
    assert client.get("/perfil").status_code == 200
    assert client.get_cookie("remember_token") is not None


@pytest.mark.parametrize(
    ("actual", "nueva", "confirmacion"),
    [
        ("incorrecta", PASSWORD_NUEVA, PASSWORD_NUEVA),
        (PASSWORD_ACTUAL, "corta", "corta"),
        (PASSWORD_ACTUAL, " " * 10, " " * 10),
        (PASSWORD_ACTUAL, PASSWORD_NUEVA, "confirmación distinta"),
        (PASSWORD_ACTUAL, "x" * 129, "x" * 129),
    ],
)
def test_cambio_password_invalido_conserva_hash(
    client, usuario, actual, nueva, confirmacion
):
    hash_anterior = usuario.password_hash
    autenticar(client, usuario)

    response = cambiar_password(
        client,
        actual=actual,
        nueva=nueva,
        confirmar=confirmacion,
    )

    assert response.status_code == 302
    db.session.refresh(usuario)
    assert usuario.password_hash == hash_anterior


def test_cambio_password_acepta_longitud_maxima(client, usuario):
    nueva = "x" * 128
    autenticar(client, usuario)

    cambiar_password(client, nueva=nueva, confirmar=nueva)

    db.session.refresh(usuario)
    assert check_password_hash(usuario.password_hash, nueva)


def test_fallo_commit_de_password_conserva_hash_y_sesion_activa(
    client, usuario, monkeypatch
):
    hash_anterior = usuario.password_hash
    autenticar(client, usuario)

    def fallar_commit():
        raise RuntimeError("fallo controlado")

    monkeypatch.setattr(db.session, "commit", fallar_commit)
    response = cambiar_password(client)

    assert response.status_code == 302
    db.session.expire_all()
    persistido = db.session.get(Usuario, usuario.id)
    assert persistido.password_hash == hash_anterior
    assert client.get("/perfil").status_code == 200


def test_password_antigua_falla_y_nueva_funciona(client, usuario):
    autenticar(client, usuario)
    cambiar_password(client)
    post_sin_automatismo(
        client,
        "/logout",
        {},
        token_csrf(client, "/perfil"),
    )

    antigua = autenticar(client, usuario, password=PASSWORD_ACTUAL)
    assert antigua.status_code == 200
    nueva = autenticar(client, usuario, password=PASSWORD_NUEVA)
    assert nueva.status_code == 302


def test_cambio_password_limpia_sesion_y_rota_csrf(client, usuario):
    autenticar(client, usuario)
    token_anterior = token_csrf(client, "/perfil")
    with client.session_transaction() as sesion:
        sesion["editar_tramo"] = {"dato": "antiguo"}

    response = cambiar_password(client, token=token_anterior)

    assert response.status_code == 302
    with client.session_transaction() as sesion:
        token_nuevo = sesion["_csrf_token"]
        assert token_nuevo != token_anterior
        assert "editar_tramo" not in sesion
        assert "_user_id" in sesion
    assert (
        post_sin_automatismo(client, "/logout", {}, token_anterior).status_code
        == 400
    )
    assert (
        post_sin_automatismo(client, "/logout", {}, token_nuevo).status_code
        == 302
    )


def test_password_no_aparece_en_respuesta_logs_ni_auditoria(
    client, usuario, caplog
):
    actual = PASSWORD_ACTUAL
    nueva = "valor secreto nuevo y largo"
    autenticar(client, usuario)

    with caplog.at_level(logging.INFO):
        response = cambiar_password(
            client,
            actual=actual,
            nueva=nueva,
            confirmar=nueva,
            follow_redirects=True,
        )

    texto = response.get_data(as_text=True)
    logs = caplog.text
    assert actual not in texto
    assert nueva not in texto
    assert actual not in logs
    assert nueva not in logs
    assert Modificacion.query.count() == 0


def test_logout_post_cierra_sesion_y_rutas_protegidas_redirigen(
    client, usuario
):
    autenticar(client, usuario)

    response = post_sin_automatismo(
        client,
        "/logout",
        {},
        token_csrf(client, "/perfil"),
    )

    assert response.status_code == 302
    assert client.get("/fichar").status_code == 302


def test_logout_get_405_y_post_sin_csrf_400(client, usuario):
    autenticar(client, usuario)

    assert client.get("/logout").status_code == 405
    assert post_sin_automatismo(client, "/logout", {}).status_code == 400
    assert client.get("/fichar").status_code == 200


def test_logout_rota_csrf_y_token_anterior_no_se_reutiliza(client, usuario):
    autenticar(client, usuario)
    token_anterior = token_csrf(client, "/perfil")

    post_sin_automatismo(client, "/logout", {}, token_anterior)
    with client.session_transaction() as sesion:
        token_nuevo = sesion["_csrf_token"]
        assert token_nuevo != token_anterior
        assert "_user_id" not in sesion

    reutilizado = post_sin_automatismo(
        client,
        "/registro",
        datos_registro(),
        token_anterior,
    )
    assert reutilizado.status_code == 400
    assert Usuario.query.count() == 1


def test_logout_no_solicita_borrar_email_recordado(client, usuario):
    autenticar(client, usuario, recordar=True)
    response = post_sin_automatismo(
        client,
        "/logout",
        {},
        token_csrf(client, "/perfil"),
    )

    assert response.status_code == 302
    assert "Clear-Site-Data" not in response.headers
    assert client.get_cookie("remember_token") is None

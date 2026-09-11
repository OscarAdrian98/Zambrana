import sys
from datetime import date, datetime, time

import pytest

from app import app as flask_app, db
from app.models import Ausencia, Fichaje, RegistroHorario
from app.services.edicion_fichajes import crear_snapshot_borrado_firmado
from config.test_config import assert_safe_test_database_uri


def login(client, user, password="password-correcta", remember=False):
    data = {
        "email": user.email,
        "password": password,
    }
    if remember:
        data["remember"] = "on"
    return client.post("/login", data=data)


def form_fragment(html, form_id):
    marker = f'id="{form_id}"'
    marker_position = html.index(marker)
    start = html.rfind("<form", 0, marker_position)
    end = html.index("</form>", marker_position) + len("</form>")
    return html[start:end]


def crear_fichaje(usuario, eliminado=False):
    fichaje = Fichaje(
        usuario_id=usuario.id,
        fecha=date.today(),
        fecha_creacion=datetime.now(),
        creado_por_admin=False,
        eliminado=eliminado,
    )
    db.session.add(fichaje)
    db.session.flush()
    return fichaje


def crear_registro(fichaje, tipo, hora, eliminado=False, origen="Tienda"):
    registro = RegistroHorario(
        fichaje_id=fichaje.id,
        tipo=tipo,
        timestamp=datetime.combine(fichaje.fecha, hora),
        creado_por_admin=False,
        eliminado=eliminado,
        origen=origen,
    )
    db.session.add(registro)
    return registro


def snapshot_borrado(fichaje):
    registros = RegistroHorario.query.filter_by(
        fichaje_id=fichaje.id,
        eliminado=False,
    ).all()
    return crear_snapshot_borrado_firmado(
        fichaje,
        registros,
        flask_app.config["SECRET_KEY"],
    )


def test_configuracion_de_test_rechaza_una_uri_no_sqlite():
    assert "config.config" not in sys.modules
    assert "config.secret_config" not in sys.modules

    with pytest.raises(RuntimeError):
        assert_safe_test_database_uri(
            "mysql+pymysql://example_user:change_me@db.example.invalid/example_db"
        )


def test_login_correcto(client, usuario):
    response = login(client, usuario, remember=True)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/fichar")
    assert "remember_token=" in response.headers.get("Set-Cookie", "")


def test_login_incorrecto(client, usuario):
    response = login(client, usuario, password="incorrecta")

    assert response.status_code == 200
    assert "Usuario o contraseña incorrectos" in response.get_data(as_text=True)
    assert client.get("/fichar").status_code == 302


def test_usuario_normal_es_rechazado_en_ruta_administrativa(client, usuario):
    login(client, usuario)

    response = client.get("/admin/usuarios")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/fichar")


def test_primera_entrada_crea_cabecera_y_registro(client, usuario):
    login(client, usuario)

    response = client.post(
        "/fichar_registro",
        data={"tipo": "entrada", "origen": "Tienda"},
    )

    assert response.status_code == 302
    assert Fichaje.query.count() == 1
    assert RegistroHorario.query.count() == 1
    assert RegistroHorario.query.one().tipo == "entrada"


def test_salida_sin_entrada_es_rechazada(client, usuario):
    login(client, usuario)

    response = client.post(
        "/fichar_registro",
        data={"tipo": "salida", "origen": "Tienda"},
        follow_redirects=True,
    )

    assert "No puedes registrar una salida" in response.get_data(as_text=True)
    assert Fichaje.query.count() == 0
    assert RegistroHorario.query.count() == 0


def test_doble_entrada_es_rechazada(client, usuario):
    login(client, usuario)
    client.post(
        "/fichar_registro",
        data={"tipo": "entrada", "origen": "Tienda"},
    )

    response = client.post(
        "/fichar_registro",
        data={"tipo": "entrada", "origen": "Remoto"},
        follow_redirects=True,
    )

    assert "Ya has registrado una entrada" in response.get_data(as_text=True)
    assert RegistroHorario.query.count() == 1


def test_entrada_y_salida_correctas(client, usuario):
    login(client, usuario)

    client.post(
        "/fichar_registro",
        data={"tipo": "entrada", "origen": "Remoto"},
    )
    response = client.post(
        "/fichar_registro",
        data={"tipo": "salida", "origen": "Remoto"},
    )

    assert response.status_code == 302
    registros = RegistroHorario.query.order_by(RegistroHorario.timestamp).all()
    assert [registro.tipo for registro in registros] == ["entrada", "salida"]
    assert [registro.origen for registro in registros] == ["Remoto", "Remoto"]


def test_vacaciones_bloquean_el_fichaje(client, usuario):
    db.session.add(
        Ausencia(
            usuario_id=usuario.id,
            fecha=date.today(),
            tipo="Vacaciones",
            creado_por_admin=False,
        )
    )
    db.session.commit()
    login(client, usuario)

    pagina_fichar = client.get("/fichar").get_data(as_text=True)
    assert "Vacaciones" in pagina_fichar
    assert 'id="form_entrada"' not in pagina_fichar
    assert 'id="form_salida"' not in pagina_fichar
    assert "No hay ninguna acción de fichaje disponible." in pagina_fichar

    response = client.post(
        "/fichar_registro",
        data={"tipo": "entrada", "origen": "Tienda"},
        follow_redirects=True,
    )

    assert "No puedes fichar hoy" in response.get_data(as_text=True)
    assert Fichaje.query.count() == 0


@pytest.mark.parametrize(
    "tipo_ausencia",
    ["Medico", "Médico", "MEDICO", "  médico  "],
)
def test_ausencia_medica_no_bloquea_el_fichaje(
    client,
    usuario,
    tipo_ausencia,
):
    db.session.add(
        Ausencia(
            usuario_id=usuario.id,
            fecha=date.today(),
            tipo=tipo_ausencia,
            hora_desde=time(10, 0),
            hora_hasta=time(11, 0),
            creado_por_admin=False,
        )
    )
    db.session.commit()
    login(client, usuario)

    pagina_fichar = client.get("/fichar").get_data(as_text=True)
    assert 'id="form_entrada"' in pagina_fichar
    assert 'id="form_salida"' not in pagina_fichar
    assert "disabled" not in form_fragment(pagina_fichar, "form_entrada")

    response = client.post(
        "/fichar_registro",
        data={"tipo": "entrada", "origen": "Tienda"},
    )

    assert response.status_code == 302
    assert Fichaje.query.count() == 1
    assert RegistroHorario.query.count() == 1


def test_varias_ausencias_eligen_el_primer_bloqueo_por_id(client, usuario):
    db.session.add_all(
        [
            Ausencia(
                usuario_id=usuario.id,
                fecha=date.today(),
                tipo="Médico",
                creado_por_admin=False,
            ),
            Ausencia(
                usuario_id=usuario.id,
                fecha=date.today(),
                tipo="Vacaciones",
                creado_por_admin=False,
            ),
            Ausencia(
                usuario_id=usuario.id,
                fecha=date.today(),
                tipo="Enfermedad",
                creado_por_admin=False,
            ),
        ]
    )
    db.session.commit()
    login(client, usuario)

    html = client.get("/fichar").get_data(as_text=True)

    assert "Vacaciones" in html
    assert "Enfermedad" not in html
    assert 'id="form_entrada"' not in html
    assert 'id="form_salida"' not in html


def test_fichaje_eliminado_no_controla_el_estado_visible(client, usuario):
    fichaje = crear_fichaje(usuario, eliminado=True)
    crear_registro(fichaje, "entrada", time(9, 0))
    db.session.commit()
    login(client, usuario)

    response = client.get("/fichar")
    html = response.get_data(as_text=True)

    assert "Dentro del trabajo" not in html
    assert "Fuera del trabajo" in html
    assert 'id="form_entrada"' in html
    assert 'id="form_salida"' not in html
    assert "disabled" not in form_fragment(html, "form_entrada")


def test_nueva_entrada_no_reutiliza_un_fichaje_eliminado(client, usuario):
    fichaje_eliminado = crear_fichaje(usuario, eliminado=True)
    registro_eliminado = crear_registro(
        fichaje_eliminado,
        "entrada",
        time(9, 0),
    )
    db.session.commit()
    login(client, usuario)

    response = client.post(
        "/fichar_registro",
        data={"tipo": "entrada", "origen": "Remoto"},
    )

    assert response.status_code == 302
    fichajes = Fichaje.query.order_by(Fichaje.id).all()
    assert len(fichajes) == 2
    assert fichajes[0].id == fichaje_eliminado.id
    assert fichajes[0].eliminado is True
    assert fichajes[1].eliminado is False

    registros = RegistroHorario.query.order_by(RegistroHorario.id).all()
    assert len(registros) == 2
    assert registros[0].id == registro_eliminado.id
    assert registros[1].fichaje_id == fichajes[1].id
    assert registros[1].origen == "Remoto"


def test_registro_eliminado_no_controla_botones_estado_ni_total(client, usuario):
    fichaje = crear_fichaje(usuario)
    crear_registro(fichaje, "entrada", time(9, 0))
    crear_registro(fichaje, "salida", time(10, 0))
    crear_registro(fichaje, "entrada", time(11, 0), eliminado=True)
    db.session.commit()
    login(client, usuario)

    response = client.get("/fichar")
    html = response.get_data(as_text=True)

    assert "Dentro del trabajo" not in html
    assert "Fuera del trabajo" in html
    assert 'id="contador-trabajo">01:00<' in html
    assert 'id="form_entrada"' in html
    assert 'id="form_salida"' not in html
    assert "disabled" not in form_fragment(html, "form_entrada")
    assert "const inicio = new Date" not in html


def test_login_no_contiene_codigo_que_almacene_la_contrasena(app):
    template, _, _ = app.jinja_loader.get_source(
        app.jinja_env,
        "login.html",
    )

    assert 'localStorage.setItem("rememberedPassword"' not in template
    assert "sessionStorage" not in template
    assert 'localStorage.removeItem("rememberedPassword")' in template
    assert template.count("try {") >= 2
    assert template.count("catch (error)") >= 2


def test_fallo_de_commit_no_deja_una_cabecera_vacia(
    client,
    usuario,
    monkeypatch,
):
    login(client, usuario)

    def commit_con_error():
        raise RuntimeError("fallo simulado antes del commit")

    monkeypatch.setattr(db.session, "commit", commit_con_error)

    response = client.post(
        "/fichar_registro",
        data={"tipo": "entrada", "origen": "Tienda"},
    )

    assert response.status_code == 302
    assert Fichaje.query.count() == 0
    assert RegistroHorario.query.count() == 0


@pytest.mark.parametrize(
    ("data", "mensaje"),
    [
        (
            {"tipo": "pausa", "origen": "Tienda"},
            "Tipo de fichaje no válido",
        ),
        (
            {"tipo": "entrada", "origen": "Casa"},
            "Origen de fichaje no válido",
        ),
    ],
)
def test_tipo_y_origen_invalidos_se_rechazan(
    client,
    usuario,
    data,
    mensaje,
):
    login(client, usuario)

    response = client.post(
        "/fichar_registro",
        data=data,
        follow_redirects=True,
    )

    assert mensaje in response.get_data(as_text=True)
    assert Fichaje.query.count() == 0
    assert RegistroHorario.query.count() == 0


def test_get_no_borra_fichaje(client, administrador):
    fichaje = crear_fichaje(administrador)
    db.session.commit()
    login(client, administrador)

    response = client.get(f"/admin/borrar_fichaje/{fichaje.id}")

    assert response.status_code == 405
    db.session.refresh(fichaje)
    assert fichaje.eliminado is False


def test_usuario_normal_no_puede_borrar_fichaje(
    client,
    usuario,
    administrador,
):
    fichaje = crear_fichaje(administrador)
    db.session.commit()
    login(client, usuario)

    response = client.post(
        f"/admin/borrar_fichaje/{fichaje.id}",
        data={"snapshot": snapshot_borrado(fichaje)},
    )

    assert response.status_code == 302
    db.session.refresh(fichaje)
    assert fichaje.eliminado is False


def test_post_de_administrador_marca_fichaje_como_eliminado(
    client,
    administrador,
):
    fichaje = crear_fichaje(administrador)
    db.session.commit()
    login(client, administrador)

    response = client.post(
        f"/admin/borrar_fichaje/{fichaje.id}",
        data={"snapshot": snapshot_borrado(fichaje)},
    )

    assert response.status_code == 302
    db.session.refresh(fichaje)
    assert fichaje.eliminado is True


def test_fallo_al_borrar_hace_rollback(
    client,
    administrador,
    monkeypatch,
):
    fichaje = crear_fichaje(administrador)
    db.session.commit()
    login(client, administrador)
    snapshot = snapshot_borrado(fichaje)

    def commit_con_error():
        raise RuntimeError("fallo simulado al borrar")

    monkeypatch.setattr(db.session, "commit", commit_con_error)

    response = client.post(
        f"/admin/borrar_fichaje/{fichaje.id}",
        data={"snapshot": snapshot},
    )

    assert response.status_code == 302
    db.session.refresh(fichaje)
    assert fichaje.eliminado is False
    assert Fichaje.query.count() == 1

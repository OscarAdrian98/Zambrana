import re
from datetime import date, datetime, time, timedelta
from html import unescape

import pytest
from werkzeug.security import check_password_hash

from app import app as flask_app, db
from app.models import Ausencia, Fichaje, RegistroHorario, SabadoAsignado, Usuario
from app.services.ausencias import crear_snapshot_ausencia_firmado
from app.services.edicion_fichajes import crear_snapshot_borrado_firmado


PATRON_TOKEN = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
PATRON_SNAPSHOT = re.compile(r'name="snapshot"\s+value="([^"]+)"')


def obtener_csrf(client, ruta="/login"):
    respuesta = client.get(ruta)
    coincidencia = PATRON_TOKEN.search(respuesta.get_data(as_text=True))
    assert coincidencia is not None
    return unescape(coincidencia.group(1))


def post_explicito(client, ruta, data=None, token=None, headers=None):
    datos = dict(data or {})
    if token is not None:
        datos["csrf_token"] = token
    return client.open(
        ruta,
        method="POST",
        data=datos,
        headers=headers,
    )


def autenticar(client, usuario, remember=False):
    datos = {
        "email": usuario.email,
        "password": "password-correcta",
    }
    if remember:
        datos["remember"] = "on"
    return post_explicito(
        client,
        "/login",
        data=datos,
        token=obtener_csrf(client),
    )


def crear_fichaje(usuario, entrada=time(9, 0), salida=time(10, 0)):
    fichaje = Fichaje(
        usuario_id=usuario.id,
        fecha=date.today(),
        fecha_creacion=datetime.now(),
        creado_por_admin=False,
        eliminado=False,
    )
    db.session.add(fichaje)
    db.session.flush()
    registros = []
    for tipo, hora in (("entrada", entrada), ("salida", salida)):
        registro = RegistroHorario(
            fichaje_id=fichaje.id,
            tipo=tipo,
            timestamp=datetime.combine(fichaje.fecha, hora),
            creado_por_admin=False,
            eliminado=False,
            origen="Tienda",
        )
        db.session.add(registro)
        registros.append(registro)
    db.session.commit()
    return fichaje, registros


def snapshot_borrado(fichaje, registros):
    return crear_snapshot_borrado_firmado(
        fichaje,
        registros,
        flask_app.config["SECRET_KEY"],
    )


def crear_ausencia(usuario):
    ausencia = Ausencia(
        usuario_id=usuario.id,
        fecha=date.today() + timedelta(days=10),
        tipo="Vacaciones",
        observaciones="Prueba CSRF",
        creado_por_admin=False,
    )
    db.session.add(ausencia)
    db.session.commit()
    return ausencia


def snapshot_ausencia(usuario, ausencia):
    return crear_snapshot_ausencia_firmado(
        usuario.id,
        (ausencia,),
        flask_app.config["SECRET_KEY"],
    )


def datos_edicion(client, fichaje, registros):
    html = client.get(
        f"/admin/editar_fichaje/{fichaje.id}"
    ).get_data(as_text=True)
    token = unescape(PATRON_TOKEN.search(html).group(1))
    snapshot = unescape(PATRON_SNAPSHOT.search(html).group(1))
    clave = f"existente_{registros[0].id}_{registros[1].id}"
    return token, {
        "snapshot": snapshot,
        f"tramos[{clave}][entrada_id]": str(registros[0].id),
        f"tramos[{clave}][salida_id]": str(registros[1].id),
        f"tramos[{clave}][entrada]": "08:30",
        f"tramos[{clave}][salida]": "10:00",
        f"tramos[{clave}][origen]": "Tienda",
        f"tramos[{clave}][eliminar]": "0",
    }


# 1
def test_get_genera_token_aleatorio_en_sesion(client):
    primero = obtener_csrf(client)
    segundo = obtener_csrf(client)

    assert primero == segundo
    assert len(primero) >= 32


# 2
def test_post_sin_token_se_rechaza(client):
    response = post_explicito(
        client,
        "/login",
        {"email": "nadie@example.test", "password": "x"},
    )

    assert response.status_code == 400
    assert response.get_data(as_text=True) == "Solicitud no válida."


# 3
def test_token_incorrecto_se_rechaza_sin_filtrar_el_correcto(client):
    correcto = obtener_csrf(client)
    response = post_explicito(
        client,
        "/login",
        {"email": "nadie@example.test", "password": "x"},
        token="token-fabricado",
    )

    assert response.status_code == 400
    assert correcto not in response.get_data(as_text=True)


# 4
def test_token_correcto_se_acepta(client, usuario):
    response = autenticar(client, usuario)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/fichar")


# 5
def test_token_de_otra_sesion_se_rechaza(app, client, usuario):
    otro_cliente = app.test_client()
    token_ajeno = obtener_csrf(otro_cliente)
    obtener_csrf(client)

    response = post_explicito(
        client,
        "/login",
        {"email": usuario.email, "password": "password-correcta"},
        token=token_ajeno,
    )

    assert response.status_code == 400
    assert client.get("/perfil").status_code == 302


# 6
def test_rechazo_general_no_modifica_datos(client, usuario):
    autenticar(client, usuario)

    response = post_explicito(
        client,
        "/fichar_registro",
        {"tipo": "entrada", "origen": "Tienda"},
    )

    assert response.status_code == 400
    assert Fichaje.query.count() == 0
    assert RegistroHorario.query.count() == 0


# 7
def test_get_de_solo_lectura_sigue_funcionando(client, usuario):
    autenticar(client, usuario)

    response = client.get("/resumen")

    assert response.status_code == 200


# 8
def test_login_con_token(client, usuario):
    response = autenticar(client, usuario)

    assert response.status_code == 302
    assert client.get("/perfil").status_code == 200


# 9
def test_login_sin_token(client, usuario):
    response = post_explicito(
        client,
        "/login",
        {"email": usuario.email, "password": "password-correcta"},
    )

    assert response.status_code == 400
    assert client.get("/perfil").status_code == 302


# 10
def test_login_con_token_incorrecto(client, usuario):
    obtener_csrf(client)
    response = post_explicito(
        client,
        "/login",
        {"email": usuario.email, "password": "password-correcta"},
        token="incorrecto",
    )

    assert response.status_code == 400
    assert client.get("/perfil").status_code == 302


# 11
def test_login_remember_sigue_funcionando(client, usuario):
    response = autenticar(client, usuario, remember=True)

    assert response.status_code == 302
    assert "remember_token=" in response.headers.get("Set-Cookie", "")


# 12
def test_logout_mediante_post_con_token(client, usuario):
    autenticar(client, usuario)
    token = obtener_csrf(client, "/perfil")

    response = post_explicito(client, "/logout", token=token)

    assert response.status_code == 302
    assert client.get("/perfil").status_code == 302


# 13
def test_logout_mediante_get_no_cierra_sesion(client, usuario):
    autenticar(client, usuario)

    response = client.get("/logout")

    assert response.status_code == 405
    assert client.get("/perfil").status_code == 200


# 14
def test_logout_sin_token_se_rechaza_y_mantiene_sesion(client, usuario):
    autenticar(client, usuario)

    response = post_explicito(client, "/logout")

    assert response.status_code == 400
    assert client.get("/perfil").status_code == 200


# 15
def test_entrada_con_token(client, usuario):
    autenticar(client, usuario)
    token = obtener_csrf(client, "/fichar")

    response = post_explicito(
        client,
        "/fichar_registro",
        {"tipo": "entrada", "origen": "Tienda"},
        token,
    )

    assert response.status_code == 302
    assert Fichaje.query.count() == 1
    assert RegistroHorario.query.count() == 1


# 16
def test_entrada_sin_token(client, usuario):
    autenticar(client, usuario)

    response = post_explicito(
        client,
        "/fichar_registro",
        {"tipo": "entrada", "origen": "Tienda"},
    )

    assert response.status_code == 400
    assert Fichaje.query.count() == 0


# 17
def test_salida_con_token(client, usuario):
    fichaje, registros = crear_fichaje(usuario)
    db.session.delete(registros[1])
    db.session.commit()
    autenticar(client, usuario)

    response = post_explicito(
        client,
        "/fichar_registro",
        {"tipo": "salida"},
        obtener_csrf(client, "/fichar"),
    )

    assert response.status_code == 302
    assert Fichaje.query.count() == 1
    assert RegistroHorario.query.filter_by(fichaje_id=fichaje.id).count() == 2


# 18
def test_token_invalido_no_crea_fichaje(client, usuario):
    autenticar(client, usuario)

    response = post_explicito(
        client,
        "/fichar_registro",
        {"tipo": "entrada", "origen": "Tienda"},
        "incorrecto",
    )

    assert response.status_code == 400
    assert Fichaje.query.count() == 0


# 19
def test_token_invalido_no_crea_registro_horario(client, usuario):
    autenticar(client, usuario)

    post_explicito(
        client,
        "/fichar_registro",
        {"tipo": "entrada", "origen": "Tienda"},
        "incorrecto",
    )

    assert RegistroHorario.query.count() == 0


# 20
def test_crear_ausencia_con_token(client, usuario):
    autenticar(client, usuario)
    fecha = date.today() + timedelta(days=20)

    response = post_explicito(
        client,
        "/mis-ausencias",
        {
            "fecha_desde": fecha.isoformat(),
            "fecha_hasta": fecha.isoformat(),
            "tipo": "Vacaciones",
            "observaciones": "CSRF válido",
        },
        obtener_csrf(client, "/mis-ausencias"),
    )

    assert response.status_code == 302
    assert Ausencia.query.count() == 1


# 21
def test_crear_ausencia_sin_token(client, usuario):
    autenticar(client, usuario)
    fecha = date.today() + timedelta(days=20)

    response = post_explicito(
        client,
        "/mis-ausencias",
        {
            "fecha_desde": fecha.isoformat(),
            "fecha_hasta": fecha.isoformat(),
            "tipo": "Vacaciones",
        },
    )

    assert response.status_code == 400
    assert Ausencia.query.count() == 0


# 22
def test_eliminar_ausencia_con_token(client, usuario):
    ausencia = crear_ausencia(usuario)
    autenticar(client, usuario)

    response = post_explicito(
        client,
        "/eliminar-ausencia",
        {"snapshot": snapshot_ausencia(usuario, ausencia)},
        obtener_csrf(client, "/mis-ausencias"),
    )

    assert response.status_code == 302
    assert Ausencia.query.count() == 0


# 23
def test_eliminar_ausencia_sin_token(client, usuario):
    ausencia = crear_ausencia(usuario)
    autenticar(client, usuario)

    response = post_explicito(
        client,
        "/eliminar-ausencia",
        {"snapshot": snapshot_ausencia(usuario, ausencia)},
    )

    assert response.status_code == 400
    assert Ausencia.query.count() == 1


# 24
def test_rechazo_de_ausencia_mantiene_filas_originales(client, usuario):
    ausencia = crear_ausencia(usuario)
    autenticar(client, usuario)

    post_explicito(
        client,
        "/eliminar-ausencia",
        {"snapshot": snapshot_ausencia(usuario, ausencia)},
        "fabricado",
    )

    assert [fila.id for fila in Ausencia.query.all()] == [ausencia.id]


# 25
def test_crear_fichaje_administrativo_con_token(
    client,
    administrador,
    usuario,
):
    autenticar(client, administrador)
    fecha = date.today() - timedelta(days=30)

    response = post_explicito(
        client,
        f"/admin/crear-fichaje/{usuario.id}",
        {
            "usuario_id": str(usuario.id),
            "fecha": fecha.isoformat(),
            "entrada": "09:00",
            "salida": "10:00",
        },
        obtener_csrf(client, f"/admin/crear-fichaje/{usuario.id}"),
    )

    assert response.status_code == 302
    assert Fichaje.query.filter_by(usuario_id=usuario.id).count() == 1
    assert RegistroHorario.query.count() == 2


# 26
def test_borrar_fichaje_con_token(client, administrador):
    fichaje, registros = crear_fichaje(administrador)
    autenticar(client, administrador)

    response = post_explicito(
        client,
        f"/admin/borrar_fichaje/{fichaje.id}",
        data={"snapshot": snapshot_borrado(fichaje, registros)},
        token=obtener_csrf(client, f"/admin/fichajes/{administrador.id}"),
    )

    assert response.status_code == 302
    db.session.refresh(fichaje)
    assert fichaje.eliminado is True


# 27
def test_borrar_fichaje_sin_token_no_cambia_eliminado(client, administrador):
    fichaje, registros = crear_fichaje(administrador)
    autenticar(client, administrador)

    response = post_explicito(
        client,
        f"/admin/borrar_fichaje/{fichaje.id}",
        data={"snapshot": snapshot_borrado(fichaje, registros)},
    )

    assert response.status_code == 400
    db.session.refresh(fichaje)
    assert fichaje.eliminado is False


# 28
def test_editar_con_csrf_y_snapshot_correctos(client, administrador):
    fichaje, registros = crear_fichaje(administrador)
    autenticar(client, administrador)
    token, data = datos_edicion(client, fichaje, registros)

    response = post_explicito(
        client,
        f"/admin/editar_fichaje/{fichaje.id}",
        data,
        token,
    )

    assert response.status_code == 302
    db.session.refresh(registros[0])
    assert registros[0].eliminado is True
    activa = RegistroHorario.query.filter_by(
        fichaje_id=fichaje.id,
        tipo="entrada",
        eliminado=False,
    ).one()
    assert activa.timestamp.time() == time(8, 30)


# 29
def test_editar_sin_csrf_no_modifica_registros(client, administrador):
    fichaje, registros = crear_fichaje(administrador)
    autenticar(client, administrador)
    _, data = datos_edicion(client, fichaje, registros)
    original = registros[0].timestamp

    response = post_explicito(
        client,
        f"/admin/editar_fichaje/{fichaje.id}",
        data,
    )

    assert response.status_code == 400
    db.session.refresh(registros[0])
    assert registros[0].timestamp == original


# 30
def test_registrar_ausencia_administrativa_con_token(
    client,
    administrador,
    usuario,
):
    autenticar(client, administrador)
    fecha = date.today() + timedelta(days=25)
    ruta = f"/admin/registrar-ausencia/{usuario.id}"

    response = post_explicito(
        client,
        ruta,
        {
            "fecha_desde": fecha.isoformat(),
            "fecha_hasta": fecha.isoformat(),
            "tipo": "Vacaciones",
            "observaciones": "Administrativa",
        },
        obtener_csrf(client, ruta),
    )

    assert response.status_code == 302
    ausencia = Ausencia.query.one()
    assert ausencia.usuario_id == usuario.id
    assert ausencia.creado_por_admin is True


# 31
def test_guardar_sabados_con_token(client, usuario):
    autenticar(client, usuario)
    sabado = date.today()
    while sabado.weekday() != 5:
        sabado += timedelta(days=1)
    if sabado.month != date.today().month:
        sabado = date.today().replace(day=1)
        while sabado.weekday() != 5:
            sabado += timedelta(days=1)

    response = post_explicito(
        client,
        "/perfil",
        {"sabados[]": sabado.isoformat()},
        obtener_csrf(client, "/perfil"),
    )

    assert response.status_code == 302
    assert SabadoAsignado.query.filter_by(usuario_id=usuario.id).count() == 1


# 32
def test_guardar_sabados_sin_token(client, usuario):
    autenticar(client, usuario)

    response = post_explicito(
        client,
        "/perfil",
        {"sabados[]": date.today().isoformat()},
    )

    assert response.status_code == 400
    assert SabadoAsignado.query.count() == 0


# 33
def test_cambiar_contrasena_con_token(client, usuario):
    autenticar(client, usuario)

    response = post_explicito(
        client,
        "/cambiar-contrasena",
        {
            "contrasena_actual": "password-correcta",
            "nueva_contrasena": "nueva-segura",
            "confirmar_contrasena": "nueva-segura",
        },
        obtener_csrf(client, "/perfil"),
    )

    assert response.status_code == 302
    db.session.refresh(usuario)
    assert check_password_hash(usuario.password_hash, "nueva-segura")


# 34
def test_cambiar_contrasena_sin_token(client, usuario):
    hash_original = usuario.password_hash
    autenticar(client, usuario)

    response = post_explicito(
        client,
        "/cambiar-contrasena",
        {
            "contrasena_actual": "password-correcta",
            "nueva_contrasena": "nueva-segura",
            "confirmar_contrasena": "nueva-segura",
        },
    )

    assert response.status_code == 400
    db.session.refresh(usuario)
    assert usuario.password_hash == hash_original


# 35
def test_registro_con_token(client):
    response = post_explicito(
        client,
        "/registro",
        {
            "nombre": "Usuario nuevo",
            "email": "nuevo@example.test",
            "password": "password-registro",
            "confirmar_password": "password-registro",
            "puesto": "Administración",
        },
        obtener_csrf(client, "/registro"),
    )

    assert response.status_code == 302
    assert Usuario.query.filter_by(email="nuevo@example.test").count() == 1


# 36
def test_registro_sin_token(client):
    response = post_explicito(
        client,
        "/registro",
        {
            "nombre": "Usuario nuevo",
            "email": "nuevo@example.test",
            "password": "password-registro",
            "confirmar_password": "password-registro",
            "puesto": "Administración",
        },
    )

    assert response.status_code == 400


# 37
def test_rechazo_de_registro_no_crea_usuario(client):
    post_explicito(
        client,
        "/registro",
        {
            "nombre": "Usuario nuevo",
            "email": "nuevo@example.test",
            "password": "password-registro",
            "confirmar_password": "password-registro",
            "puesto": "Administración",
        },
        "incorrecto",
    )

    assert Usuario.query.filter_by(email="nuevo@example.test").count() == 0


def test_edicion_csrf_invalido_y_snapshot_valido_no_modifica(
    client,
    administrador,
):
    fichaje, registros = crear_fichaje(administrador)
    autenticar(client, administrador)
    _, data = datos_edicion(client, fichaje, registros)
    original = registros[0].timestamp

    response = post_explicito(
        client,
        f"/admin/editar_fichaje/{fichaje.id}",
        data,
        "incorrecto",
    )

    assert response.status_code == 400
    db.session.refresh(registros[0])
    assert registros[0].timestamp == original


def test_edicion_csrf_valido_y_snapshot_manipulado_no_modifica(
    client,
    administrador,
):
    fichaje, registros = crear_fichaje(administrador)
    autenticar(client, administrador)
    token, data = datos_edicion(client, fichaje, registros)
    data["snapshot"] += "manipulado"
    original = registros[0].timestamp

    response = post_explicito(
        client,
        f"/admin/editar_fichaje/{fichaje.id}",
        data,
        token,
    )

    assert response.status_code == 302
    db.session.refresh(registros[0])
    assert registros[0].timestamp == original


def test_edicion_csrf_y_snapshot_invalidos_no_modifica(
    client,
    administrador,
):
    fichaje, registros = crear_fichaje(administrador)
    autenticar(client, administrador)
    _, data = datos_edicion(client, fichaje, registros)
    data["snapshot"] += "manipulado"
    original = registros[0].timestamp

    response = post_explicito(
        client,
        f"/admin/editar_fichaje/{fichaje.id}",
        data,
        "incorrecto",
    )

    assert response.status_code == 400
    db.session.refresh(registros[0])
    assert registros[0].timestamp == original


@pytest.mark.parametrize("metodo", ["POST", "PUT", "PATCH", "DELETE"])
def test_todos_los_metodos_mutables_exigen_csrf(client, metodo):
    response = client.open("/login", method=metodo)

    assert response.status_code == 400


def test_token_correcto_se_acepta_mediante_cabecera(client, usuario):
    token = obtener_csrf(client)

    response = post_explicito(
        client,
        "/login",
        {"email": usuario.email, "password": "password-correcta"},
        headers={"X-CSRF-Token": token},
    )

    assert response.status_code == 302


def test_formulario_dinamico_conserva_un_token_en_el_formulario_principal(
    client,
    administrador,
):
    fichaje, _ = crear_fichaje(administrador)
    autenticar(client, administrador)
    html = client.get(
        f"/admin/editar_fichaje/{fichaje.id}"
    ).get_data(as_text=True)
    inicio = html.index('<form method="POST"')
    fin = html.index("</form>", inicio)
    formulario = html[inicio:fin]

    assert formulario.count('name="csrf_token"') == 1
    assert "htmlTramoNuevo" in html


def test_todos_los_formularios_post_declaran_token_csrf(app):
    plantillas = (
        "login.html",
        "registro.html",
        "fichar.html",
        "ausencias.html",
        "perfil.html",
        "admin_registrar_ausencia.html",
        "admin_crear_fichaje.html",
        "editar_fichaje_admin.html",
        "admin_fichajes_usuario.html",
    )

    for plantilla in plantillas:
        fuente, _, _ = app.jinja_loader.get_source(app.jinja_env, plantilla)
        formularios = re.findall(
            r'<form\b[^>]*method="POST"[^>]*>.*?</form>',
            fuente,
            flags=re.DOTALL,
        )
        assert formularios, plantilla
        assert all('name="csrf_token"' in formulario for formulario in formularios)


def test_fetch_interno_solo_consulta_api_get(app):
    fuente, _, _ = app.jinja_loader.get_source(app.jinja_env, "fichar.html")

    assert 'fetch("/api/debo_fichar")' in fuente
    assert 'method: "POST"' not in fuente


def test_vista_fichar_no_acepta_post_adicional(client, usuario):
    autenticar(client, usuario)

    response = post_explicito(
        client,
        "/fichar",
        token=obtener_csrf(client, "/fichar"),
    )

    assert response.status_code == 405
    assert Fichaje.query.count() == 0
    assert RegistroHorario.query.count() == 0

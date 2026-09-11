from datetime import date, datetime, time, timedelta
from html import unescape
import inspect
import re

import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from app import db
from app import routes
from app.models import Fichaje, Modificacion, RegistroHorario, Usuario
from app.services.edicion_fichajes import crear_snapshot_borrado_firmado
import app.services.fichajes as fichajes_service
from app.services.fichajes import (
    ADMIN_BORRADO_ADMINISTRADOR_INEXISTENTE,
    ADMIN_BORRADO_CONFLICTO_CONCURRENTE,
    ADMIN_BORRADO_ELIMINADO,
    ADMIN_BORRADO_ERROR_PERSISTENCIA,
    ADMIN_BORRADO_FICHAJE_INEXISTENTE,
    ADMIN_BORRADO_SIN_PERMISOS,
    ADMIN_BORRADO_USUARIO_INEXISTENTE,
    ADMIN_BORRADO_YA_ELIMINADO,
    ResultadoBorradoFichajeAdministrativo,
    eliminar_fichaje_administrativo,
)


FECHA = date(2026, 3, 29)
PATRON_SNAPSHOT = re.compile(r'name="snapshot"\s+value="([^"]+)"')


def crear_usuario(*, admin=False, sufijo="borrado"):
    usuario = Usuario(
        nombre=f"Usuario {sufijo}",
        email=f"{sufijo}@example.test",
        password_hash="not-used",
        admin=admin,
        puesto="Administracion",
    )
    db.session.add(usuario)
    db.session.commit()
    return usuario


def crear_fichaje(usuario, registros=(), *, eliminado=False, fecha=FECHA):
    fichaje = Fichaje(
        usuario_id=usuario.id,
        fecha=fecha,
        fecha_creacion=datetime.combine(fecha, time(7, 30)),
        creado_por_admin=True,
        eliminado=eliminado,
    )
    db.session.add(fichaje)
    db.session.flush()
    creados = []
    for tipo, hora, origen, registro_eliminado, creado_por_admin in registros:
        registro = RegistroHorario(
            fichaje_id=fichaje.id,
            tipo=tipo,
            timestamp=datetime.combine(fecha, hora),
            origen=origen,
            eliminado=registro_eliminado,
            creado_por_admin=creado_por_admin,
        )
        db.session.add(registro)
        creados.append(registro)
    db.session.commit()
    return fichaje, creados


def registros_variados():
    return (
        ("entrada", time(9, 0), "Tienda", False, False),
        ("salida", time(12, 0), "Auto", False, True),
        ("entrada", time(16, 0), "Remoto", True, True),
        ("salida", time(20, 0), "Remoto", True, False),
    )


def estado_hijos(fichaje_id):
    return [
        (
            registro.id,
            registro.fichaje_id,
            registro.tipo,
            registro.timestamp,
            registro.origen,
            registro.eliminado,
            registro.creado_por_admin,
        )
        for registro in RegistroHorario.query.filter_by(
            fichaje_id=fichaje_id
        ).order_by(RegistroHorario.id)
    ]


def snapshot_actual(app, fichaje_id):
    fichaje = db.session.get(Fichaje, fichaje_id)
    registros = (
        RegistroHorario.query.filter_by(
            fichaje_id=fichaje_id,
            eliminado=False,
        )
        .order_by(RegistroHorario.timestamp, RegistroHorario.id)
        .all()
    )
    return crear_snapshot_borrado_firmado(
        fichaje,
        registros,
        app.config["SECRET_KEY"],
    )


def borrar(app, administrador_id, fichaje_id, snapshot):
    db.session.rollback()
    return eliminar_fichaje_administrativo(
        db.session,
        administrador_id=administrador_id,
        fichaje_id=fichaje_id,
        snapshot=snapshot,
        secret_key=app.config["SECRET_KEY"],
    )


def autenticar(client, usuario):
    return client.post(
        "/login",
        data={"email": usuario.email, "password": "password-correcta"},
    )


def test_borrado_valido_preserva_cabecera_hijos_y_hace_un_commit(
    app,
    administrador,
    usuario,
    monkeypatch,
):
    fichaje, _ = crear_fichaje(usuario, registros_variados())
    fichaje_id = fichaje.id
    estado_cabecera = (
        fichaje.usuario_id,
        fichaje.fecha,
        fichaje.fecha_creacion,
        fichaje.creado_por_admin,
    )
    hijos_antes = estado_hijos(fichaje_id)
    snapshot = snapshot_actual(app, fichaje_id)
    commit_real = db.session.commit
    commits = []

    def commit_contado():
        commits.append(True)
        return commit_real()

    monkeypatch.setattr(db.session, "commit", commit_contado)
    resultado = borrar(app, administrador.id, fichaje_id, snapshot)

    cabecera = db.session.get(Fichaje, fichaje_id)
    assert resultado.codigo == ADMIN_BORRADO_ELIMINADO
    assert commits == [True]
    assert cabecera.eliminado is True
    assert (
        cabecera.usuario_id,
        cabecera.fecha,
        cabecera.fecha_creacion,
        cabecera.creado_por_admin,
    ) == estado_cabecera
    assert estado_hijos(fichaje_id) == hijos_antes
    assert Modificacion.query.filter_by(fichaje_id=fichaje_id).count() == 0


def test_administrador_inexistente_no_modifica(app, usuario):
    fichaje, _ = crear_fichaje(usuario, registros_variados())
    fichaje_id = fichaje.id
    antes = estado_hijos(fichaje_id)

    resultado = borrar(app, 999999, fichaje_id, snapshot_actual(app, fichaje_id))

    assert resultado.codigo == ADMIN_BORRADO_ADMINISTRADOR_INEXISTENTE
    assert db.session.get(Fichaje, fichaje_id).eliminado is False
    assert estado_hijos(fichaje_id) == antes


def test_usuario_sin_permisos_no_modifica(app, usuario):
    fichaje, _ = crear_fichaje(usuario)
    fichaje_id = fichaje.id

    resultado = borrar(
        app,
        usuario.id,
        fichaje_id,
        snapshot_actual(app, fichaje_id),
    )

    assert resultado.codigo == ADMIN_BORRADO_SIN_PERMISOS
    assert db.session.get(Fichaje, fichaje_id).eliminado is False


@pytest.mark.parametrize("fichaje_id", [None, False, 0, -1, 999999])
def test_fichaje_inexistente_o_id_invalido_no_modifica(
    app,
    administrador,
    usuario,
    fichaje_id,
):
    existente, _ = crear_fichaje(usuario)
    existente_id = existente.id

    resultado = borrar(app, administrador.id, fichaje_id, "irrelevante")

    assert resultado.codigo == ADMIN_BORRADO_FICHAJE_INEXISTENTE
    assert db.session.get(Fichaje, existente_id).eliminado is False


def test_usuario_propietario_inexistente_es_estado_controlado(
    app,
    administrador,
):
    fichaje = Fichaje(
        usuario_id=999999,
        fecha=FECHA,
        fecha_creacion=datetime.combine(FECHA, time(7)),
        creado_por_admin=False,
        eliminado=False,
    )
    db.session.add(fichaje)
    db.session.commit()
    fichaje_id = fichaje.id

    resultado = borrar(app, administrador.id, fichaje_id, "irrelevante")

    assert resultado.codigo == ADMIN_BORRADO_USUARIO_INEXISTENTE
    assert db.session.get(Fichaje, fichaje_id).eliminado is False


def test_fichaje_ya_eliminado_es_idempotente_y_no_exige_snapshot_vigente(
    app,
    administrador,
    usuario,
):
    fichaje, _ = crear_fichaje(
        usuario,
        registros_variados(),
        eliminado=True,
    )
    fichaje_id = fichaje.id
    antes = estado_hijos(fichaje_id)

    resultado = borrar(app, administrador.id, fichaje_id, "manipulado")

    assert resultado.codigo == ADMIN_BORRADO_YA_ELIMINADO
    assert db.session.get(Fichaje, fichaje_id).eliminado is True
    assert estado_hijos(fichaje_id) == antes
    assert Modificacion.query.filter_by(fichaje_id=fichaje_id).count() == 0


def test_conserva_todos_los_campos_de_registros_hijos(
    app,
    administrador,
    usuario,
):
    fichaje, _ = crear_fichaje(usuario, registros_variados())
    fichaje_id = fichaje.id
    antes = estado_hijos(fichaje_id)

    resultado = borrar(
        app,
        administrador.id,
        fichaje_id,
        snapshot_actual(app, fichaje_id),
    )

    assert resultado.codigo == ADMIN_BORRADO_ELIMINADO
    assert estado_hijos(fichaje_id) == antes


def test_fichaje_sin_registros_se_elimina_sin_error(
    app,
    administrador,
    usuario,
):
    fichaje, _ = crear_fichaje(usuario)
    fichaje_id = fichaje.id

    resultado = borrar(
        app,
        administrador.id,
        fichaje_id,
        snapshot_actual(app, fichaje_id),
    )

    assert resultado.codigo == ADMIN_BORRADO_ELIMINADO
    assert db.session.get(Fichaje, fichaje_id).eliminado is True
    assert RegistroHorario.query.filter_by(fichaje_id=fichaje_id).count() == 0


def test_varias_cabeceras_activas_borra_solo_el_id_dirigido(
    app,
    administrador,
    usuario,
):
    primero, _ = crear_fichaje(usuario, registros_variados())
    segundo, _ = crear_fichaje(usuario, (), fecha=primero.fecha)
    primero_id = primero.id
    segundo_id = segundo.id

    resultado = borrar(
        app,
        administrador.id,
        primero_id,
        snapshot_actual(app, primero_id),
    )

    assert resultado.codigo == ADMIN_BORRADO_ELIMINADO
    assert db.session.get(Fichaje, primero_id).eliminado is True
    assert db.session.get(Fichaje, segundo_id).eliminado is False


def test_snapshot_manipulado_no_elimina(app, administrador, usuario):
    fichaje, _ = crear_fichaje(usuario, registros_variados())
    fichaje_id = fichaje.id
    snapshot = snapshot_actual(app, fichaje_id)

    resultado = borrar(app, administrador.id, fichaje_id, snapshot + "x")

    assert resultado.codigo == ADMIN_BORRADO_CONFLICTO_CONCURRENTE
    assert db.session.get(Fichaje, fichaje_id).eliminado is False


@pytest.mark.parametrize("cambio", ["edicion", "manual"])
def test_snapshot_obsoleto_por_cambio_de_registros_no_elimina(
    app,
    administrador,
    usuario,
    cambio,
):
    fichaje, registros = crear_fichaje(usuario, registros_variados()[:2])
    fichaje_id = fichaje.id
    snapshot = snapshot_actual(app, fichaje_id)
    if cambio == "edicion":
        registros[0].timestamp = datetime.combine(FECHA, time(9, 15))
    else:
        db.session.add(
            RegistroHorario(
                fichaje_id=fichaje_id,
                tipo="entrada",
                timestamp=datetime.combine(FECHA, time(16)),
                origen="Tienda",
                eliminado=False,
                creado_por_admin=False,
            )
        )
    db.session.commit()

    resultado = borrar(app, administrador.id, fichaje_id, snapshot)

    assert resultado.codigo == ADMIN_BORRADO_CONFLICTO_CONCURRENTE
    assert db.session.get(Fichaje, fichaje_id).eliminado is False


def test_snapshot_obsoleto_por_cambio_de_fecha_de_cabecera_no_elimina(
    app,
    administrador,
    usuario,
):
    fichaje, _ = crear_fichaje(usuario)
    fichaje_id = fichaje.id
    snapshot = snapshot_actual(app, fichaje_id)
    fichaje.fecha = FECHA + timedelta(days=1)
    db.session.commit()

    resultado = borrar(app, administrador.id, fichaje_id, snapshot)

    assert resultado.codigo == ADMIN_BORRADO_CONFLICTO_CONCURRENTE
    assert db.session.get(Fichaje, fichaje_id).eliminado is False


def test_fallo_al_actualizar_cabecera_hace_rollback_total(
    app,
    administrador,
    usuario,
):
    fichaje, _ = crear_fichaje(usuario, registros_variados())
    fichaje_id = fichaje.id
    antes = estado_hijos(fichaje_id)

    def fallar_actualizacion(_mapper, _connection, _target):
        raise RuntimeError("fallo de actualización controlado")

    event.listen(Fichaje, "before_update", fallar_actualizacion)
    try:
        resultado = borrar(
            app,
            administrador.id,
            fichaje_id,
            snapshot_actual(app, fichaje_id),
        )
    finally:
        event.remove(Fichaje, "before_update", fallar_actualizacion)

    assert resultado.codigo == ADMIN_BORRADO_ERROR_PERSISTENCIA
    assert not db.session.new
    assert not db.session.dirty
    assert db.session.get(Fichaje, fichaje_id).eliminado is False
    assert estado_hijos(fichaje_id) == antes


def test_fallo_flush_hace_rollback_y_deja_sesion_reutilizable(
    app,
    administrador,
    usuario,
    monkeypatch,
):
    fichaje, _ = crear_fichaje(usuario)
    fichaje_id = fichaje.id
    snapshot = snapshot_actual(app, fichaje_id)
    flush_real = db.session.flush
    llamadas = []

    def flush_con_fallo(*args, **kwargs):
        if not llamadas:
            llamadas.append(True)
            raise RuntimeError("fallo de flush controlado")
        return flush_real(*args, **kwargs)

    monkeypatch.setattr(db.session, "flush", flush_con_fallo)
    primero = borrar(app, administrador.id, fichaje_id, snapshot)
    assert not db.session.new
    assert not db.session.dirty
    segundo = borrar(app, administrador.id, fichaje_id, snapshot)

    assert primero.codigo == ADMIN_BORRADO_ERROR_PERSISTENCIA
    assert segundo.codigo == ADMIN_BORRADO_ELIMINADO
    assert db.session.get(Fichaje, fichaje_id).eliminado is True


def test_mariadb_error_1020_se_trata_como_conflicto_controlado(
    app,
    administrador,
    usuario,
    monkeypatch,
):
    fichaje, _ = crear_fichaje(usuario, registros_variados())
    fichaje_id = fichaje.id
    snapshot = snapshot_actual(app, fichaje_id)
    error = OperationalError(
        "UPDATE fichajes",
        {},
        Exception(1020, "record changed"),
    )
    monkeypatch.setattr(
        db.session,
        "flush",
        lambda: (_ for _ in ()).throw(error),
    )

    resultado = borrar(app, administrador.id, fichaje_id, snapshot)

    assert resultado.codigo == ADMIN_BORRADO_CONFLICTO_CONCURRENTE
    assert db.session.get(Fichaje, fichaje_id).eliminado is False
    assert not db.session.new and not db.session.dirty and db.session.is_active


def test_fallo_commit_hace_rollback_y_reintento_elimina_una_vez(
    app,
    administrador,
    usuario,
    monkeypatch,
):
    fichaje, _ = crear_fichaje(usuario, registros_variados())
    fichaje_id = fichaje.id
    snapshot = snapshot_actual(app, fichaje_id)
    hijos_antes = estado_hijos(fichaje_id)
    commit_real = db.session.commit
    llamadas = []

    def commit_con_fallo():
        if not llamadas:
            llamadas.append(True)
            raise RuntimeError("fallo de commit controlado")
        return commit_real()

    monkeypatch.setattr(db.session, "commit", commit_con_fallo)
    primero = borrar(app, administrador.id, fichaje_id, snapshot)
    assert primero.codigo == ADMIN_BORRADO_ERROR_PERSISTENCIA
    assert not db.session.new
    assert not db.session.dirty
    assert db.session.get(Fichaje, fichaje_id).eliminado is False

    segundo = borrar(app, administrador.id, fichaje_id, snapshot)
    tercero = borrar(app, administrador.id, fichaje_id, snapshot)

    assert segundo.codigo == ADMIN_BORRADO_ELIMINADO
    assert tercero.codigo == ADMIN_BORRADO_YA_ELIMINADO
    assert estado_hijos(fichaje_id) == hijos_antes
    assert Modificacion.query.filter_by(fichaje_id=fichaje_id).count() == 0


def test_api_no_acepta_campos_forzados():
    firma = inspect.signature(eliminar_fichaje_administrativo)

    for campo in (
        "eliminado",
        "usuario_id",
        "fecha",
        "registros",
        "creado_por_admin",
        "origen",
    ):
        assert campo not in firma.parameters


def test_get_no_borra_y_post_anonimo_o_empleado_no_borra(
    client,
    app,
    administrador,
    usuario,
):
    fichaje, _ = crear_fichaje(usuario)
    fichaje_id = fichaje.id
    ruta = f"/admin/borrar_fichaje/{fichaje_id}"
    snapshot = snapshot_actual(app, fichaje_id)

    assert client.get(ruta).status_code == 405
    assert client.post(ruta, data={"snapshot": snapshot}).status_code == 302
    autenticar(client, usuario)
    assert client.post(ruta, data={"snapshot": snapshot}).status_code == 302
    assert db.session.get(Fichaje, fichaje_id).eliminado is False


def test_post_admin_con_csrf_borra_y_muestra_mensaje(
    client,
    app,
    administrador,
    usuario,
):
    fichaje, _ = crear_fichaje(usuario, registros_variados())
    fichaje_id = fichaje.id
    autenticar(client, administrador)

    respuesta = client.post(
        f"/admin/borrar_fichaje/{fichaje_id}",
        data={"snapshot": snapshot_actual(app, fichaje_id)},
        follow_redirects=True,
    )

    assert respuesta.status_code == 200
    assert "Fichaje eliminado correctamente." in respuesta.get_data(as_text=True)
    assert db.session.get(Fichaje, fichaje_id).eliminado is True


def test_post_sin_csrf_devuelve_400_y_no_borra(
    client,
    app,
    administrador,
    usuario,
):
    fichaje, _ = crear_fichaje(usuario)
    fichaje_id = fichaje.id
    autenticar(client, administrador)

    respuesta = client.post(
        f"/admin/borrar_fichaje/{fichaje_id}",
        data={"snapshot": snapshot_actual(app, fichaje_id)},
        incluir_csrf=False,
    )

    assert respuesta.status_code == 400
    assert db.session.get(Fichaje, fichaje_id).eliminado is False


def test_ruta_fichaje_inexistente_o_id_manipulado(
    client,
    administrador,
):
    autenticar(client, administrador)

    assert client.post(
        "/admin/borrar_fichaje/999999",
        data={"snapshot": "irrelevante"},
    ).status_code == 404
    assert client.post("/admin/borrar_fichaje/-1").status_code == 404
    assert client.post("/admin/borrar_fichaje/abc").status_code == 404


def test_ruta_ya_eliminado_es_idempotente_y_muestra_mensaje(
    client,
    administrador,
    usuario,
):
    fichaje, _ = crear_fichaje(usuario, eliminado=True)
    fichaje_id = fichaje.id
    autenticar(client, administrador)

    respuesta = client.post(
        f"/admin/borrar_fichaje/{fichaje_id}",
        data={"snapshot": "obsoleto"},
        follow_redirects=True,
    )

    assert respuesta.status_code == 200
    assert "El fichaje ya estaba eliminado." in respuesta.get_data(as_text=True)
    assert db.session.get(Fichaje, fichaje_id).eliminado is True


def test_ruta_snapshot_invalido_u_obsoleto_muestra_conflicto(
    client,
    app,
    administrador,
    usuario,
):
    fichaje, _ = crear_fichaje(usuario, registros_variados()[:2])
    fichaje_id = fichaje.id
    snapshot = snapshot_actual(app, fichaje_id)
    db.session.add(
        RegistroHorario(
            fichaje_id=fichaje_id,
            tipo="entrada",
            timestamp=datetime.combine(FECHA, time(16)),
            origen="Tienda",
            eliminado=False,
            creado_por_admin=False,
        )
    )
    db.session.commit()
    autenticar(client, administrador)

    respuesta = client.post(
        f"/admin/borrar_fichaje/{fichaje_id}",
        data={"snapshot": snapshot},
        follow_redirects=True,
    )

    assert respuesta.status_code == 200
    assert "modificado por otra operación" in respuesta.get_data(as_text=True)
    assert db.session.get(Fichaje, fichaje_id).eliminado is False


def test_ruta_ignora_campos_extra_manipulados(
    client,
    app,
    administrador,
    usuario,
):
    fichaje, _ = crear_fichaje(usuario)
    fichaje_id = fichaje.id
    autenticar(client, administrador)

    respuesta = client.post(
        f"/admin/borrar_fichaje/{fichaje_id}",
        data={
            "snapshot": snapshot_actual(app, fichaje_id),
            "usuario_id": str(administrador.id),
            "fecha": "2030-01-01",
            "eliminado": "0",
            "creado_por_admin": "0",
            "origen": "Auto",
            "registros": "999999",
        },
    )

    assert respuesta.status_code == 302
    cabecera = db.session.get(Fichaje, fichaje_id)
    assert cabecera.usuario_id == usuario.id
    assert cabecera.fecha == FECHA
    assert cabecera.creado_por_admin is True
    assert cabecera.eliminado is True


def test_ruta_controla_error_persistencia(
    client,
    administrador,
    usuario,
    monkeypatch,
):
    fichaje, _ = crear_fichaje(usuario)
    fichaje_id = fichaje.id
    autenticar(client, administrador)
    monkeypatch.setattr(
        routes,
        "eliminar_fichaje_administrativo",
        lambda *args, **kwargs: ResultadoBorradoFichajeAdministrativo(
            codigo=ADMIN_BORRADO_ERROR_PERSISTENCIA,
            fichaje_id=fichaje_id,
            usuario_id=usuario.id,
            fecha=FECHA,
        ),
    )

    respuesta = client.post(
        f"/admin/borrar_fichaje/{fichaje_id}",
        data={"snapshot": "irrelevante"},
        follow_redirects=True,
    )

    assert respuesta.status_code == 200
    assert "Error al borrar el fichaje." in respuesta.get_data(as_text=True)
    assert db.session.get(Fichaje, fichaje_id).eliminado is False


def test_vista_incluye_snapshot_y_confirmacion_honesta(
    client,
    administrador,
    usuario,
):
    fichaje, _ = crear_fichaje(usuario, registros_variados())
    autenticar(client, administrador)

    respuesta = client.get(
        f"/admin/fichajes/{usuario.id}?desde={FECHA}&hasta={FECHA}"
    )
    html = respuesta.get_data(as_text=True)
    snapshots = [unescape(value) for value in PATRON_SNAPSHOT.findall(html)]

    assert respuesta.status_code == 200
    assert len(snapshots) == 2
    assert snapshots[0] == snapshots[1]
    assert "eliminar este fichaje del registro activo" in html
    assert "borrar este fichaje y todos sus registros" not in html
    assert f"/admin/borrar_fichaje/{fichaje.id}" in html


def test_ruta_es_delgada_y_no_contiene_escrituras_directas():
    fuente = inspect.getsource(routes.borrar_fichaje_admin)

    for fragmento in (
        "fichaje.eliminado =",
        "Fichaje.eliminado =",
        "RegistroHorario(",
        "Modificacion(",
        "session.add",
        "db.session.add",
        "session.flush",
        "db.session.flush",
        "session.commit",
        "db.session.commit",
        "session.rollback",
        "db.session.rollback",
    ):
        assert fragmento not in fuente
    assert "eliminar_fichaje_administrativo(" in fuente


def test_servicio_no_crea_modificacion(monkeypatch, app, administrador, usuario):
    fichaje, _ = crear_fichaje(usuario)
    fichaje_id = fichaje.id

    def modificacion_prohibida(*args, **kwargs):
        raise AssertionError("El borrado no debe crear Modificacion")

    monkeypatch.setattr(fichajes_service, "Modificacion", modificacion_prohibida)
    resultado = borrar(
        app,
        administrador.id,
        fichaje_id,
        snapshot_actual(app, fichaje_id),
    )

    assert resultado.codigo == ADMIN_BORRADO_ELIMINADO

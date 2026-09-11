from datetime import date, datetime, time
import inspect

import pytest
from sqlalchemy import event
from werkzeug.security import generate_password_hash

from app import db
from app import routes
from app.models import Ausencia, Fichaje, RegistroHorario, Usuario
from app.services.fichajes import (
    ADMIN_ADMINISTRADOR_INEXISTENTE,
    ADMIN_ERROR_PERSISTENCIA,
    ADMIN_FECHA_INVALIDA,
    ADMIN_FICHAJE_CREADO,
    ADMIN_FICHAJE_YA_EXISTENTE,
    ADMIN_FICHAJES_ACTIVOS_MULTIPLES,
    ADMIN_HORAS_INVALIDAS,
    ADMIN_SIN_PERMISOS,
    ADMIN_TRAMO_INVALIDO,
    ADMIN_USUARIO_INEXISTENTE,
    crear_fichaje_administrativo,
)


FECHA_TEXTO = "2024-02-29"
FECHA = date(2024, 2, 29)


def crear_usuario(*, admin=False, sufijo="objetivo"):
    usuario = Usuario(
        nombre=f"Usuario {sufijo}",
        email=f"{sufijo}@example.test",
        password_hash=generate_password_hash("password-correcta"),
        admin=admin,
        puesto="Administracion",
    )
    db.session.add(usuario)
    db.session.commit()
    return usuario


def crear_cabecera(usuario, *, eliminado=False, fecha=FECHA):
    fichaje = Fichaje(
        usuario_id=usuario.id,
        fecha=fecha,
        fecha_creacion=datetime(2024, 2, 29, 7, 0),
        creado_por_admin=False,
        eliminado=eliminado,
    )
    db.session.add(fichaje)
    db.session.commit()
    return fichaje


def crear(admin_id, usuario_id, **cambios):
    datos = {
        "administrador_id": admin_id,
        "usuario_id": usuario_id,
        "fecha": FECHA_TEXTO,
        "hora_entrada": "09:00",
        "hora_salida": "17:00",
    }
    datos.update(cambios)
    return crear_fichaje_administrativo(db.session, **datos)


def autenticar(client, usuario):
    return client.post(
        "/login",
        data={"email": usuario.email, "password": "password-correcta"},
    )


def datos_post(usuario_id, **cambios):
    datos = {
        "usuario_id": str(usuario_id),
        "fecha": FECHA_TEXTO,
        "entrada": "09:00",
        "salida": "17:00",
    }
    datos.update(cambios)
    return datos


def test_servicio_crea_cabecera_y_dos_registros_forzados_con_un_commit(
    administrador,
    usuario,
    monkeypatch,
):
    commit_real = db.session.commit
    commits = []

    def commit_contado():
        commits.append(True)
        return commit_real()

    monkeypatch.setattr(db.session, "commit", commit_contado)
    resultado = crear(administrador.id, usuario.id)

    assert resultado.codigo == ADMIN_FICHAJE_CREADO
    assert resultado.usuario_id == usuario.id
    assert resultado.fecha == FECHA
    assert commits == [True]
    fichaje = db.session.get(Fichaje, resultado.fichaje_id)
    registros = RegistroHorario.query.order_by(RegistroHorario.timestamp).all()
    assert fichaje.creado_por_admin is True
    assert fichaje.eliminado is False
    assert fichaje.fecha == FECHA
    assert [(r.tipo, r.timestamp.time()) for r in registros] == [
        ("entrada", time(9, 0)),
        ("salida", time(17, 0)),
    ]
    assert all(r.creado_por_admin is True for r in registros)
    assert all(r.eliminado is False for r in registros)
    assert [r.origen for r in registros] == ["Tienda", "Tienda"]


def test_servicio_rechaza_administrador_inexistente_sin_escribir(usuario):
    resultado = crear(999999, usuario.id)

    assert resultado.codigo == ADMIN_ADMINISTRADOR_INEXISTENTE
    assert Fichaje.query.count() == 0
    assert RegistroHorario.query.count() == 0


def test_servicio_rechaza_usuario_inexistente_sin_escribir(administrador):
    resultado = crear(administrador.id, 999999)

    assert resultado.codigo == ADMIN_USUARIO_INEXISTENTE
    assert Fichaje.query.count() == 0


def test_servicio_revalida_privilegios_del_llamador(usuario):
    objetivo = crear_usuario(sufijo="sin-permisos-objetivo")

    resultado = crear(usuario.id, objetivo.id)

    assert resultado.codigo == ADMIN_SIN_PERMISOS
    assert Fichaje.query.count() == 0


@pytest.mark.parametrize(
    "valor",
    [
        None,
        "",
        "2024-2-29",
        "2024-02-30",
        "29/02/2024",
        "2024-02-29T09:00",
        date(2024, 2, 29),
        datetime(2024, 2, 29, 9, 0),
    ],
)
def test_servicio_rechaza_fechas_invalidas_o_fuera_del_contrato(
    administrador,
    usuario,
    valor,
):
    resultado = crear(administrador.id, usuario.id, fecha=valor)

    assert resultado.codigo == ADMIN_FECHA_INVALIDA
    assert Fichaje.query.count() == 0


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("hora_entrada", None),
        ("hora_entrada", ""),
        ("hora_entrada", "9:00"),
        ("hora_entrada", "09:00:00"),
        ("hora_entrada", "24:00"),
        ("hora_salida", "17:60"),
        ("hora_salida", time(17, 0)),
        ("hora_salida", "2024-02-29T17:00"),
    ],
)
def test_servicio_rechaza_horas_invalidas_o_fuera_del_contrato(
    administrador,
    usuario,
    campo,
    valor,
):
    resultado = crear(administrador.id, usuario.id, **{campo: valor})

    assert resultado.codigo == ADMIN_HORAS_INVALIDAS
    assert Fichaje.query.count() == 0


@pytest.mark.parametrize(
    ("entrada", "salida"),
    [("09:00", "09:00"), ("17:00", "09:00")],
)
def test_servicio_rechaza_tramo_nulo_o_invertido(
    administrador,
    usuario,
    entrada,
    salida,
):
    resultado = crear(
        administrador.id,
        usuario.id,
        hora_entrada=entrada,
        hora_salida=salida,
    )

    assert resultado.codigo == ADMIN_TRAMO_INVALIDO
    assert Fichaje.query.count() == 0


@pytest.mark.parametrize(
    ("administrador_id", "usuario_id", "codigo"),
    [
        (None, 1, ADMIN_ADMINISTRADOR_INEXISTENTE),
        (True, 1, ADMIN_ADMINISTRADOR_INEXISTENTE),
        ("1", 1, ADMIN_ADMINISTRADOR_INEXISTENTE),
        (1, None, ADMIN_USUARIO_INEXISTENTE),
        (1, False, ADMIN_USUARIO_INEXISTENTE),
        (1, "1", ADMIN_USUARIO_INEXISTENTE),
        (1, 0, ADMIN_USUARIO_INEXISTENTE),
    ],
)
def test_servicio_rechaza_identificadores_fuera_del_contrato(
    app,
    administrador_id,
    usuario_id,
    codigo,
):
    resultado = crear(administrador_id, usuario_id)

    assert resultado.codigo == codigo
    assert Fichaje.query.count() == 0


def test_duplicado_activo_devuelve_el_id_exacto(administrador, usuario):
    existente = crear_cabecera(usuario)

    resultado = crear(administrador.id, usuario.id)

    assert resultado.codigo == ADMIN_FICHAJE_YA_EXISTENTE
    assert resultado.fichaje_id == existente.id
    assert Fichaje.query.count() == 1


def test_varias_cabeceras_activas_se_tratan_como_anomalia(administrador, usuario):
    primero = crear_cabecera(usuario)
    segundo = Fichaje(
        usuario_id=usuario.id,
        fecha=FECHA,
        fecha_creacion=datetime(2024, 2, 29, 8, 0),
        creado_por_admin=False,
        eliminado=False,
    )
    db.session.add(segundo)
    db.session.commit()

    resultado = crear(administrador.id, usuario.id)

    assert resultado.codigo == ADMIN_FICHAJES_ACTIVOS_MULTIPLES
    assert resultado.fichaje_id is None
    assert {f.id for f in Fichaje.query.all()} == {primero.id, segundo.id}


def test_cabecera_eliminada_no_se_reutiliza_y_permite_una_nueva(
    administrador,
    usuario,
):
    eliminada = crear_cabecera(usuario, eliminado=True)
    registro_eliminado = RegistroHorario(
        fichaje_id=eliminada.id,
        tipo="entrada",
        timestamp=datetime(2024, 2, 29, 8, 0),
        creado_por_admin=False,
        eliminado=True,
        origen="Remoto",
    )
    db.session.add(registro_eliminado)
    db.session.commit()

    resultado = crear(administrador.id, usuario.id)

    assert resultado.codigo == ADMIN_FICHAJE_CREADO
    assert resultado.fichaje_id != eliminada.id
    assert db.session.get(Fichaje, eliminada.id).eliminado is True
    conservado = db.session.get(RegistroHorario, registro_eliminado.id)
    assert conservado.eliminado is True
    assert conservado.origen == "Remoto"
    assert Fichaje.query.count() == 2


def test_cabecera_eliminada_y_activa_devuelve_solo_la_activa(
    administrador,
    usuario,
):
    eliminada = crear_cabecera(usuario, eliminado=True)
    activa = Fichaje(
        usuario_id=usuario.id,
        fecha=FECHA,
        fecha_creacion=datetime(2024, 2, 29, 8, 0),
        creado_por_admin=False,
        eliminado=False,
    )
    db.session.add(activa)
    db.session.commit()

    resultado = crear(administrador.id, usuario.id)

    assert resultado.codigo == ADMIN_FICHAJE_YA_EXISTENTE
    assert resultado.fichaje_id == activa.id
    assert db.session.get(Fichaje, eliminada.id).eliminado is True


@pytest.mark.parametrize("tipo", ["Medico", "Vacaciones"])
def test_ausencias_medicas_y_bloqueantes_no_se_modifican_ni_impiden_el_alta(
    administrador,
    usuario,
    tipo,
):
    ausencia = Ausencia(
        usuario_id=usuario.id,
        fecha=FECHA,
        tipo=tipo,
        observaciones="Conservar",
        creado_por_admin=False,
    )
    db.session.add(ausencia)
    db.session.commit()

    resultado = crear(administrador.id, usuario.id)

    assert resultado.codigo == ADMIN_FICHAJE_CREADO
    conservada = db.session.get(Ausencia, ausencia.id)
    assert conservada.tipo == tipo
    assert conservada.observaciones == "Conservar"
    assert Ausencia.query.count() == 1


def test_fallo_al_anadir_cabecera_hace_rollback_total(
    administrador,
    usuario,
    monkeypatch,
):
    add_real = db.session.add

    def add_con_fallo(objeto, *args, **kwargs):
        if isinstance(objeto, Fichaje):
            raise RuntimeError("fallo controlado cabecera")
        return add_real(objeto, *args, **kwargs)

    monkeypatch.setattr(db.session, "add", add_con_fallo)
    resultado = crear(administrador.id, usuario.id)

    assert resultado.codigo == ADMIN_ERROR_PERSISTENCIA
    assert Fichaje.query.count() == 0
    assert RegistroHorario.query.count() == 0
    assert db.session.is_active


def test_fallo_del_flush_de_cabecera_hace_rollback_total(
    administrador,
    usuario,
    monkeypatch,
):
    def flush_con_fallo(*_args, **_kwargs):
        raise RuntimeError("fallo controlado flush cabecera")

    monkeypatch.setattr(db.session, "flush", flush_con_fallo)
    resultado = crear(administrador.id, usuario.id)

    assert resultado.codigo == ADMIN_ERROR_PERSISTENCIA
    assert Fichaje.query.count() == 0
    assert RegistroHorario.query.count() == 0
    assert db.session.is_active


@pytest.mark.parametrize("tipo_fallido", ["entrada", "salida"])
def test_fallo_al_persistir_cada_registro_hace_rollback_total(
    administrador,
    usuario,
    tipo_fallido,
):
    def fallar_registro(_mapper, _connection, target):
        if target.tipo == tipo_fallido:
            raise RuntimeError(f"fallo controlado {tipo_fallido}")

    event.listen(RegistroHorario, "before_insert", fallar_registro)
    try:
        resultado = crear(administrador.id, usuario.id)
    finally:
        event.remove(RegistroHorario, "before_insert", fallar_registro)

    assert resultado.codigo == ADMIN_ERROR_PERSISTENCIA
    assert Fichaje.query.count() == 0
    assert RegistroHorario.query.count() == 0
    assert db.session.is_active


def test_fallo_de_commit_hace_rollback_y_la_sesion_admite_reintento(
    administrador,
    usuario,
    monkeypatch,
):
    commit_real = db.session.commit

    with monkeypatch.context() as contexto:
        contexto.setattr(
            db.session,
            "commit",
            lambda: (_ for _ in ()).throw(RuntimeError("fallo commit")),
        )
        fallido = crear(administrador.id, usuario.id)

    assert fallido.codigo == ADMIN_ERROR_PERSISTENCIA
    assert Fichaje.query.count() == 0
    assert RegistroHorario.query.count() == 0
    assert db.session.is_active

    monkeypatch.setattr(db.session, "commit", commit_real)
    reintento = crear(administrador.id, usuario.id)
    assert reintento.codigo == ADMIN_FICHAJE_CREADO
    assert Fichaje.query.count() == 1
    assert RegistroHorario.query.count() == 2


def test_campos_de_trazabilidad_no_forman_parte_de_la_firma_publica(
    administrador,
    usuario,
):
    with pytest.raises(TypeError):
        crear_fichaje_administrativo(
            db.session,
            administrador_id=administrador.id,
            usuario_id=usuario.id,
            fecha=FECHA_TEXTO,
            hora_entrada="09:00",
            hora_salida="17:00",
            origen="Remoto",
            eliminado=True,
            creado_por_admin=False,
        )


def test_get_de_creacion_es_accesible_para_admin_y_preselecciona_usuario(
    client,
    administrador,
    usuario,
):
    autenticar(client, administrador)

    response = client.get(f"/admin/crear-fichaje/{usuario.id}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert f'value="{usuario.id}" selected' in html


def test_get_de_creacion_deniega_a_empleado(client, usuario):
    autenticar(client, usuario)

    response = client.get("/admin/crear-fichaje")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/fichar")


def test_post_valido_redirige_al_historial_y_persiste(client, administrador, usuario):
    autenticar(client, administrador)

    response = client.post(
        f"/admin/crear-fichaje/{usuario.id}",
        data=datos_post(usuario.id),
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/admin/fichajes/{usuario.id}")
    assert Fichaje.query.filter_by(usuario_id=usuario.id).count() == 1
    assert RegistroHorario.query.count() == 2


def test_post_sin_csrf_se_rechaza_antes_de_escribir(client, administrador, usuario):
    autenticar(client, administrador)

    response = client.post(
        "/admin/crear-fichaje",
        data=datos_post(usuario.id),
        incluir_csrf=False,
    )

    assert response.status_code == 400
    assert Fichaje.query.count() == 0


def test_ruta_duplicada_redirige_a_edicion_del_activo_exacto(
    client,
    administrador,
    usuario,
):
    existente = crear_cabecera(usuario)
    autenticar(client, administrador)

    response = client.post(
        "/admin/crear-fichaje",
        data=datos_post(usuario.id),
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/admin/editar_fichaje/{existente.id}"
    )
    assert Fichaje.query.count() == 1


def test_ruta_trata_varias_activas_sin_escoger_una_arbitrariamente(
    client,
    administrador,
    usuario,
):
    crear_cabecera(usuario)
    db.session.add(
        Fichaje(
            usuario_id=usuario.id,
            fecha=FECHA,
            fecha_creacion=datetime(2024, 2, 29, 8, 0),
            creado_por_admin=False,
            eliminado=False,
        )
    )
    db.session.commit()
    autenticar(client, administrador)

    response = client.post(
        "/admin/crear-fichaje",
        data=datos_post(usuario.id),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "varios fichajes activos" in response.get_data(as_text=True)
    assert Fichaje.query.count() == 2


@pytest.mark.parametrize(
    "usuario_id",
    ["", "abc", "0", "-1", "1.5", " 1", "+1", "１"],
)
def test_ruta_controla_identificador_manipulado(
    client,
    administrador,
    usuario_id,
):
    autenticar(client, administrador)

    response = client.post(
        "/admin/crear-fichaje",
        data=datos_post(usuario_id),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "usuario seleccionado no existe" in response.get_data(as_text=True)
    assert Fichaje.query.count() == 0


def test_ruta_controla_usuario_numerico_inexistente(client, administrador):
    autenticar(client, administrador)

    response = client.post(
        "/admin/crear-fichaje",
        data=datos_post(999999),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "usuario seleccionado no existe" in response.get_data(as_text=True)
    assert Fichaje.query.count() == 0


@pytest.mark.parametrize(
    "cambios",
    [
        {"fecha": ""},
        {"fecha": "2024-02-30"},
        {"entrada": ""},
        {"salida": "17:00:00"},
        {"entrada": "09:00", "salida": "09:00"},
        {"entrada": "18:00", "salida": "17:00"},
    ],
)
def test_ruta_controla_fecha_horas_y_orden_invalidos(
    client,
    administrador,
    usuario,
    cambios,
):
    autenticar(client, administrador)

    response = client.post(
        "/admin/crear-fichaje",
        data=datos_post(usuario.id, **cambios),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert Fichaje.query.count() == 0
    assert RegistroHorario.query.count() == 0


def test_ruta_ignora_campos_extra_y_fuerza_trazabilidad(
    client,
    administrador,
    usuario,
):
    autenticar(client, administrador)
    datos = datos_post(
        usuario.id,
        origen="Remoto",
        eliminado="1",
        creado_por_admin="0",
        fichaje_id="777",
        tipo="pausa",
    )

    response = client.post("/admin/crear-fichaje", data=datos)

    assert response.status_code == 302
    fichaje = Fichaje.query.one()
    registros = RegistroHorario.query.order_by(RegistroHorario.id).all()
    assert fichaje.creado_por_admin is True
    assert fichaje.eliminado is False
    assert all(r.creado_por_admin is True for r in registros)
    assert all(r.eliminado is False for r in registros)
    assert [r.origen for r in registros] == ["Tienda", "Tienda"]
    assert [r.tipo for r in registros] == ["entrada", "salida"]


def test_ruta_controla_fallo_de_persistencia_sin_dejar_datos(
    client,
    administrador,
    usuario,
):
    autenticar(client, administrador)

    def fallar_salida(_mapper, _connection, target):
        if target.tipo == "salida":
            raise RuntimeError("fallo controlado salida")

    event.listen(RegistroHorario, "before_insert", fallar_salida)
    try:
        response = client.post(
            "/admin/crear-fichaje",
            data=datos_post(usuario.id),
            follow_redirects=True,
        )
    finally:
        event.remove(RegistroHorario, "before_insert", fallar_salida)

    assert response.status_code == 200
    assert "Error al crear el fichaje" in response.get_data(as_text=True)
    assert Fichaje.query.count() == 0
    assert RegistroHorario.query.count() == 0


def test_ruta_no_contiene_escrituras_directas_de_la_creacion_administrativa():
    fuente = inspect.getsource(routes.crear_fichaje_admin)

    for fragmento in (
        "Fichaje(",
        "RegistroHorario(",
        "db.session.add(",
        "db.session.add_all(",
        "db.session.flush(",
        "db.session.commit(",
        "db.session.rollback(",
    ):
        assert fragmento not in fuente
    assert "crear_fichaje_administrativo(" in fuente

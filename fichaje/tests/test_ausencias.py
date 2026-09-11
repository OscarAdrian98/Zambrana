from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest
from flask import current_app
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from app import db
from app.models import Ausencia, Fichaje, RegistroHorario, Usuario
from app.services.ausencias import (
    DatosAusencia,
    ErrorValidacionAusencia,
    TIPO_ASUNTOS_PROPIOS,
    TIPO_BAJA,
    TIPO_ENFERMEDAD,
    TIPO_MEDICO,
    TIPO_VACACIONES,
    agrupar_ausencias,
    ausencia_bloquea_fichaje,
    ausencia_cubre_fecha,
    buscar_duplicados_exactos,
    calcular_dias_consumidos,
    calcular_saldo_vacaciones,
    crear_snapshot_ausencia_firmado,
    es_ausencia_medica,
    fecha_hoy_madrid,
    fechas_intervalo,
    normalizar_observaciones,
    normalizar_tipo_ausencia,
    parsear_ids_ausencias,
    preparar_datos_ausencia,
    puede_gestionar_ausencia,
    seleccionar_ausencia_bloqueante,
    validar_fechas,
    validar_horas_medicas,
)


FECHA_FUTURA = date(2099, 6, 15)


def login(client, usuario):
    return client.post(
        "/login",
        data={
            "email": usuario.email,
            "password": "password-correcta",
        },
    )


def crear_otro_usuario(email="otro@example.test", admin=False):
    usuario = Usuario(
        nombre="Otro usuario ficticio",
        email=email,
        password_hash=generate_password_hash("password-correcta"),
        admin=admin,
        puesto="Administración",
    )
    db.session.add(usuario)
    db.session.commit()
    return usuario


def crear_ausencia(
    usuario,
    fecha=FECHA_FUTURA,
    tipo=TIPO_VACACIONES,
    observaciones="Texto ficticio neutro",
    creado_por_admin=False,
    hora_desde=None,
    hora_hasta=None,
):
    ausencia = Ausencia(
        usuario_id=usuario.id,
        fecha=fecha,
        tipo=tipo,
        observaciones=observaciones,
        creado_por_admin=creado_por_admin,
        hora_desde=hora_desde,
        hora_hasta=hora_hasta,
    )
    db.session.add(ausencia)
    db.session.commit()
    return ausencia


def snapshot_ausencia(usuario, *ausencias):
    return crear_snapshot_ausencia_firmado(
        usuario.id,
        ausencias,
        current_app.config["SECRET_KEY"],
    )


def datos_formulario(**cambios):
    datos = {
        "fecha_desde": FECHA_FUTURA.isoformat(),
        "fecha_hasta": FECHA_FUTURA.isoformat(),
        "tipo": TIPO_VACACIONES,
        "observaciones": "  Texto ficticio neutro  ",
        "hora_desde": "",
        "hora_hasta": "",
    }
    datos.update(cambios)
    return datos


def fila_simple(
    identificador,
    fecha,
    tipo=TIPO_VACACIONES,
    observaciones=None,
    hora_desde=None,
    hora_hasta=None,
    creado_por_admin=False,
    usuario_id=1,
):
    return SimpleNamespace(
        id=identificador,
        usuario_id=usuario_id,
        fecha=fecha,
        tipo=tipo,
        observaciones=observaciones,
        hora_desde=hora_desde,
        hora_hasta=hora_hasta,
        creado_por_admin=creado_por_admin,
    )


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Vacaciones", TIPO_VACACIONES),
        ("enfermedad", TIPO_ENFERMEDAD),
        (" ASUNTOS PROPIOS ", TIPO_ASUNTOS_PROPIOS),
        ("bAjA", TIPO_BAJA),
        ("Medico", TIPO_MEDICO),
        ("Médico", TIPO_MEDICO),
        ("mÉdIcO", TIPO_MEDICO),
    ],
)
def test_normaliza_tipos_validos_aliases_y_espacios(entrada, esperado):
    assert normalizar_tipo_ausencia(entrada) == esperado


@pytest.mark.parametrize(
    "entrada",
    ["", "Teletrabajo", "Vacaciones\x00", "x" * 51, None, ["Vacaciones"]],
)
def test_rechaza_tipo_vacio_invalido_largo_o_manipulado(entrada):
    with pytest.raises(ErrorValidacionAusencia):
        normalizar_tipo_ausencia(entrada)


@pytest.mark.parametrize("entrada", ["Medico", "Médico", "MEDICO", " médico "])
def test_detecta_ausencia_medica_tolerando_aliases(entrada):
    assert es_ausencia_medica(entrada) is True
    assert ausencia_bloquea_fichaje(fila_simple(1, date.today(), entrada)) is False


@pytest.mark.parametrize(
    "tipo",
    [TIPO_VACACIONES, TIPO_ENFERMEDAD, TIPO_ASUNTOS_PROPIOS, TIPO_BAJA],
)
def test_tipos_ordinarios_bloquean_fichaje(tipo):
    assert ausencia_bloquea_fichaje(fila_simple(1, date.today(), tipo)) is True


def test_ausencia_inexistente_no_bloquea():
    assert ausencia_bloquea_fichaje(None) is False


@pytest.mark.parametrize(
    ("desde", "hasta", "esperado"),
    [
        ("2026-07-20", "2026-07-20", (date(2026, 7, 20), date(2026, 7, 20))),
        ("2026-07-31", "2026-08-01", (date(2026, 7, 31), date(2026, 8, 1))),
        ("2026-12-31", "2027-01-01", (date(2026, 12, 31), date(2027, 1, 1))),
        ("2028-02-29", "2028-03-01", (date(2028, 2, 29), date(2028, 3, 1))),
    ],
)
def test_valida_fechas_y_cambios_de_periodo(desde, hasta, esperado):
    assert validar_fechas(desde, hasta) == esperado


@pytest.mark.parametrize(
    ("desde", "hasta"),
    [
        ("", "2026-07-20"),
        ("2026-07-20", ""),
        ("20/07/2026", "2026-07-20"),
        ("2026-02-30", "2026-03-01"),
        ("2026-07-200", "2026-07-20"),
        ("2026-07-21", "2026-07-20"),
        (["2026-07-20"], "2026-07-20"),
    ],
)
def test_rechaza_fechas_invalidas_imposibles_o_manipuladas(desde, hasta):
    with pytest.raises(ErrorValidacionAusencia):
        validar_fechas(desde, hasta)


def test_rango_de_un_dia_es_inclusivo():
    assert fechas_intervalo(date(2026, 7, 20), date(2026, 7, 20)) == (
        date(2026, 7, 20),
    )
    assert calcular_dias_consumidos(date(2026, 7, 20), date(2026, 7, 20)) == 1


@pytest.mark.parametrize(
    ("desde", "hasta", "dias"),
    [
        (date(2026, 7, 19), date(2026, 7, 19), 1),  # domingo
        (date(2026, 7, 25), date(2026, 7, 25), 1),  # sábado
        (date(2026, 8, 1), date(2026, 8, 1), 1),  # sábado de agosto
        (date(2026, 7, 24), date(2026, 7, 27), 4),  # fin de semana
        (date(2026, 12, 31), date(2027, 1, 2), 3),  # cambio de año
        (date(2028, 2, 28), date(2028, 3, 1), 3),  # bisiesto
    ],
)
def test_calculo_preserva_todos_los_dias_naturales(desde, hasta, dias):
    assert calcular_dias_consumidos(desde, hasta) == dias
    assert len(fechas_intervalo(desde, hasta)) == dias


def test_calculo_rechaza_intervalo_invertido():
    with pytest.raises(ErrorValidacionAusencia):
        calcular_dias_consumidos(date(2026, 7, 21), date(2026, 7, 20))


def test_ausencia_cubre_solo_su_fecha_almacenada():
    ausencia = fila_simple(1, date(2026, 7, 20))
    assert ausencia_cubre_fecha(ausencia, date(2026, 7, 20)) is True
    assert ausencia_cubre_fecha(ausencia, date(2026, 7, 21)) is False


def test_horas_medicas_validas_y_sin_segundos():
    desde, hasta = validar_horas_medicas(TIPO_MEDICO, "09:30", "10:45")
    assert desde == time(9, 30)
    assert hasta == time(10, 45)
    assert desde.second == hasta.second == 0


@pytest.mark.parametrize(
    ("desde", "hasta"),
    [
        ("9:30", "10:45"),
        ("09:60", "10:45"),
        ("09:30", "10:99"),
        ("09:30", ""),
        ("", "10:45"),
        ("10:45", "09:30"),
        ("10:45", "10:45"),
        (["09:30"], "10:45"),
    ],
)
def test_rechaza_horas_medicas_invalidas_incompletas_o_invertidas(desde, hasta):
    with pytest.raises(ErrorValidacionAusencia):
        validar_horas_medicas(TIPO_MEDICO, desde, hasta)


def test_cita_medica_sin_horas_sigue_permitida():
    assert validar_horas_medicas(TIPO_MEDICO, "", "") == (None, None)


def test_tipo_no_medico_limpia_horas_en_backend():
    assert validar_horas_medicas(TIPO_VACACIONES, "09:00", "10:00") == (
        None,
        None,
    )


def test_preparacion_canoniza_y_limpia_texto():
    datos = preparar_datos_ausencia(
        datos_formulario(tipo="  MÉDICO ", observaciones="  cita ficticia  ")
    )
    assert datos.tipo == TIPO_MEDICO
    assert datos.observaciones == "cita ficticia"


@pytest.mark.parametrize(
    "observaciones",
    ["x" * 256, "texto\x00oculto", "línea\nsegunda"],
)
def test_observaciones_rechazan_longitud_y_controles(observaciones):
    with pytest.raises(ErrorValidacionAusencia):
        normalizar_observaciones(observaciones)


def test_observaciones_vacias_se_guardan_como_nulo():
    assert normalizar_observaciones("   ") is None


def test_ids_validos_se_deduplican_preservando_orden():
    assert parsear_ids_ausencias("3,1,3,2") == (3, 1, 2)


@pytest.mark.parametrize("valor", ["", "0", "-1", "1, 2", "abc", "1;2", None])
def test_ids_manipulados_se_rechazan(valor):
    with pytest.raises(ErrorValidacionAusencia):
        parsear_ids_ausencias(valor)


def test_permiso_central_acepta_propietario_o_admin():
    ausencia = fila_simple(1, FECHA_FUTURA, usuario_id=10)
    assert puede_gestionar_ausencia(SimpleNamespace(id=10, admin=False), ausencia)
    assert puede_gestionar_ausencia(SimpleNamespace(id=99, admin=True), ausencia)
    assert not puede_gestionar_ausencia(
        SimpleNamespace(id=99, admin=False),
        ausencia,
    )


def test_duplicado_exacto_considera_alias_y_excluye_la_propia_fila():
    datos = DatosAusencia(
        fecha_desde=FECHA_FUTURA,
        fecha_hasta=FECHA_FUTURA,
        tipo=TIPO_MEDICO,
        observaciones="Neutro",
        hora_desde=time(9),
        hora_hasta=time(10),
    )
    existente = fila_simple(
        7,
        FECHA_FUTURA,
        tipo="Médico",
        observaciones="Neutro",
        hora_desde=time(9),
        hora_hasta=time(10),
    )
    assert buscar_duplicados_exactos([existente], datos) == [existente]
    assert buscar_duplicados_exactos([existente], datos, excluir_ids=(7,)) == []


def test_solapamiento_no_identico_se_conserva():
    datos = DatosAusencia(
        fecha_desde=FECHA_FUTURA,
        fecha_hasta=FECHA_FUTURA,
        tipo=TIPO_ENFERMEDAD,
        observaciones=None,
        hora_desde=None,
        hora_hasta=None,
    )
    existente = fila_simple(1, FECHA_FUTURA, tipo=TIPO_VACACIONES)
    assert buscar_duplicados_exactos([existente], datos) == []


def test_varias_ausencias_eligen_primer_bloqueo_por_id():
    filas = [
        fila_simple(1, date.today(), tipo="Médico"),
        fila_simple(3, date.today(), tipo=TIPO_ENFERMEDAD),
        fila_simple(2, date.today(), tipo=TIPO_VACACIONES),
    ]
    assert seleccionar_ausencia_bloqueante(filas).id == 2


def test_agrupacion_preserva_tramos_y_aliases_historicos():
    hoy = date(2026, 7, 20)
    filas = [
        fila_simple(1, date(2026, 7, 21), tipo="Médico"),
        fila_simple(2, date(2026, 7, 22), tipo="medico"),
        fila_simple(3, date(2026, 7, 24), tipo="Medico"),
    ]
    bloques = agrupar_ausencias(filas, hoy)
    assert [(b["fecha"], b["fecha_hasta"], b["dias"]) for b in bloques] == [
        (date(2026, 7, 24), date(2026, 7, 24), 1),
        (date(2026, 7, 21), date(2026, 7, 22), 2),
    ]
    assert all(b["tipo"] == TIPO_MEDICO for b in bloques)


def test_saldo_preserva_regla_actual_y_medico_no_descuenta():
    hoy = date(2026, 7, 20)
    filas = [
        fila_simple(1, date(2026, 7, 1)),
        fila_simple(2, date(2026, 7, 2)),
        fila_simple(3, date(2026, 8, 1)),
        fila_simple(4, date(2026, 8, 2)),
        fila_simple(5, date(2026, 7, 20), tipo=TIPO_MEDICO),
    ]
    assert calcular_saldo_vacaciones(filas, hoy) == {
        "saldo_utilizado": 2,
        "saldo_solicitado": 2,
        "saldo_disponible": 26,
    }


def test_tramo_de_vacaciones_que_cruza_hoy_no_cambia_regla_historica():
    hoy = date(2026, 7, 20)
    filas = [
        fila_simple(1, date(2026, 7, 19)),
        fila_simple(2, date(2026, 7, 20)),
        fila_simple(3, date(2026, 7, 21)),
    ]
    saldo = calcular_saldo_vacaciones(filas, hoy)
    assert saldo["saldo_utilizado"] == 0
    assert saldo["saldo_solicitado"] == 0
    assert saldo["saldo_disponible"] == 30


def test_fecha_madrid_resuelve_cambio_de_dia_desde_utc():
    instante_utc = datetime(2026, 1, 1, 23, 30, tzinfo=timezone.utc)
    assert fecha_hoy_madrid(instante_utc) == date(2026, 1, 2)


def test_fecha_madrid_rechaza_datetime_naive():
    with pytest.raises(ValueError):
        fecha_hoy_madrid(datetime(2026, 1, 1, 23, 30))


def test_usuario_lista_solo_sus_ausencias_y_texto_se_escapa(client, usuario):
    otro = crear_otro_usuario()
    crear_ausencia(usuario, observaciones="<script>propio</script>")
    crear_ausencia(
        otro,
        fecha=FECHA_FUTURA + timedelta(days=1),
        observaciones="MARCADOR_AJENO",
    )
    login(client, usuario)

    html = client.get(
        "/mis-ausencias",
        query_string={"desde": "2099-01-01", "hasta": "2099-12-31"},
    ).get_data(as_text=True)

    assert "&lt;script&gt;propio&lt;/script&gt;" in html
    assert "<script>propio</script>" not in html
    assert "MARCADOR_AJENO" not in html


def test_creacion_empleado_normaliza_y_ignora_usuario_id(client, usuario):
    otro = crear_otro_usuario()
    login(client, usuario)

    response = client.post(
        "/mis-ausencias",
        data=datos_formulario(
            tipo="  vAcAcIoNeS ",
            observaciones="  Neutro  ",
            usuario_id=str(otro.id),
            hora_desde="09:00",
            hora_hasta="10:00",
        ),
    )

    assert response.status_code == 302
    ausencia = Ausencia.query.one()
    assert ausencia.usuario_id == usuario.id
    assert ausencia.tipo == TIPO_VACACIONES
    assert ausencia.observaciones == "Neutro"
    assert ausencia.hora_desde is None
    assert ausencia.hora_hasta is None


def test_creacion_de_rango_genera_todas_las_fechas_en_un_commit(client, usuario):
    login(client, usuario)
    client.post(
        "/mis-ausencias",
        data=datos_formulario(
            fecha_desde="2099-06-15",
            fecha_hasta="2099-06-17",
        ),
    )
    assert [a.fecha for a in Ausencia.query.order_by(Ausencia.fecha)] == [
        date(2099, 6, 15),
        date(2099, 6, 16),
        date(2099, 6, 17),
    ]


@pytest.mark.parametrize(
    "cambio",
    [
        {"tipo": "No existe"},
        {"fecha_desde": "2099-02-30"},
        {"fecha_hasta": "2099-06-14"},
        {"hora_desde": "09:00", "tipo": TIPO_MEDICO},
        {"observaciones": "x" * 256},
    ],
)
def test_creacion_invalida_no_deja_filas(client, usuario, cambio):
    login(client, usuario)
    response = client.post(
        "/mis-ausencias",
        data=datos_formulario(**cambio),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert Ausencia.query.count() == 0
    assert "Traceback" not in response.get_data(as_text=True)


def test_duplicado_exacto_se_rechaza_sin_impedir_otro_tipo(client, usuario):
    crear_ausencia(usuario, observaciones="Neutro")
    login(client, usuario)
    client.post(
        "/mis-ausencias",
        data=datos_formulario(observaciones="Neutro"),
    )
    assert Ausencia.query.count() == 1

    client.post(
        "/mis-ausencias",
        data=datos_formulario(
            tipo=TIPO_ENFERMEDAD,
            observaciones="Neutro",
        ),
    )
    assert Ausencia.query.count() == 2


def test_fallo_commit_creacion_hace_rollback_y_no_deja_objeto(
    client,
    usuario,
    monkeypatch,
):
    login(client, usuario)

    def commit_con_error():
        raise RuntimeError("fallo controlado")

    monkeypatch.setattr(db.session, "commit", commit_con_error)
    response = client.post("/mis-ausencias", data=datos_formulario())

    assert response.status_code == 302
    assert Ausencia.query.count() == 0
    assert db.session.is_active


def test_edicion_propia_valida_y_no_cambia_propietario(client, usuario):
    otro = crear_otro_usuario()
    ausencia = crear_ausencia(usuario, tipo=TIPO_MEDICO)
    login(client, usuario)

    response = client.post(
        "/mis-ausencias",
        data=datos_formulario(
            editar_snapshot=snapshot_ausencia(usuario, ausencia),
            tipo=TIPO_ENFERMEDAD,
            observaciones="  Editado  ",
            usuario_id=str(otro.id),
            hora_desde="09:00",
            hora_hasta="10:00",
        ),
    )

    assert response.status_code == 302
    editada = Ausencia.query.one()
    assert editada.usuario_id == usuario.id
    assert editada.tipo == TIPO_ENFERMEDAD
    assert editada.observaciones == "Editado"
    assert editada.hora_desde is None
    assert editada.hora_hasta is None


def test_edicion_no_se_considera_duplicado_consigo_misma(client, usuario):
    ausencia = crear_ausencia(usuario)
    login(client, usuario)
    client.post(
        "/mis-ausencias",
        data=datos_formulario(
            editar_snapshot=snapshot_ausencia(usuario, ausencia),
            observaciones=ausencia.observaciones,
        ),
    )
    assert Ausencia.query.count() == 1


def test_preparar_edicion_carga_valores_y_ids_verificados(client, usuario):
    ausencia = crear_ausencia(
        usuario,
        tipo=TIPO_MEDICO,
        hora_desde=time(9),
        hora_hasta=time(10),
    )
    login(client, usuario)

    response = client.post(
        "/editar-ausencia",
        data={"snapshot": snapshot_ausencia(usuario, ausencia)},
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)
    assert 'name="editar_snapshot"' in html
    assert 'value="09:00"' in html
    assert 'value="10:00"' in html


def test_editar_ausencia_ajena_no_filtra_datos_ni_modifica(client, usuario):
    otro = crear_otro_usuario()
    ausencia = crear_ausencia(otro)
    login(client, usuario)
    response = client.post(
        "/editar-ausencia",
        data={"snapshot": snapshot_ausencia(otro, ausencia)},
    )
    assert response.status_code == 404
    assert db.session.get(Ausencia, ausencia.id) is not None


@pytest.mark.parametrize("valor", ["", "snapshot-invalido", "alterado.firma"])
def test_editar_snapshot_inexistente_o_manipulado_devuelve_404(
    client,
    usuario,
    valor,
):
    login(client, usuario)
    response = client.post(
        "/editar-ausencia",
        data={"snapshot": valor},
    )
    assert response.status_code == 404


def test_empleado_no_edita_ausencia_pasada_o_creada_por_admin(client, usuario):
    pasada = crear_ausencia(
        usuario,
        fecha=date(2000, 1, 1),
        observaciones="Pasada",
    )
    administrativa = crear_ausencia(
        usuario,
        fecha=FECHA_FUTURA + timedelta(days=1),
        observaciones="Administrativa",
        creado_por_admin=True,
    )
    login(client, usuario)
    for ausencia in (pasada, administrativa):
        response = client.post(
            "/editar-ausencia",
            data={"snapshot": snapshot_ausencia(usuario, ausencia)},
        )
        assert response.status_code == 403


def test_fallo_commit_edicion_restaura_valores_reales(
    client,
    usuario,
    monkeypatch,
):
    ausencia = crear_ausencia(usuario, observaciones="Original")
    ausencia_id = ausencia.id
    login(client, usuario)

    def commit_con_error():
        raise RuntimeError("fallo controlado")

    monkeypatch.setattr(db.session, "commit", commit_con_error)
    client.post(
        "/mis-ausencias",
        data=datos_formulario(
            editar_snapshot=snapshot_ausencia(usuario, ausencia),
            tipo=TIPO_BAJA,
            observaciones="Cambiado",
        ),
    )
    db.session.expire_all()
    original = db.session.get(Ausencia, ausencia_id)
    assert original is not None
    assert original.tipo == TIPO_VACACIONES
    assert original.observaciones == "Original"
    assert Ausencia.query.count() == 1


def test_borrado_propio_es_post_fisico(client, usuario):
    ausencia = crear_ausencia(usuario)
    login(client, usuario)
    response = client.post(
        "/eliminar-ausencia",
        data={"snapshot": snapshot_ausencia(usuario, ausencia)},
    )
    assert response.status_code == 302
    assert Ausencia.query.count() == 0


def test_borrado_get_no_existe_y_no_elimina(client, usuario):
    ausencia = crear_ausencia(usuario)
    login(client, usuario)
    response = client.get(
        "/eliminar-ausencia",
        query_string={"snapshot": snapshot_ausencia(usuario, ausencia)},
    )
    assert response.status_code == 405
    assert Ausencia.query.count() == 1


def test_borrado_sin_csrf_no_elimina(client, usuario):
    ausencia = crear_ausencia(usuario)
    login(client, usuario)
    response = client.post(
        "/eliminar-ausencia",
        data={"snapshot": snapshot_ausencia(usuario, ausencia)},
        incluir_csrf=False,
    )
    assert response.status_code == 400
    assert Ausencia.query.count() == 1


def test_doble_borrado_se_rechaza_claramente(client, usuario):
    ausencia = crear_ausencia(usuario)
    ausencia_id = ausencia.id
    snapshot = snapshot_ausencia(usuario, ausencia)
    login(client, usuario)
    assert (
        client.post(
            "/eliminar-ausencia",
            data={"snapshot": snapshot},
        ).status_code
        == 302
    )
    assert (
        client.post(
            "/eliminar-ausencia",
            data={"snapshot": snapshot},
        ).status_code
        == 404
    )


def test_borrado_ajeno_no_modifica(client, usuario):
    otro = crear_otro_usuario()
    ausencia = crear_ausencia(otro)
    login(client, usuario)
    response = client.post(
        "/eliminar-ausencia",
        data={"snapshot": snapshot_ausencia(otro, ausencia)},
    )
    assert response.status_code == 404
    assert db.session.get(Ausencia, ausencia.id) is not None


def test_fallo_commit_borrado_hace_rollback(
    client,
    usuario,
    monkeypatch,
):
    ausencia = crear_ausencia(usuario)
    ausencia_id = ausencia.id
    snapshot = snapshot_ausencia(usuario, ausencia)
    login(client, usuario)

    def commit_con_error():
        raise RuntimeError("fallo controlado")

    monkeypatch.setattr(db.session, "commit", commit_con_error)
    client.post(
        "/eliminar-ausencia",
        data={"snapshot": snapshot},
    )
    db.session.expire_all()
    assert db.session.get(Ausencia, ausencia_id) is not None
    assert Ausencia.query.count() == 1


def test_usuario_normal_no_accede_a_rutas_administrativas(client, usuario):
    login(client, usuario)
    assert client.get(f"/admin/ausencias/{usuario.id}").status_code == 302
    assert (
        client.get(f"/admin/registrar-ausencia/{usuario.id}").status_code
        == 302
    )


def test_admin_lista_y_crea_ausencia_para_objetivo(
    client,
    administrador,
    usuario,
):
    login(client, administrador)
    assert client.get(f"/admin/ausencias/{usuario.id}").status_code == 200
    response = client.post(
        f"/admin/registrar-ausencia/{usuario.id}",
        data=datos_formulario(tipo="médico", hora_desde="09:00", hora_hasta="10:00"),
    )
    assert response.status_code == 302
    ausencia = Ausencia.query.one()
    assert ausencia.usuario_id == usuario.id
    assert ausencia.creado_por_admin is True
    assert ausencia.tipo == TIPO_MEDICO


def test_admin_objetivo_inexistente_devuelve_404(client, administrador):
    login(client, administrador)
    assert client.get("/admin/ausencias/999999").status_code == 404
    assert client.get("/admin/registrar-ausencia/999999").status_code == 404


@pytest.mark.parametrize(
    "cambio",
    [
        {"tipo": "Inválido"},
        {"fecha_desde": "sin-fecha"},
        {"fecha_hasta": "2099-06-14"},
        {"tipo": TIPO_MEDICO, "hora_desde": "09:00", "hora_hasta": ""},
    ],
)
def test_admin_rechaza_datos_invalidos_sin_filas(
    client,
    administrador,
    usuario,
    cambio,
):
    login(client, administrador)
    response = client.post(
        f"/admin/registrar-ausencia/{usuario.id}",
        data=datos_formulario(**cambio),
    )
    assert response.status_code == 302
    assert Ausencia.query.count() == 0


def test_admin_rechaza_duplicado_exacto(client, administrador, usuario):
    crear_ausencia(usuario, observaciones="Neutro", creado_por_admin=True)
    login(client, administrador)
    client.post(
        f"/admin/registrar-ausencia/{usuario.id}",
        data=datos_formulario(observaciones="Neutro"),
    )
    assert Ausencia.query.count() == 1


def test_fallo_commit_admin_hace_rollback(
    client,
    administrador,
    usuario,
    monkeypatch,
):
    login(client, administrador)

    def commit_con_error():
        raise RuntimeError("fallo controlado")

    monkeypatch.setattr(db.session, "commit", commit_con_error)
    client.post(
        f"/admin/registrar-ausencia/{usuario.id}",
        data=datos_formulario(),
    )
    assert Ausencia.query.count() == 0
    assert db.session.is_active


@pytest.mark.parametrize("tipo", ["Medico", "Médico"])
def test_ausencia_medica_permite_entrada(client, usuario, tipo):
    crear_ausencia(
        usuario,
        fecha=date.today(),
        tipo=tipo,
        hora_desde=time(9),
        hora_hasta=time(10),
    )
    login(client, usuario)
    response = client.post(
        "/fichar_registro",
        data={"tipo": "entrada", "origen": "Tienda"},
    )
    assert response.status_code == 302
    assert RegistroHorario.query.filter_by(tipo="entrada").count() == 1


def test_ausencia_medica_permite_salida(client, usuario):
    crear_ausencia(usuario, fecha=date.today(), tipo=TIPO_MEDICO)
    fichaje = Fichaje(
        usuario_id=usuario.id,
        fecha=date.today(),
        fecha_creacion=datetime.now(),
        creado_por_admin=False,
        eliminado=False,
    )
    db.session.add(fichaje)
    db.session.flush()
    db.session.add(
        RegistroHorario(
            fichaje_id=fichaje.id,
            tipo="entrada",
            timestamp=datetime.combine(date.today(), time(8)),
            creado_por_admin=False,
            eliminado=False,
            origen="Tienda",
        )
    )
    db.session.commit()
    login(client, usuario)
    client.post("/fichar_registro", data={"tipo": "salida"})
    assert RegistroHorario.query.filter_by(tipo="salida").count() == 1


def test_ausencia_bloqueante_impide_fichar(client, usuario):
    crear_ausencia(usuario, fecha=date.today(), tipo=TIPO_BAJA)
    login(client, usuario)
    response = client.post(
        "/fichar_registro",
        data={"tipo": "entrada", "origen": "Tienda"},
        follow_redirects=True,
    )
    assert "No puedes fichar hoy" in response.get_data(as_text=True)
    assert Fichaje.query.count() == 0


@pytest.mark.parametrize("desplazamiento", [-1, 1])
def test_ausencia_fuera_de_hoy_no_bloquea(client, usuario, desplazamiento):
    crear_ausencia(
        usuario,
        fecha=date.today() + timedelta(days=desplazamiento),
        tipo=TIPO_BAJA,
    )
    login(client, usuario)
    client.post(
        "/fichar_registro",
        data={"tipo": "entrada", "origen": "Tienda"},
    )
    assert Fichaje.query.count() == 1


def test_ausencia_eliminada_fisicamente_deja_de_bloquear(client, usuario):
    ausencia = crear_ausencia(usuario, fecha=date.today(), tipo=TIPO_BAJA)
    login(client, usuario)
    client.post(
        "/eliminar-ausencia",
        data={"snapshot": snapshot_ausencia(usuario, ausencia)},
    )
    client.post(
        "/fichar_registro",
        data={"tipo": "entrada", "origen": "Tienda"},
    )
    assert Ausencia.query.count() == 0
    assert Fichaje.query.count() == 1


def test_ruta_fichar_usa_fecha_local_madrid(
    client,
    usuario,
    monkeypatch,
):
    import app.routes as rutas

    fecha_madrid = date(2099, 1, 2)
    crear_ausencia(usuario, fecha=fecha_madrid, tipo=TIPO_BAJA)
    login(client, usuario)
    monkeypatch.setattr(rutas, "fecha_hoy_madrid", lambda: fecha_madrid)
    html = client.get("/fichar").get_data(as_text=True)
    assert "Baja" in html


def test_filtro_de_tipo_acepta_alias_medico_historico(client, usuario):
    crear_ausencia(usuario, tipo="Médico", observaciones="ALIAS_MEDICO")
    login(client, usuario)
    html = client.get(
        "/mis-ausencias",
        query_string={
            "desde": "2099-01-01",
            "hasta": "2099-12-31",
            "tipo": "médico",
        },
    ).get_data(as_text=True)
    assert "ALIAS_MEDICO" in html


def test_plantilla_ofrece_edicion_y_borrado_post_con_snapshot(client, usuario):
    ausencia = crear_ausencia(usuario)
    login(client, usuario)
    html = client.get(
        "/mis-ausencias",
        query_string={"desde": "2099-01-01", "hasta": "2099-12-31"},
    ).get_data(as_text=True)
    assert 'action="/editar-ausencia"' in html
    assert 'action="/eliminar-ausencia"' in html
    assert f'name="snapshot" value="{snapshot_ausencia(usuario, ausencia)}"' in html
    assert 'name="ausencia_ids"' not in html
    assert 'name="fecha_inicio"' not in html


def test_integrity_error_en_creacion_se_trata_sin_error_500(
    client,
    usuario,
    monkeypatch,
):
    login(client, usuario)

    def commit_con_integrity_error():
        raise IntegrityError("sentencia oculta", {}, RuntimeError("simulado"))

    monkeypatch.setattr(db.session, "commit", commit_con_integrity_error)
    response = client.post(
        "/mis-ausencias",
        data=datos_formulario(),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert Ausencia.query.count() == 0
    assert "sentencia oculta" not in response.get_data(as_text=True)

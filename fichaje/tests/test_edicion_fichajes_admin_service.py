from datetime import date, datetime, time
import inspect

import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from werkzeug.security import generate_password_hash

from app import db
from app import routes
from app.models import Fichaje, Modificacion, RegistroHorario, Usuario
from app.services.edicion_fichajes import (
    crear_snapshot_firmado,
    preparar_edicion,
)
from app.services.fichajes import (
    ADMIN_EDICION_ACTUALIZADA,
    ADMIN_EDICION_ADMINISTRADOR_INEXISTENTE,
    ADMIN_EDICION_CONFLICTO_CONCURRENTE,
    ADMIN_EDICION_ERROR_PERSISTENCIA,
    ADMIN_EDICION_FICHAJE_ELIMINADO,
    ADMIN_EDICION_FICHAJE_INEXISTENTE,
    ADMIN_EDICION_FICHAJES_ACTIVOS_MULTIPLES,
    ADMIN_EDICION_REGISTRO_AJENO,
    ADMIN_EDICION_SIN_CAMBIOS,
    ADMIN_EDICION_SIN_PERMISOS,
    ADMIN_EDICION_TRAMOS_INVALIDOS,
    ADMIN_EDICION_USUARIO_INEXISTENTE,
    EntradaEdicionFichajeAdministrativo,
    editar_fichaje_administrativo,
)
from app.services.horarios import reconstruir_tramos


FECHA = date(2026, 3, 29)


def crear_usuario(*, admin=False, sufijo="servicio-edicion"):
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


def crear_fichaje(
    usuario,
    registros=(),
    *,
    fecha=FECHA,
    eliminado=False,
):
    fichaje = Fichaje(
        usuario_id=usuario.id,
        fecha=fecha,
        fecha_creacion=datetime.combine(fecha, time(7, 0)),
        creado_por_admin=False,
        eliminado=eliminado,
    )
    db.session.add(fichaje)
    db.session.flush()
    creados = []
    for tipo, hora, origen, registro_eliminado in registros:
        registro = RegistroHorario(
            fichaje_id=fichaje.id,
            tipo=tipo,
            timestamp=datetime.combine(fecha, hora),
            creado_por_admin=False,
            eliminado=registro_eliminado,
            origen=origen,
        )
        db.session.add(registro)
        creados.append(registro)
    db.session.commit()
    return fichaje, creados


def tramo(entrada, salida, origen="Tienda"):
    return [
        ("entrada", entrada, origen, False),
        ("salida", salida, origen, False),
    ]


def activos(fichaje_id):
    return (
        RegistroHorario.query.filter_by(
            fichaje_id=fichaje_id,
            eliminado=False,
        )
        .order_by(RegistroHorario.timestamp, RegistroHorario.id)
        .all()
    )


def estado_registros(fichaje_id):
    return [
        (
            registro.id,
            registro.tipo,
            registro.timestamp,
            registro.origen,
            registro.creado_por_admin,
            registro.eliminado,
        )
        for registro in RegistroHorario.query.filter_by(
            fichaje_id=fichaje_id
        ).order_by(RegistroHorario.id)
    ]


def formulario_actual(app, fichaje_id):
    registros = activos(fichaje_id)
    preparacion = preparar_edicion(reconstruir_tramos(registros))
    snapshot = crear_snapshot_firmado(
        fichaje_id,
        registros,
        app.config["SECRET_KEY"],
    )
    datos = {}
    for fila in preparacion.tramos:
        base = f"tramos[{fila.clave}]"
        datos[f"{base}[entrada_id]"] = str(fila.entrada_id)
        datos[f"{base}[salida_id]"] = str(fila.salida_id or "")
        datos[f"{base}[entrada]"] = fila.entrada
        datos[f"{base}[salida]"] = fila.salida
        datos[f"{base}[origen]"] = fila.origen
        datos[f"{base}[eliminar]"] = "0"
    for incidencia in preparacion.irregulares:
        base = f"irregulares[{incidencia.clave}]"
        datos[f"{base}[registro_id]"] = str(incidencia.registro_id)
    return snapshot, datos


def base_por_entrada(datos, registro_id):
    for nombre, valor in datos.items():
        if nombre.endswith("[entrada_id]") and valor == str(registro_id):
            return nombre[: -len("[entrada_id]")]
    raise AssertionError("No se encontro el tramo")


def agregar_tramo(datos, clave, entrada, salida, origen="Tienda"):
    base = f"tramos[{clave}]"
    datos[f"{base}[entrada_id]"] = ""
    datos[f"{base}[salida_id]"] = ""
    datos[f"{base}[entrada]"] = entrada
    datos[f"{base}[salida]"] = salida
    datos[f"{base}[origen]"] = origen
    datos[f"{base}[eliminar]"] = "0"
    return base


def entrada(snapshot, datos):
    return EntradaEdicionFichajeAdministrativo(
        snapshot=snapshot,
        campos=tuple(datos.items()),
    )


def editar(app, administrador_id, fichaje_id, solicitud):
    db.session.rollback()
    return editar_fichaje_administrativo(
        db.session,
        administrador_id=administrador_id,
        fichaje_id=fichaje_id,
        entrada=solicitud,
        secret_key=app.config["SECRET_KEY"],
    )


def autenticar(client, usuario):
    return client.post(
        "/login",
        data={"email": usuario.email, "password": "password-correcta"},
    )


def test_edicion_valida_reemplaza_registros_audita_y_hace_un_commit(
    app,
    administrador,
    usuario,
    monkeypatch,
):
    fichaje, originales = crear_fichaje(
        usuario,
        tramo(time(9, 0), time(14, 0), "Remoto"),
    )
    fichaje_id = fichaje.id
    snapshot, datos = formulario_actual(app, fichaje_id)
    base = base_por_entrada(datos, originales[0].id)
    datos[f"{base}[entrada]"] = "09:15"
    datos[f"{base}[salida]"] = "14:15"
    commit_real = db.session.commit
    commits = []

    def commit_contado():
        commits.append(True)
        return commit_real()

    monkeypatch.setattr(db.session, "commit", commit_contado)
    resultado = editar(
        app,
        administrador.id,
        fichaje_id,
        entrada(snapshot, datos),
    )

    assert resultado.codigo == ADMIN_EDICION_ACTUALIZADA
    assert commits == [True]
    assert all(db.session.get(RegistroHorario, r.id).eliminado for r in originales)
    nuevos = activos(fichaje_id)
    assert [(r.tipo, r.timestamp.time()) for r in nuevos] == [
        ("entrada", time(9, 15)),
        ("salida", time(14, 15)),
    ]
    assert all(r.creado_por_admin is True and r.eliminado is False for r in nuevos)
    assert [r.origen for r in nuevos] == ["Remoto", "Remoto"]
    auditoria = Modificacion.query.one()
    assert auditoria.admin_id == administrador.id
    assert auditoria.campo_modificado == "tramo_mod"
    assert auditoria.valor_anterior == "09:00-14:00"
    assert auditoria.valor_nuevo == "09:15-14:15"


def test_anadir_segundo_tramo_conserva_ids_y_origen_del_primero(
    app,
    administrador,
    usuario,
):
    fichaje, originales = crear_fichaje(
        usuario,
        tramo(time(9, 0), time(14, 0), "Remoto"),
    )
    fichaje_id = fichaje.id
    snapshot, datos = formulario_actual(app, fichaje_id)
    agregar_tramo(datos, "nuevo", "16:00", "20:00", "Tienda")

    resultado = editar(
        app,
        administrador.id,
        fichaje_id,
        entrada(snapshot, datos),
    )

    assert resultado.codigo == ADMIN_EDICION_ACTUALIZADA
    registros = activos(fichaje_id)
    assert [r.id for r in registros[:2]] == [r.id for r in originales]
    assert [r.origen for r in registros] == ["Remoto", "Remoto", "Tienda", "Tienda"]
    auditoria = Modificacion.query.one()
    assert auditoria.campo_modificado == "tramo_add"
    assert auditoria.valor_anterior == "-"
    assert auditoria.valor_nuevo == "ADD 16:00-20:00"


def test_eliminar_un_tramo_conserva_el_otro_y_audita(
    app,
    administrador,
    usuario,
):
    registros = tramo(time(9, 0), time(14, 0), "Tienda")
    registros += tramo(time(16, 0), time(20, 0), "Remoto")
    fichaje, originales = crear_fichaje(usuario, registros)
    fichaje_id = fichaje.id
    snapshot, datos = formulario_actual(app, fichaje_id)
    base = base_por_entrada(datos, originales[2].id)
    datos[f"{base}[eliminar]"] = "1"

    resultado = editar(
        app,
        administrador.id,
        fichaje_id,
        entrada(snapshot, datos),
    )

    assert resultado.codigo == ADMIN_EDICION_ACTUALIZADA
    assert [r.id for r in activos(fichaje_id)] == [originales[0].id, originales[1].id]
    assert db.session.get(RegistroHorario, originales[2].id).eliminado is True
    assert db.session.get(RegistroHorario, originales[3].id).eliminado is True
    auditoria = Modificacion.query.one()
    assert (auditoria.campo_modificado, auditoria.valor_anterior, auditoria.valor_nuevo) == (
        "tramo_del",
        "16:00-20:00",
        "DEL",
    )


def test_eliminar_todos_los_tramos_mantiene_cabecera_activa(
    app,
    administrador,
    usuario,
):
    registros = tramo(time(9, 0), time(14, 0)) + tramo(time(16, 0), time(20, 0))
    fichaje, _ = crear_fichaje(usuario, registros)
    fichaje_id = fichaje.id
    snapshot, datos = formulario_actual(app, fichaje_id)
    for nombre in tuple(datos):
        if nombre.endswith("[eliminar]"):
            datos[nombre] = "1"

    resultado = editar(
        app,
        administrador.id,
        fichaje_id,
        entrada(snapshot, datos),
    )

    assert resultado.codigo == ADMIN_EDICION_ACTUALIZADA
    assert activos(fichaje_id) == []
    assert db.session.get(Fichaje, fichaje_id).eliminado is False
    assert RegistroHorario.query.filter_by(fichaje_id=fichaje_id).count() == 4
    assert [m.campo_modificado for m in Modificacion.query.order_by(Modificacion.id)] == [
        "tramo_del",
        "tramo_del",
    ]


def test_sin_cambios_no_escribe_y_limpia_transaccion(
    app,
    administrador,
    usuario,
):
    fichaje, _ = crear_fichaje(usuario, tramo(time(9, 0), time(14, 0)))
    fichaje_id = fichaje.id
    antes = estado_registros(fichaje_id)
    snapshot, datos = formulario_actual(app, fichaje_id)

    resultado = editar(
        app,
        administrador.id,
        fichaje_id,
        entrada(snapshot, datos),
    )

    assert resultado.codigo == ADMIN_EDICION_SIN_CAMBIOS
    assert estado_registros(fichaje_id) == antes
    assert Modificacion.query.count() == 0
    assert not db.session.new
    assert not db.session.dirty
    assert db.session.is_active


def test_administrador_inexistente_no_modifica(app, usuario):
    fichaje, _ = crear_fichaje(usuario, tramo(time(9, 0), time(14, 0)))
    fichaje_id = fichaje.id
    antes = estado_registros(fichaje_id)
    snapshot, datos = formulario_actual(app, fichaje_id)

    resultado = editar(app, 999999, fichaje_id, entrada(snapshot, datos))

    assert resultado.codigo == ADMIN_EDICION_ADMINISTRADOR_INEXISTENTE
    assert estado_registros(fichaje_id) == antes


def test_usuario_sin_permisos_no_modifica(app, usuario):
    objetivo = crear_usuario(sufijo="objetivo-sin-permisos")
    fichaje, _ = crear_fichaje(objetivo, tramo(time(9, 0), time(14, 0)))
    fichaje_id = fichaje.id
    antes = estado_registros(fichaje_id)
    snapshot, datos = formulario_actual(app, fichaje_id)

    resultado = editar(app, usuario.id, fichaje_id, entrada(snapshot, datos))

    assert resultado.codigo == ADMIN_EDICION_SIN_PERMISOS
    assert estado_registros(fichaje_id) == antes


def test_fichaje_inexistente_no_modifica(app, administrador):
    resultado = editar(
        app,
        administrador.id,
        999999,
        EntradaEdicionFichajeAdministrativo("x", ()),
    )

    assert resultado.codigo == ADMIN_EDICION_FICHAJE_INEXISTENTE


def test_fichaje_eliminado_no_se_reactiva(app, administrador, usuario):
    fichaje, registros = crear_fichaje(
        usuario,
        tramo(time(9, 0), time(14, 0)),
        eliminado=True,
    )
    fichaje_id = fichaje.id
    snapshot = crear_snapshot_firmado(
        fichaje_id,
        registros,
        app.config["SECRET_KEY"],
    )

    resultado = editar(
        app,
        administrador.id,
        fichaje_id,
        EntradaEdicionFichajeAdministrativo(snapshot, ()),
    )

    assert resultado.codigo == ADMIN_EDICION_FICHAJE_ELIMINADO
    assert db.session.get(Fichaje, fichaje_id).eliminado is True
    assert all(r.eliminado is False for r in registros)


def test_cabecera_sin_usuario_devuelve_estado_controlado(app, administrador):
    fichaje = Fichaje(
        usuario_id=999999,
        fecha=FECHA,
        fecha_creacion=datetime.combine(FECHA, time(7, 0)),
        creado_por_admin=False,
        eliminado=False,
    )
    db.session.add(fichaje)
    db.session.commit()
    fichaje_id = fichaje.id

    resultado = editar(
        app,
        administrador.id,
        fichaje_id,
        EntradaEdicionFichajeAdministrativo("x", ()),
    )

    assert resultado.codigo == ADMIN_EDICION_USUARIO_INEXISTENTE


def test_varias_cabeceras_activas_no_eligen_una(app, administrador, usuario):
    primero, _ = crear_fichaje(usuario, tramo(time(9, 0), time(14, 0)))
    segundo, _ = crear_fichaje(usuario, (), fecha=primero.fecha)
    primero_id = primero.id
    segundo_id = segundo.id
    antes = estado_registros(primero_id)
    snapshot, datos = formulario_actual(app, primero_id)

    resultado = editar(
        app,
        administrador.id,
        primero_id,
        entrada(snapshot, datos),
    )

    assert resultado.codigo == ADMIN_EDICION_FICHAJES_ACTIVOS_MULTIPLES
    assert estado_registros(primero_id) == antes
    assert db.session.get(Fichaje, segundo_id).eliminado is False


def test_id_de_otro_fichaje_se_rechaza_sin_modificar_ninguno(
    app,
    administrador,
    usuario,
):
    primero, registros_primero = crear_fichaje(
        usuario,
        tramo(time(9, 0), time(14, 0)),
    )
    otro_usuario = crear_usuario(sufijo="otro-fichaje-id")
    segundo, registros_segundo = crear_fichaje(
        otro_usuario,
        tramo(time(10, 0), time(15, 0)),
    )
    primero_id = primero.id
    segundo_id = segundo.id
    antes_primero = estado_registros(primero_id)
    antes_segundo = estado_registros(segundo_id)
    snapshot, datos = formulario_actual(app, primero_id)
    base = base_por_entrada(datos, registros_primero[0].id)
    datos[f"{base}[entrada_id]"] = str(registros_segundo[0].id)

    resultado = editar(
        app,
        administrador.id,
        primero_id,
        entrada(snapshot, datos),
    )

    assert resultado.codigo == ADMIN_EDICION_REGISTRO_AJENO
    assert estado_registros(primero_id) == antes_primero
    assert estado_registros(segundo_id) == antes_segundo


@pytest.mark.parametrize("identificador", ["-1", "999999", "+1", "１"])
def test_id_invalido_o_inexistente_se_rechaza(
    app,
    administrador,
    usuario,
    identificador,
):
    fichaje, registros = crear_fichaje(
        usuario,
        tramo(time(9, 0), time(14, 0)),
    )
    fichaje_id = fichaje.id
    snapshot, datos = formulario_actual(app, fichaje_id)
    base = base_por_entrada(datos, registros[0].id)
    datos[f"{base}[entrada_id]"] = identificador

    resultado = editar(
        app,
        administrador.id,
        fichaje_id,
        entrada(snapshot, datos),
    )

    assert resultado.codigo == ADMIN_EDICION_REGISTRO_AJENO
    assert len(activos(fichaje_id)) == 2


def test_id_repetido_en_dos_tramos_se_rechaza(app, administrador, usuario):
    fichaje, registros = crear_fichaje(
        usuario,
        tramo(time(9, 0), time(14, 0)),
    )
    fichaje_id = fichaje.id
    snapshot, datos = formulario_actual(app, fichaje_id)
    original = base_por_entrada(datos, registros[0].id)
    duplicado = "tramos[duplicado]"
    for campo in ("entrada_id", "salida_id", "entrada", "salida", "origen"):
        datos[f"{duplicado}[{campo}]"] = datos[f"{original}[{campo}]"]
    datos[f"{duplicado}[eliminar]"] = "0"

    resultado = editar(
        app,
        administrador.id,
        fichaje_id,
        entrada(snapshot, datos),
    )

    assert resultado.codigo == ADMIN_EDICION_REGISTRO_AJENO


def test_tipos_intercambiados_se_rechazan(app, administrador, usuario):
    fichaje, registros = crear_fichaje(
        usuario,
        tramo(time(9, 0), time(14, 0)),
    )
    fichaje_id = fichaje.id
    snapshot, datos = formulario_actual(app, fichaje_id)
    base = base_por_entrada(datos, registros[0].id)
    datos[f"{base}[entrada_id]"] = str(registros[1].id)
    datos[f"{base}[salida_id]"] = str(registros[0].id)

    resultado = editar(
        app,
        administrador.id,
        fichaje_id,
        entrada(snapshot, datos),
    )

    assert resultado.codigo == ADMIN_EDICION_REGISTRO_AJENO


def test_formulario_con_campos_desalineados_es_validacion_controlada(
    app,
    administrador,
    usuario,
):
    fichaje, registros = crear_fichaje(
        usuario,
        tramo(time(9, 0), time(14, 0)),
    )
    fichaje_id = fichaje.id
    snapshot, datos = formulario_actual(app, fichaje_id)
    base = base_por_entrada(datos, registros[0].id)
    del datos[f"{base}[salida]"]

    resultado = editar(
        app,
        administrador.id,
        fichaje_id,
        entrada(snapshot, datos),
    )

    assert resultado.codigo == ADMIN_EDICION_TRAMOS_INVALIDOS
    assert len(activos(fichaje_id)) == 2


@pytest.mark.parametrize(
    ("entrada_hora", "salida_hora"),
    [
        ("09:00", ""),
        ("", "14:00"),
        ("09:00", "09:00"),
        ("14:00", "09:00"),
        ("09:00:00", "14:00"),
    ],
)
def test_horas_parciales_iguales_invertidas_o_con_segundos_se_rechazan(
    app,
    administrador,
    usuario,
    entrada_hora,
    salida_hora,
):
    fichaje, _ = crear_fichaje(usuario)
    fichaje_id = fichaje.id
    snapshot, datos = formulario_actual(app, fichaje_id)
    agregar_tramo(datos, "invalido", entrada_hora, salida_hora)

    resultado = editar(
        app,
        administrador.id,
        fichaje_id,
        entrada(snapshot, datos),
    )

    if entrada_hora and not salida_hora:
        assert resultado.codigo == ADMIN_EDICION_ACTUALIZADA
        assert reconstruir_tramos(activos(fichaje_id)).entrada_abierta is not None
    else:
        assert resultado.codigo == ADMIN_EDICION_TRAMOS_INVALIDOS


def test_solapamiento_se_rechaza(app, administrador, usuario):
    fichaje, _ = crear_fichaje(
        usuario,
        tramo(time(9, 0), time(14, 0)),
    )
    fichaje_id = fichaje.id
    snapshot, datos = formulario_actual(app, fichaje_id)
    agregar_tramo(datos, "solapado", "13:30", "18:00")

    resultado = editar(
        app,
        administrador.id,
        fichaje_id,
        entrada(snapshot, datos),
    )

    assert resultado.codigo == ADMIN_EDICION_TRAMOS_INVALIDOS
    assert "solaparse" in resultado.mensaje


def test_tramo_duplicado_exacto_se_rechaza(app, administrador, usuario):
    fichaje, _ = crear_fichaje(
        usuario,
        tramo(time(9, 0), time(14, 0)),
    )
    fichaje_id = fichaje.id
    snapshot, datos = formulario_actual(app, fichaje_id)
    agregar_tramo(datos, "duplicado", "09:00", "14:00", "Remoto")

    resultado = editar(
        app,
        administrador.id,
        fichaje_id,
        entrada(snapshot, datos),
    )

    assert resultado.codigo == ADMIN_EDICION_TRAMOS_INVALIDOS


def test_registro_eliminado_no_puede_reactivarse(app, administrador, usuario):
    fichaje, registros = crear_fichaje(
        usuario,
        [
            ("entrada", time(9, 0), "Tienda", True),
            ("salida", time(14, 0), "Tienda", True),
        ],
    )
    fichaje_id = fichaje.id
    snapshot, datos = formulario_actual(app, fichaje_id)
    base = agregar_tramo(datos, "historico", "09:00", "14:00")
    datos[f"{base}[entrada_id]"] = str(registros[0].id)
    datos[f"{base}[salida_id]"] = str(registros[1].id)

    resultado = editar(
        app,
        administrador.id,
        fichaje_id,
        entrada(snapshot, datos),
    )

    assert resultado.codigo == ADMIN_EDICION_REGISTRO_AJENO
    assert all(db.session.get(RegistroHorario, r.id).eliminado for r in registros)


@pytest.mark.parametrize(
    ("origen_entrada", "origen_salida"),
    [("Tienda", "Tienda"), ("Remoto", "Remoto"), ("Tienda", "Auto")],
)
def test_tramo_sin_cambios_conserva_ids_y_origenes_exactos(
    app,
    administrador,
    usuario,
    origen_entrada,
    origen_salida,
):
    fichaje, registros = crear_fichaje(
        usuario,
        [
            ("entrada", time(9, 0), origen_entrada, False),
            ("salida", time(14, 0), origen_salida, False),
        ],
    )
    fichaje_id = fichaje.id
    snapshot, datos = formulario_actual(app, fichaje_id)

    resultado = editar(
        app,
        administrador.id,
        fichaje_id,
        entrada(snapshot, datos),
    )

    assert resultado.codigo == ADMIN_EDICION_SIN_CAMBIOS
    conservados = activos(fichaje_id)
    assert [r.id for r in conservados] == [r.id for r in registros]
    assert [r.origen for r in conservados] == [origen_entrada, origen_salida]


def test_modificar_tramo_remoto_conserva_convencion_remota(
    app,
    administrador,
    usuario,
):
    fichaje, registros = crear_fichaje(
        usuario,
        tramo(time(9, 0), time(14, 0), "Remoto"),
    )
    fichaje_id = fichaje.id
    snapshot, datos = formulario_actual(app, fichaje_id)
    base = base_por_entrada(datos, registros[0].id)
    datos[f"{base}[salida]"] = "14:30"

    resultado = editar(
        app,
        administrador.id,
        fichaje_id,
        entrada(snapshot, datos),
    )

    assert resultado.codigo == ADMIN_EDICION_ACTUALIZADA
    finales = activos(fichaje_id)
    assert finales[0].id == registros[0].id
    assert finales[1].id != registros[1].id
    assert [r.origen for r in finales] == ["Remoto", "Remoto"]


def test_modificar_salida_auto_aplica_origen_seleccionado_del_tramo(
    app,
    administrador,
    usuario,
):
    fichaje, registros = crear_fichaje(
        usuario,
        [
            ("entrada", time(9, 0), "Tienda", False),
            ("salida", time(14, 0), "Auto", False),
        ],
    )
    fichaje_id = fichaje.id
    snapshot, datos = formulario_actual(app, fichaje_id)
    base = base_por_entrada(datos, registros[0].id)
    datos[f"{base}[salida]"] = "14:30"

    resultado = editar(
        app,
        administrador.id,
        fichaje_id,
        entrada(snapshot, datos),
    )

    assert resultado.codigo == ADMIN_EDICION_ACTUALIZADA
    finales = activos(fichaje_id)
    assert finales[0].id == registros[0].id
    assert finales[1].origen == "Tienda"
    assert db.session.get(RegistroHorario, registros[1].id).eliminado is True
    origen_auditado = Modificacion.query.filter_by(
        campo_modificado="origen_salida"
    ).one()
    assert (origen_auditado.valor_anterior, origen_auditado.valor_nuevo) == (
        "Auto",
        "Tienda",
    )


def test_snapshot_obsoleto_no_sobrescribe_cambio_externo(
    app,
    administrador,
    usuario,
):
    fichaje, registros = crear_fichaje(
        usuario,
        tramo(time(9, 0), time(14, 0)),
    )
    fichaje_id = fichaje.id
    snapshot, datos = formulario_actual(app, fichaje_id)
    base = base_por_entrada(datos, registros[0].id)
    datos[f"{base}[salida]"] = "15:00"
    registros[0].origen = "Remoto"
    db.session.commit()
    estado_externo = estado_registros(fichaje_id)

    resultado = editar(
        app,
        administrador.id,
        fichaje_id,
        entrada(snapshot, datos),
    )

    assert resultado.codigo == ADMIN_EDICION_CONFLICTO_CONCURRENTE
    assert estado_registros(fichaje_id) == estado_externo
    assert Modificacion.query.count() == 0


def ejecutar_con_fallo_evento(
    app,
    administrador_id,
    fichaje_id,
    solicitud,
    modelo,
    evento,
    condicion,
):
    def fallar(_mapper, _connection, target):
        if condicion(target):
            raise RuntimeError("fallo controlado")

    event.listen(modelo, evento, fallar)
    try:
        return editar(app, administrador_id, fichaje_id, solicitud)
    finally:
        event.remove(modelo, evento, fallar)


def test_fallo_al_marcar_antiguos_hace_rollback_total(
    app,
    administrador,
    usuario,
):
    fichaje, registros = crear_fichaje(
        usuario,
        tramo(time(9, 0), time(14, 0)),
    )
    fichaje_id = fichaje.id
    antes = estado_registros(fichaje_id)
    snapshot, datos = formulario_actual(app, fichaje_id)
    base = base_por_entrada(datos, registros[0].id)
    datos[f"{base}[entrada]"] = "09:15"

    resultado = ejecutar_con_fallo_evento(
        app,
        administrador.id,
        fichaje_id,
        entrada(snapshot, datos),
        RegistroHorario,
        "before_update",
        lambda target: target.eliminado is True,
    )

    assert resultado.codigo == ADMIN_EDICION_ERROR_PERSISTENCIA
    assert estado_registros(fichaje_id) == antes
    assert Modificacion.query.count() == 0
    assert not db.session.new and not db.session.dirty and db.session.is_active


@pytest.mark.parametrize("tipo", ["entrada", "salida"])
def test_fallo_al_insertar_cada_registro_hace_rollback_total(
    app,
    administrador,
    usuario,
    tipo,
):
    fichaje, registros = crear_fichaje(
        usuario,
        tramo(time(9, 0), time(14, 0)),
    )
    fichaje_id = fichaje.id
    antes = estado_registros(fichaje_id)
    snapshot, datos = formulario_actual(app, fichaje_id)
    base = base_por_entrada(datos, registros[0].id)
    datos[f"{base}[entrada]"] = "09:15"
    datos[f"{base}[salida]"] = "14:15"

    resultado = ejecutar_con_fallo_evento(
        app,
        administrador.id,
        fichaje_id,
        entrada(snapshot, datos),
        RegistroHorario,
        "before_insert",
        lambda target: target.tipo == tipo,
    )

    assert resultado.codigo == ADMIN_EDICION_ERROR_PERSISTENCIA
    assert estado_registros(fichaje_id) == antes
    assert Modificacion.query.count() == 0


def test_fallo_al_insertar_auditoria_hace_rollback_total(
    app,
    administrador,
    usuario,
):
    fichaje, registros = crear_fichaje(
        usuario,
        tramo(time(9, 0), time(14, 0)),
    )
    fichaje_id = fichaje.id
    antes = estado_registros(fichaje_id)
    snapshot, datos = formulario_actual(app, fichaje_id)
    datos[f"{base_por_entrada(datos, registros[0].id)}[salida]"] = "14:30"

    resultado = ejecutar_con_fallo_evento(
        app,
        administrador.id,
        fichaje_id,
        entrada(snapshot, datos),
        Modificacion,
        "before_insert",
        lambda _target: True,
    )

    assert resultado.codigo == ADMIN_EDICION_ERROR_PERSISTENCIA
    assert estado_registros(fichaje_id) == antes
    assert Modificacion.query.count() == 0


def test_fallo_commit_permite_reintento_unico(
    app,
    administrador,
    usuario,
    monkeypatch,
):
    fichaje, registros = crear_fichaje(
        usuario,
        tramo(time(9, 0), time(14, 0)),
    )
    fichaje_id = fichaje.id
    antes = estado_registros(fichaje_id)
    snapshot, datos = formulario_actual(app, fichaje_id)
    datos[f"{base_por_entrada(datos, registros[0].id)}[salida]"] = "14:30"
    solicitud = entrada(snapshot, datos)
    commit_real = db.session.commit

    with monkeypatch.context() as contexto:
        contexto.setattr(
            db.session,
            "commit",
            lambda: (_ for _ in ()).throw(RuntimeError("fallo commit")),
        )
        fallido = editar(app, administrador.id, fichaje_id, solicitud)

    assert fallido.codigo == ADMIN_EDICION_ERROR_PERSISTENCIA
    assert estado_registros(fichaje_id) == antes
    assert Modificacion.query.count() == 0
    assert not db.session.new and not db.session.dirty and db.session.is_active

    monkeypatch.setattr(db.session, "commit", commit_real)
    reintento = editar(app, administrador.id, fichaje_id, solicitud)
    assert reintento.codigo == ADMIN_EDICION_ACTUALIZADA
    assert len(activos(fichaje_id)) == 2
    assert RegistroHorario.query.filter_by(fichaje_id=fichaje_id).count() == 3
    assert Modificacion.query.count() == 1


def test_mariadb_error_1020_se_trata_como_conflicto_obsoleto(
    app,
    administrador,
    usuario,
    monkeypatch,
):
    fichaje, registros = crear_fichaje(
        usuario,
        tramo(time(9, 0), time(14, 0)),
    )
    fichaje_id = fichaje.id
    antes = estado_registros(fichaje_id)
    snapshot, datos = formulario_actual(app, fichaje_id)
    datos[f"{base_por_entrada(datos, registros[0].id)}[salida]"] = "14:30"
    solicitud = entrada(snapshot, datos)
    error = OperationalError(
        "UPDATE registro_horario",
        {},
        Exception(1020, "record changed"),
    )

    monkeypatch.setattr(
        db.session,
        "commit",
        lambda: (_ for _ in ()).throw(error),
    )
    resultado = editar(app, administrador.id, fichaje_id, solicitud)

    assert resultado.codigo == ADMIN_EDICION_CONFLICTO_CONCURRENTE
    assert estado_registros(fichaje_id) == antes
    assert Modificacion.query.count() == 0
    assert not db.session.new and not db.session.dirty and db.session.is_active


def test_api_no_acepta_campos_de_modelo_controlables(
    app,
    administrador,
    usuario,
):
    fichaje, _ = crear_fichaje(usuario)

    with pytest.raises(TypeError):
        editar_fichaje_administrativo(
            db.session,
            administrador_id=administrador.id,
            fichaje_id=fichaje.id,
            entrada=EntradaEdicionFichajeAdministrativo("x", ()),
            secret_key=app.config["SECRET_KEY"],
            usuario_id=usuario.id,
            fecha=FECHA,
            tipo="salida",
            origen="Auto",
            eliminado=False,
            creado_por_admin=False,
        )


def test_tramos_desordenados_se_ordenan_deterministicamente(
    app,
    administrador,
    usuario,
):
    fichaje, _ = crear_fichaje(usuario)
    fichaje_id = fichaje.id
    snapshot, datos = formulario_actual(app, fichaje_id)
    agregar_tramo(datos, "tarde", "16:00", "20:00", "Remoto")
    agregar_tramo(datos, "manana", "09:00", "14:00", "Tienda")

    resultado = editar(
        app,
        administrador.id,
        fichaje_id,
        entrada(snapshot, datos),
    )

    assert resultado.codigo == ADMIN_EDICION_ACTUALIZADA
    assert [r.timestamp.time() for r in activos(fichaje_id)] == [
        time(9, 0),
        time(14, 0),
        time(16, 0),
        time(20, 0),
    ]


def test_cabecera_no_cambia_usuario_fecha_ni_trazabilidad(
    app,
    administrador,
    usuario,
):
    fichaje, _ = crear_fichaje(usuario)
    fichaje_id = fichaje.id
    estado_cabecera = (
        fichaje.usuario_id,
        fichaje.fecha,
        fichaje.fecha_creacion,
        fichaje.creado_por_admin,
        fichaje.eliminado,
    )
    snapshot, datos = formulario_actual(app, fichaje_id)
    agregar_tramo(datos, "nuevo", "09:00", "14:00")

    editar(app, administrador.id, fichaje_id, entrada(snapshot, datos))

    cabecera = db.session.get(Fichaje, fichaje_id)
    assert (
        cabecera.usuario_id,
        cabecera.fecha,
        cabecera.fecha_creacion,
        cabecera.creado_por_admin,
        cabecera.eliminado,
    ) == estado_cabecera
    assert all(r.timestamp.date() == FECHA for r in activos(fichaje_id))


def test_get_ruta_exige_sesion_y_administrador(client, administrador, usuario):
    fichaje, _ = crear_fichaje(usuario)
    ruta = f"/admin/editar_fichaje/{fichaje.id}"

    assert client.get(ruta).status_code == 302
    autenticar(client, usuario)
    denegado = client.get(ruta)
    assert denegado.status_code == 302
    assert denegado.headers["Location"].endswith("/fichar")


def test_get_ruta_admin_y_fichaje_eliminado_controlado(
    client,
    administrador,
    usuario,
):
    activo, _ = crear_fichaje(usuario)
    eliminado, _ = crear_fichaje(usuario, (), fecha=FECHA.replace(day=28), eliminado=True)
    autenticar(client, administrador)

    assert client.get(f"/admin/editar_fichaje/{activo.id}").status_code == 200
    respuesta = client.get(f"/admin/editar_fichaje/{eliminado.id}")
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith(f"/admin/fichajes/{usuario.id}")


def test_ruta_fichaje_inexistente_devuelve_404_en_get_y_post(
    client,
    administrador,
):
    autenticar(client, administrador)
    ruta = "/admin/editar_fichaje/999999"

    assert client.get(ruta).status_code == 404
    assert client.post(ruta, data={"snapshot": "irrelevante"}).status_code == 404


def test_post_ruta_fichaje_eliminado_no_reactiva(
    client,
    administrador,
    usuario,
    app,
):
    fichaje, registros = crear_fichaje(
        usuario,
        tramo(time(9, 0), time(14, 0)),
        eliminado=True,
    )
    fichaje_id = fichaje.id
    snapshot = crear_snapshot_firmado(
        fichaje_id,
        registros,
        app.config["SECRET_KEY"],
    )
    autenticar(client, administrador)

    respuesta = client.post(
        f"/admin/editar_fichaje/{fichaje_id}",
        data={"snapshot": snapshot},
    )

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith(
        f"/admin/fichajes/{usuario.id}"
    )
    assert db.session.get(Fichaje, fichaje_id).eliminado is True
    assert all(
        db.session.get(RegistroHorario, row.id).eliminado is False
        for row in registros
    )


def test_post_ruta_sin_csrf_no_escribe(client, administrador, usuario, app):
    fichaje, _ = crear_fichaje(usuario)
    fichaje_id = fichaje.id
    snapshot, datos = formulario_actual(app, fichaje_id)
    agregar_tramo(datos, "nuevo", "09:00", "14:00")
    datos["snapshot"] = snapshot
    autenticar(client, administrador)

    respuesta = client.post(
        f"/admin/editar_fichaje/{fichaje_id}",
        data=datos,
        incluir_csrf=False,
    )

    assert respuesta.status_code == 400
    assert activos(fichaje_id) == []


def test_campos_extra_de_ruta_no_alteran_cabecera(
    client,
    administrador,
    usuario,
    app,
):
    fichaje, _ = crear_fichaje(usuario)
    fichaje_id = fichaje.id
    snapshot, datos = formulario_actual(app, fichaje_id)
    agregar_tramo(datos, "nuevo", "09:00", "14:00")
    datos.update(
        {
            "snapshot": snapshot,
            "usuario_id": str(administrador.id),
            "fecha": "2030-01-01",
            "fichaje_id": "999999",
            "creado_por_admin": "0",
            "eliminado": "1",
        }
    )
    autenticar(client, administrador)

    respuesta = client.post(
        f"/admin/editar_fichaje/{fichaje_id}",
        data=datos,
    )

    assert respuesta.status_code == 302
    cabecera = db.session.get(Fichaje, fichaje_id)
    assert cabecera.usuario_id == usuario.id
    assert cabecera.fecha == FECHA
    assert cabecera.eliminado is False


def test_ruta_es_delgada_y_no_contiene_escritores_ni_depuracion():
    fuente = inspect.getsource(routes.editar_fichaje_admin)

    for fragmento in (
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
        "print(",
    ):
        assert fragmento not in fuente
    assert "editar_fichaje_administrativo(" in fuente

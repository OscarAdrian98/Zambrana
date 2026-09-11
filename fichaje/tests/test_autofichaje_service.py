from datetime import datetime, timedelta, timezone
import inspect

import pytest
import pytz
from sqlalchemy import event

from app import db
from app.models import Ausencia, Fichaje, RegistroHorario
from app.services.fichajes import (
    AUTO_AUSENCIA_BLOQUEANTE,
    AUTO_ERROR_PERSISTENCIA,
    AUTO_FICHAJES_ACTIVOS_MULTIPLES,
    AUTO_SALIDA_CREADA,
    AUTO_SECUENCIA_ANOMALA,
    AUTO_SIN_FICHAJE_ACTIVO,
    AUTO_SIN_TRAMO_ABIERTO,
    AUTO_TIMESTAMP_INVALIDO,
    AUTO_USUARIO_INEXISTENTE,
    AUTO_YA_CERRADO,
    analizar_secuencia,
    registrar_salida_automatica,
)


MADRID = pytz.timezone("Europe/Madrid")
ENTRADA = MADRID.localize(datetime(2026, 4, 15, 8, 0, 0))
SALIDA = MADRID.localize(datetime(2026, 4, 15, 14, 5, 0, 987654))


def crear_fichaje(usuario, *, eliminado=False):
    fichaje = Fichaje(
        usuario_id=usuario.id,
        fecha=ENTRADA.date(),
        fecha_creacion=ENTRADA,
        creado_por_admin=False,
        eliminado=eliminado,
    )
    db.session.add(fichaje)
    db.session.flush()
    return fichaje


def crear_registro(
    fichaje,
    tipo,
    instante,
    *,
    eliminado=False,
    origen="Tienda",
):
    registro = RegistroHorario(
        fichaje_id=fichaje.id,
        tipo=tipo,
        timestamp=instante,
        creado_por_admin=False,
        eliminado=eliminado,
        origen=origen,
    )
    db.session.add(registro)
    return registro


def preparar_entrada(usuario):
    fichaje = crear_fichaje(usuario)
    entrada = crear_registro(fichaje, "entrada", ENTRADA)
    db.session.commit()
    return fichaje, entrada


def test_salida_automatica_valida_fuerza_campos_y_un_commit(usuario, monkeypatch):
    fichaje, _ = preparar_entrada(usuario)
    commit_real = db.session.commit
    commits = []

    def commit_contado():
        commits.append(True)
        return commit_real()

    monkeypatch.setattr(db.session, "commit", commit_contado)
    resultado = registrar_salida_automatica(
        db.session,
        usuario.id,
        SALIDA,
    )

    assert resultado.codigo == AUTO_SALIDA_CREADA
    assert resultado.instante == SALIDA.replace(microsecond=0)
    assert resultado.fecha == fichaje.fecha
    assert commits == [True]
    registros = RegistroHorario.query.order_by(RegistroHorario.timestamp).all()
    assert [registro.tipo for registro in registros] == ["entrada", "salida"]
    salida = registros[1]
    assert salida.origen == "Auto"
    assert salida.eliminado is False
    assert salida.creado_por_admin is True
    assert salida.timestamp == SALIDA.replace(tzinfo=None, microsecond=0)
    assert analizar_secuencia(registros, fichaje.fecha).entrada_abierta is None


def test_api_automatica_no_acepta_tipo_origen_ni_campos_de_modelo():
    parametros = inspect.signature(registrar_salida_automatica).parameters
    assert tuple(parametros) == ("session", "usuario_id", "instante_efectivo")
    assert not {
        "tipo",
        "origen",
        "creado_por_admin",
        "eliminado",
        "fichaje_id",
        "registro_id",
    }.intersection(parametros)


def test_sin_fichaje_no_crea_primera_salida(usuario):
    resultado = registrar_salida_automatica(db.session, usuario.id, SALIDA)

    assert resultado.codigo == AUTO_SIN_FICHAJE_ACTIVO
    assert Fichaje.query.count() == 0
    assert RegistroHorario.query.count() == 0


def test_segunda_ejecucion_es_idempotente(usuario):
    preparar_entrada(usuario)
    primera = registrar_salida_automatica(db.session, usuario.id, SALIDA)
    salida_original = RegistroHorario.query.filter_by(tipo="salida").one()
    valores_originales = (salida_original.id, salida_original.timestamp, salida_original.origen)

    segunda = registrar_salida_automatica(
        db.session,
        usuario.id,
        SALIDA + timedelta(minutes=10),
    )

    assert primera.codigo == AUTO_SALIDA_CREADA
    assert segunda.codigo == AUTO_YA_CERRADO
    assert RegistroHorario.query.count() == 2
    salida_actual = RegistroHorario.query.filter_by(tipo="salida").one()
    assert (salida_actual.id, salida_actual.timestamp, salida_actual.origen) == valores_originales


def test_cita_medica_permite_cerrar_tramo(usuario):
    preparar_entrada(usuario)
    db.session.add(
        Ausencia(
            usuario_id=usuario.id,
            fecha=ENTRADA.date(),
            tipo="  Médico ",
            creado_por_admin=False,
        )
    )
    db.session.commit()

    resultado = registrar_salida_automatica(db.session, usuario.id, SALIDA)

    assert resultado.codigo == AUTO_SALIDA_CREADA


@pytest.mark.parametrize(
    "tipo_ausencia",
    ["Vacaciones", "Baja", "Enfermedad", "Asuntos propios", "Histórico desconocido"],
)
def test_ausencia_bloqueante_impide_salida(usuario, tipo_ausencia):
    preparar_entrada(usuario)
    db.session.add(
        Ausencia(
            usuario_id=usuario.id,
            fecha=ENTRADA.date(),
            tipo=tipo_ausencia,
            creado_por_admin=False,
        )
    )
    db.session.commit()

    resultado = registrar_salida_automatica(db.session, usuario.id, SALIDA)

    assert resultado.codigo == AUTO_AUSENCIA_BLOQUEANTE
    assert RegistroHorario.query.count() == 1


def test_medica_y_bloqueante_priorizan_bloqueo(usuario):
    preparar_entrada(usuario)
    db.session.add_all(
        [
            Ausencia(usuario_id=usuario.id, fecha=ENTRADA.date(), tipo="Médico"),
            Ausencia(usuario_id=usuario.id, fecha=ENTRADA.date(), tipo="Vacaciones"),
        ]
    )
    db.session.commit()

    resultado = registrar_salida_automatica(db.session, usuario.id, SALIDA)

    assert resultado.codigo == AUTO_AUSENCIA_BLOQUEANTE
    assert RegistroHorario.query.count() == 1


@pytest.mark.parametrize(
    "filas",
    [
        [("salida", ENTRADA)],
        [("entrada", ENTRADA), ("entrada", ENTRADA + timedelta(hours=1))],
        [
            ("entrada", ENTRADA),
            ("salida", ENTRADA + timedelta(hours=1)),
            ("salida", ENTRADA + timedelta(hours=2)),
        ],
        [("pausa", ENTRADA)],
        [("entrada", ENTRADA), ("salida", ENTRADA)],
    ],
)
def test_secuencias_anomalas_no_se_reparan(usuario, filas):
    fichaje = crear_fichaje(usuario)
    for tipo, instante in filas:
        crear_registro(fichaje, tipo, instante)
    db.session.commit()
    cantidad_inicial = RegistroHorario.query.count()

    resultado = registrar_salida_automatica(db.session, usuario.id, SALIDA)

    assert resultado.codigo == AUTO_SECUENCIA_ANOMALA
    assert RegistroHorario.query.count() == cantidad_inicial


def test_timestamp_automatico_debe_ser_posterior_a_entrada(usuario):
    preparar_entrada(usuario)

    resultado = registrar_salida_automatica(db.session, usuario.id, ENTRADA)

    assert resultado.codigo == AUTO_TIMESTAMP_INVALIDO
    assert RegistroHorario.query.count() == 1


def test_timestamp_ingenuo_es_rechazado_antes_de_escribir(usuario):
    preparar_entrada(usuario)

    resultado = registrar_salida_automatica(
        db.session,
        usuario.id,
        datetime(2026, 4, 15, 14, 5),
    )

    assert resultado.codigo == AUTO_TIMESTAMP_INVALIDO
    assert RegistroHorario.query.count() == 1


def test_varios_fichajes_activos_no_eligen_uno_arbitrariamente(usuario):
    preparar_entrada(usuario)
    segundo = crear_fichaje(usuario)
    crear_registro(segundo, "entrada", ENTRADA + timedelta(minutes=1))
    db.session.commit()

    resultado = registrar_salida_automatica(db.session, usuario.id, SALIDA)

    assert resultado.codigo == AUTO_FICHAJES_ACTIVOS_MULTIPLES
    assert Fichaje.query.count() == 2
    assert RegistroHorario.query.filter_by(tipo="salida").count() == 0


def test_cabecera_eliminada_no_se_reutiliza(usuario):
    fichaje = crear_fichaje(usuario, eliminado=True)
    crear_registro(fichaje, "entrada", ENTRADA)
    db.session.commit()

    resultado = registrar_salida_automatica(db.session, usuario.id, SALIDA)

    assert resultado.codigo == AUTO_SIN_FICHAJE_ACTIVO
    assert Fichaje.query.count() == 1
    assert RegistroHorario.query.count() == 1


def test_registro_eliminado_no_participa_ni_se_reactiva(usuario):
    fichaje = crear_fichaje(usuario)
    entrada = crear_registro(fichaje, "entrada", ENTRADA, eliminado=True)
    db.session.commit()

    resultado = registrar_salida_automatica(db.session, usuario.id, SALIDA)

    assert resultado.codigo == AUTO_SIN_TRAMO_ABIERTO
    assert RegistroHorario.query.count() == 1
    assert db.session.get(RegistroHorario, entrada.id).eliminado is True


def test_fallo_de_commit_hace_rollback_y_deja_sesion_reutilizable(
    usuario,
    monkeypatch,
):
    preparar_entrada(usuario)
    rollback_real = db.session.rollback
    rollbacks = []

    def rollback_contado():
        rollbacks.append(True)
        return rollback_real()

    monkeypatch.setattr(db.session, "rollback", rollback_contado)
    monkeypatch.setattr(
        db.session,
        "commit",
        lambda: (_ for _ in ()).throw(RuntimeError("fallo controlado")),
    )

    resultado = registrar_salida_automatica(db.session, usuario.id, SALIDA)

    assert resultado.codigo == AUTO_ERROR_PERSISTENCIA
    assert rollbacks == [True]
    assert RegistroHorario.query.count() == 1
    assert db.session.is_active


def test_usuario_inexistente_devuelve_estado_semantico(usuario):
    resultado = registrar_salida_automatica(db.session, usuario.id + 999, SALIDA)

    assert resultado.codigo == AUTO_USUARIO_INEXISTENTE
    assert Fichaje.query.count() == 0


def test_dos_ejecuciones_con_el_mismo_instante_son_idempotentes(usuario):
    preparar_entrada(usuario)

    primera = registrar_salida_automatica(db.session, usuario.id, SALIDA)
    segunda = registrar_salida_automatica(db.session, usuario.id, SALIDA)

    assert primera.codigo == AUTO_SALIDA_CREADA
    assert segunda.codigo == AUTO_YA_CERRADO
    assert RegistroHorario.query.filter_by(tipo="salida").count() == 1


def test_cabecera_eliminada_se_ignora_si_existe_otra_activa(usuario):
    eliminada = crear_fichaje(usuario, eliminado=True)
    entrada_eliminada = crear_registro(
        eliminada,
        "entrada",
        ENTRADA,
        eliminado=True,
    )
    salida_eliminada = crear_registro(
        eliminada,
        "salida",
        ENTRADA + timedelta(hours=1),
        eliminado=True,
        origen="Auto",
    )
    activa = crear_fichaje(usuario)
    crear_registro(activa, "entrada", ENTRADA)
    db.session.commit()
    historico = {
        entrada_eliminada.id: (
            entrada_eliminada.eliminado,
            entrada_eliminada.timestamp,
        ),
        salida_eliminada.id: (
            salida_eliminada.eliminado,
            salida_eliminada.timestamp,
        ),
    }

    resultado = registrar_salida_automatica(db.session, usuario.id, SALIDA)

    assert resultado.codigo == AUTO_SALIDA_CREADA
    assert db.session.get(Fichaje, eliminada.id).eliminado is True
    assert db.session.get(Fichaje, activa.id).eliminado is False
    assert RegistroHorario.query.filter_by(
        fichaje_id=activa.id,
        tipo="salida",
        eliminado=False,
    ).count() == 1
    for registro_id, valores in historico.items():
        registro = db.session.get(RegistroHorario, registro_id)
        assert (registro.eliminado, registro.timestamp) == valores


def test_salida_manual_previa_no_se_modifica_ni_se_duplica(usuario):
    fichaje = crear_fichaje(usuario)
    entrada = crear_registro(fichaje, "entrada", ENTRADA, origen="Remoto")
    salida_manual = crear_registro(
        fichaje,
        "salida",
        ENTRADA + timedelta(hours=5),
        origen="Remoto",
    )
    db.session.commit()
    valores_originales = (
        salida_manual.id,
        salida_manual.timestamp,
        salida_manual.origen,
        salida_manual.creado_por_admin,
        salida_manual.eliminado,
    )

    resultado = registrar_salida_automatica(db.session, usuario.id, SALIDA)

    assert resultado.codigo == AUTO_YA_CERRADO
    assert RegistroHorario.query.filter_by(tipo="salida").count() == 1
    salida_actual = db.session.get(RegistroHorario, salida_manual.id)
    assert (
        salida_actual.id,
        salida_actual.timestamp,
        salida_actual.origen,
        salida_actual.creado_por_admin,
        salida_actual.eliminado,
    ) == valores_originales
    assert (
        analizar_secuencia([entrada, salida_actual], fichaje.fecha).entrada_abierta
        is None
    )


def test_timestamp_utc_se_convierte_a_madrid_antes_de_derivar_fecha(usuario):
    instante_utc = datetime(2026, 4, 15, 23, 30, tzinfo=timezone.utc)
    instante_madrid = instante_utc.astimezone(MADRID)
    entrada_madrid = MADRID.localize(datetime(2026, 4, 16, 0, 30))
    fichaje = Fichaje(
        usuario_id=usuario.id,
        fecha=instante_madrid.date(),
        fecha_creacion=entrada_madrid,
        creado_por_admin=False,
        eliminado=False,
    )
    db.session.add(fichaje)
    db.session.flush()
    crear_registro(fichaje, "entrada", entrada_madrid)
    db.session.commit()

    resultado = registrar_salida_automatica(
        db.session,
        usuario.id,
        instante_utc,
    )

    assert resultado.codigo == AUTO_SALIDA_CREADA
    assert resultado.instante == instante_madrid.replace(microsecond=0)
    assert resultado.instante.tzinfo.zone == "Europe/Madrid"
    assert resultado.fecha == instante_madrid.date() == fichaje.fecha
    salida = RegistroHorario.query.filter_by(tipo="salida").one()
    assert salida.timestamp == instante_madrid.replace(tzinfo=None, microsecond=0)
    assert salida.timestamp > entrada_madrid.replace(tzinfo=None)


def test_normalizacion_a_segundos_rechaza_colision_con_entrada(usuario):
    preparar_entrada(usuario)
    instante_mismo_segundo = ENTRADA.replace(microsecond=999999)

    resultado = registrar_salida_automatica(
        db.session,
        usuario.id,
        instante_mismo_segundo,
    )

    assert resultado.codigo == AUTO_TIMESTAMP_INVALIDO
    assert resultado.instante.microsecond == 0
    assert RegistroHorario.query.filter_by(tipo="salida").count() == 0


def test_fallo_durante_flush_implicito_revierte_la_salida(usuario, monkeypatch):
    preparar_entrada(usuario)
    rollback_real = db.session.rollback
    rollbacks = []
    intentos_flush = []

    def rollback_contado():
        rollbacks.append(True)
        return rollback_real()

    def fallar_al_insertar_salida(_mapper, _connection, registro):
        if registro.tipo == "salida" and registro.origen == "Auto":
            intentos_flush.append(registro)
            raise RuntimeError("fallo controlado durante flush")

    monkeypatch.setattr(db.session, "rollback", rollback_contado)
    event.listen(RegistroHorario, "before_insert", fallar_al_insertar_salida)
    try:
        resultado = registrar_salida_automatica(db.session, usuario.id, SALIDA)
    finally:
        event.remove(RegistroHorario, "before_insert", fallar_al_insertar_salida)

    assert resultado.codigo == AUTO_ERROR_PERSISTENCIA
    assert len(intentos_flush) == 1
    assert rollbacks == [True]
    assert [registro.tipo for registro in RegistroHorario.query.all()] == ["entrada"]
    assert not db.session.new
    assert db.session.is_active
    db.session.commit()
    assert RegistroHorario.query.filter_by(tipo="salida").count() == 0


def test_reintento_tras_fallo_de_flush_crea_una_unica_salida(usuario):
    fichaje, _ = preparar_entrada(usuario)
    intentos_flush = []

    def fallar_al_insertar_salida(_mapper, _connection, registro):
        if registro.tipo == "salida" and registro.origen == "Auto":
            intentos_flush.append(registro)
            raise RuntimeError("fallo controlado durante flush")

    event.listen(RegistroHorario, "before_insert", fallar_al_insertar_salida)
    try:
        fallido = registrar_salida_automatica(db.session, usuario.id, SALIDA)
    finally:
        event.remove(RegistroHorario, "before_insert", fallar_al_insertar_salida)

    reintento = registrar_salida_automatica(db.session, usuario.id, SALIDA)

    assert fallido.codigo == AUTO_ERROR_PERSISTENCIA
    assert len(intentos_flush) == 1
    assert reintento.codigo == AUTO_SALIDA_CREADA
    registros = RegistroHorario.query.order_by(
        RegistroHorario.timestamp,
        RegistroHorario.id,
    ).all()
    assert [registro.tipo for registro in registros] == ["entrada", "salida"]
    assert (
        RegistroHorario.query.filter_by(tipo="salida", eliminado=False).count()
        == 1
    )
    assert analizar_secuencia(registros, fichaje.fecha).entrada_abierta is None
    assert not db.session.new


def test_servicio_es_propietario_de_una_transaccion_con_sesion_limpia(usuario):
    usuario_id = usuario.id
    db.session.rollback()
    assert not db.session().in_transaction()

    omision = registrar_salida_automatica(db.session, usuario_id, SALIDA)

    assert omision.codigo == AUTO_SIN_FICHAJE_ACTIVO
    assert not db.session().in_transaction()

    preparar_entrada(usuario)
    assert not db.session().in_transaction()
    creada = registrar_salida_automatica(db.session, usuario_id, SALIDA)

    assert creada.codigo == AUTO_SALIDA_CREADA
    assert not db.session().in_transaction()

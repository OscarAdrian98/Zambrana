from datetime import date, datetime, time
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytz

from app import db
from app.services.fichajes import (
    AUTO_ERROR_PERSISTENCIA,
    AUTO_FICHAJES_ACTIVOS_MULTIPLES,
    AUTO_SALIDA_CREADA,
    AUTO_SECUENCIA_ANOMALA,
    AUTO_SIN_FICHAJE_ACTIVO,
    AUTO_TIMESTAMP_INVALIDO,
    AUTO_YA_CERRADO,
    ResultadoSalidaAutomatica,
)
import autofichar_salidas


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FECHA = date(2026, 4, 15)
MADRID = pytz.timezone("Europe/Madrid")


def resultado(codigo, hora=time(14, 5)):
    instante = MADRID.localize(datetime.combine(FECHA, hora))
    return ResultadoSalidaAutomatica(codigo, instante, FECHA)


def test_script_delega_candidato_elegible_en_servicio(usuario, monkeypatch):
    entrada = SimpleNamespace(timestamp=datetime.combine(FECHA, time(8, 0)))
    llamadas = []

    monkeypatch.setattr(
        autofichar_salidas,
        "obtener_entrada_abierta_para_autofichaje",
        lambda session, usuario_id, fecha: entrada,
    )

    def registrar(session, usuario_id, instante):
        llamadas.append((session, usuario_id, instante))
        return ResultadoSalidaAutomatica(AUTO_SALIDA_CREADA, instante, instante.date())

    monkeypatch.setattr(autofichar_salidas, "registrar_salida_automatica", registrar)

    autofichar_salidas.autofichar_salidas(
        FECHA,
        time(14, 5),
        excluidos=[],
    )

    assert len(llamadas) == 1
    session, usuario_id, instante = llamadas[0]
    assert session is db.session
    assert usuario_id == usuario.id
    assert instante == MADRID.localize(datetime.combine(FECHA, time(14, 5)))


def test_sin_entrada_delega_para_obtener_resultado_semantico(usuario, monkeypatch):
    llamadas = []
    monkeypatch.setattr(
        autofichar_salidas,
        "obtener_entrada_abierta_para_autofichaje",
        lambda *_args: None,
    )

    def registrar(_session, usuario_id, instante):
        llamadas.append((usuario_id, instante))
        return ResultadoSalidaAutomatica(
            AUTO_SIN_FICHAJE_ACTIVO,
            instante,
            instante.date(),
        )

    monkeypatch.setattr(autofichar_salidas, "registrar_salida_automatica", registrar)

    autofichar_salidas.autofichar_salidas(FECHA, time(7, 0), excluidos=[])

    assert llamadas == [
        (usuario.id, MADRID.localize(datetime.combine(FECHA, time(14, 5))))
    ]


def test_antes_del_horario_no_invoca_operacion_automatica(
    usuario,
    monkeypatch,
    caplog,
):
    entrada = SimpleNamespace(timestamp=datetime.combine(FECHA, time(16, 0)))
    monkeypatch.setattr(
        autofichar_salidas,
        "obtener_entrada_abierta_para_autofichaje",
        lambda *_args: entrada,
    )
    monkeypatch.setattr(
        autofichar_salidas,
        "registrar_salida_automatica",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("No debe llamar al servicio antes del horario")
        ),
    )
    caplog.set_level(logging.INFO)

    autofichar_salidas.autofichar_salidas(FECHA, time(19, 0), excluidos=[])

    assert "aún no cumple hora de autofichaje" in caplog.text


def test_script_no_contiene_escritura_directa_de_salidas():
    source = (PROJECT_ROOT / "autofichar_salidas.py").read_text(encoding="utf-8")

    assert "RegistroHorario(" not in source
    assert "db.session.add(" not in source
    assert "db.session.commit(" not in source
    assert 'origen="Auto"' not in source
    assert "registrar_salida_automatica(" in source


def test_resultado_creado_conserva_formato_de_log(caplog):
    caplog.set_level(logging.INFO)

    autofichar_salidas.registrar_log_resultado(
        "Empleado ficticio",
        resultado(AUTO_SALIDA_CREADA),
    )

    assert "Salida autofichada para Empleado ficticio" in caplog.text
    assert "14:05:00" in caplog.text


def test_omision_idempotente_no_se_registra_como_error(caplog):
    caplog.set_level(logging.INFO)

    autofichar_salidas.registrar_log_resultado(
        "Empleado ficticio",
        resultado(AUTO_YA_CERRADO),
    )

    assert "ya tenía cerrado el tramo" in caplog.text
    assert not [record for record in caplog.records if record.levelno >= logging.WARNING]


def test_anomalias_se_diferencian_como_warning(caplog):
    caplog.set_level(logging.INFO)

    for codigo in (
        AUTO_FICHAJES_ACTIVOS_MULTIPLES,
        AUTO_SECUENCIA_ANOMALA,
        AUTO_TIMESTAMP_INVALIDO,
    ):
        autofichar_salidas.registrar_log_resultado(
            "Empleado ficticio",
            resultado(codigo),
        )

    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 3
    assert "varios fichajes activos" in caplog.text
    assert "secuencia horaria anómala" in caplog.text
    assert "timestamp automático no válido" in caplog.text


def test_error_de_persistencia_se_registra_como_error_tecnico(caplog):
    caplog.set_level(logging.INFO)

    autofichar_salidas.registrar_log_resultado(
        "Empleado ficticio",
        resultado(AUTO_ERROR_PERSISTENCIA),
    )

    assert "Error técnico al autofichar" in caplog.text
    assert any(record.levelno == logging.ERROR for record in caplog.records)


@pytest.mark.parametrize(
    ("fecha", "hora_objetivo", "offset_esperado"),
    [
        (date(2026, 3, 29), time(14, 5), 2),
        (date(2026, 10, 25), time(20, 5), 1),
    ],
)
def test_instante_programado_es_madrid_consciente_en_cambios_dst(
    fecha,
    hora_objetivo,
    offset_esperado,
):
    instante = autofichar_salidas._instante_programado(fecha, hora_objetivo)

    assert instante.tzinfo is not None
    assert instante.tzinfo.zone == "Europe/Madrid"
    assert instante.date() == fecha
    assert instante.time().replace(tzinfo=None) == hora_objetivo
    assert instante.utcoffset().total_seconds() == offset_esperado * 3600

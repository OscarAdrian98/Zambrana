import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import db
from app.models import Ausencia, Fichaje, RegistroHorario
from app.services.ausencias import (
    agrupar_ausencias_por_usuario,
    ahora_madrid,
    existe_ausencia_bloqueante,
    fecha_hoy_madrid,
    usuarios_con_ausencia_bloqueante,
)
import autofichar_salidas
import avisar_fichajes_discord
import generar_avisos_json
import send_push_notifications


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FECHA = date(2026, 7, 21)


def ausencia_simple(
    identificador,
    tipo="Baja",
    fecha=FECHA,
    usuario_id=1,
):
    return SimpleNamespace(
        id=identificador,
        tipo=tipo,
        fecha=fecha,
        usuario_id=usuario_id,
    )


def guardar_ausencias(usuario, tipos, fecha=FECHA):
    filas = []
    for tipo in tipos:
        fila = Ausencia(
            usuario_id=usuario.id,
            fecha=fecha,
            tipo=tipo,
            observaciones=None,
            creado_por_admin=False,
        )
        db.session.add(fila)
        filas.append(fila)
    db.session.commit()
    return filas


def preparar_tramo_unico(monkeypatch, modulo, usuario_id):
    monkeypatch.setattr(modulo, "EXCLUIDOS", [])
    monkeypatch.setattr(
        modulo,
        "TRAMOS",
        {
            "mañana": {
                "inicio": time(6, 0),
                "fin": time(14, 30),
                "aviso_entrada": time(10, 1),
                "aviso_salida": time(14, 1),
                "usuarios": [usuario_id],
            }
        },
    )


def instante_operativo():
    return generar_avisos_json.zona_es.localize(
        datetime(2026, 7, 21, 10, 2)
    )


def contar_selects_ausencias(app, accion):
    from sqlalchemy import event

    consultas = []

    def registrar(_connection, _cursor, statement, *_args):
        if "from ausencias" in statement.lower():
            consultas.append(statement)

    event.listen(db.engine, "before_cursor_execute", registrar)
    try:
        accion()
    finally:
        event.remove(db.engine, "before_cursor_execute", registrar)
    return len(consultas)


def test_sin_ausencias_no_bloquea():
    assert existe_ausencia_bloqueante([], FECHA) is False


@pytest.mark.parametrize(
    "tipo",
    ["Medico", "Médico", "medico", "  mÉdIcO  "],
)
def test_aliases_medicos_no_bloquean(tipo):
    filas = [ausencia_simple(1, tipo=tipo)]
    assert existe_ausencia_bloqueante(filas, FECHA) is False


def test_varias_citas_medicas_no_bloquean():
    filas = [
        ausencia_simple(2, tipo="Médico"),
        ausencia_simple(1, tipo="medico"),
    ]
    assert existe_ausencia_bloqueante(filas, FECHA) is False


def test_ausencia_ordinaria_bloquea():
    assert existe_ausencia_bloqueante(
        [ausencia_simple(1, tipo="Vacaciones")],
        FECHA,
    )


def test_medica_y_bloqueante_prioriza_bloqueante():
    filas = [
        ausencia_simple(5, tipo="Medico"),
        ausencia_simple(2, tipo="Baja"),
    ]
    assert existe_ausencia_bloqueante(filas, FECHA)


def test_filas_pasadas_y_futuras_no_afectan():
    filas = [
        ausencia_simple(1, fecha=FECHA - timedelta(days=1)),
        ausencia_simple(2, fecha=FECHA + timedelta(days=1)),
    ]
    assert existe_ausencia_bloqueante(filas, FECHA) is False


def test_entrada_desordenada_produce_la_misma_decision():
    filas = [
        ausencia_simple(20, tipo="Médico"),
        ausencia_simple(3, tipo="Enfermedad"),
        ausencia_simple(10, tipo="Medico"),
    ]
    assert existe_ausencia_bloqueante(filas, FECHA)
    assert existe_ausencia_bloqueante(list(reversed(filas)), FECHA)


def test_tipo_desconocido_bloquea_conservadoramente():
    filas = [ausencia_simple(1, tipo="Tipo histórico desconocido")]
    assert existe_ausencia_bloqueante(filas, FECHA)


def test_agrupacion_filtra_fecha_y_separa_usuarios():
    filas = [
        ausencia_simple(1, usuario_id=10, tipo="Medico"),
        ausencia_simple(2, usuario_id=10, tipo="Baja"),
        ausencia_simple(3, usuario_id=20, tipo="Médico"),
        ausencia_simple(
            4,
            usuario_id=30,
            fecha=FECHA + timedelta(days=1),
        ),
    ]
    agrupadas = agrupar_ausencias_por_usuario(filas, FECHA)
    assert set(agrupadas) == {10, 20}
    assert usuarios_con_ausencia_bloqueante(filas, FECHA) == {10}


@pytest.mark.parametrize(
    ("instante_utc", "fecha_esperada"),
    [
        (datetime(2026, 7, 20, 21, 59, tzinfo=timezone.utc), date(2026, 7, 20)),
        (datetime(2026, 7, 20, 22, 1, tzinfo=timezone.utc), date(2026, 7, 21)),
        (datetime(2026, 1, 1, 22, 59, tzinfo=timezone.utc), date(2026, 1, 1)),
        (datetime(2026, 1, 1, 23, 1, tzinfo=timezone.utc), date(2026, 1, 2)),
        (datetime(2026, 3, 29, 0, 30, tzinfo=timezone.utc), date(2026, 3, 29)),
        (datetime(2026, 10, 25, 1, 30, tzinfo=timezone.utc), date(2026, 10, 25)),
    ],
)
def test_fecha_madrid_respeta_medianoche_y_cambios_horarios(
    instante_utc,
    fecha_esperada,
):
    assert fecha_hoy_madrid(instante_utc) == fecha_esperada


def test_instante_utc_se_convierte_antes_de_calcular_hora_y_semana():
    instante = datetime(2026, 7, 20, 22, 30, tzinfo=timezone.utc)
    convertido = ahora_madrid(instante)
    assert convertido.date() == date(2026, 7, 21)
    assert convertido.time().replace(tzinfo=None) == time(0, 30)
    assert convertido.weekday() == 1


@pytest.mark.parametrize(
    ("filas", "esperado"),
    [
        ([], True),
        ([ausencia_simple(1, tipo="Medico")], True),
        ([ausencia_simple(1, tipo=" Médico ")], True),
        ([ausencia_simple(1, tipo="Baja")], False),
        (
            [
                ausencia_simple(1, tipo="Medico"),
                ausencia_simple(2, tipo="Vacaciones"),
            ],
            False,
        ),
        (
            [ausencia_simple(1, fecha=FECHA + timedelta(days=1))],
            True,
        ),
    ],
)
def test_decisiones_puras_de_autofichaje_y_aviso(filas, esperado):
    assert autofichar_salidas.debe_autofichar_usuario(filas, FECHA) is esperado
    assert generar_avisos_json.debe_generar_aviso_usuario(
        filas,
        FECHA,
    ) is esperado


def test_planificacion_pura_no_toca_base_archivos_ni_comunicaciones(
    tmp_path,
    monkeypatch,
):
    class DatabaseForbidden:
        def __getattr__(self, name):
            raise AssertionError(f"Acceso inesperado a base: {name}")

    monkeypatch.setattr(autofichar_salidas, "db", DatabaseForbidden())
    monkeypatch.setattr(generar_avisos_json, "db", DatabaseForbidden())
    monkeypatch.chdir(tmp_path)

    filas = [ausencia_simple(1, tipo="Médico")]
    assert autofichar_salidas.debe_autofichar_usuario(filas, FECHA)
    assert generar_avisos_json.debe_generar_aviso_usuario(filas, FECHA)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("tipos_hoy", "tipos_otro_dia", "debe_crear_salida"),
    [
        ([], [], True),
        (["Medico"], [], True),
        (["  Médico "], [], True),
        (["Baja"], [], False),
        (["Medico", "Vacaciones"], [], False),
        ([], ["Baja"], True),
    ],
)
def test_autofichaje_respeta_regla_central_en_sqlite(
    app,
    usuario,
    tipos_hoy,
    tipos_otro_dia,
    debe_crear_salida,
):
    guardar_ausencias(usuario, tipos_hoy, FECHA)
    guardar_ausencias(
        usuario,
        tipos_otro_dia,
        FECHA + timedelta(days=1),
    )
    fichaje = Fichaje(
        usuario_id=usuario.id,
        fecha=FECHA,
        fecha_creacion=datetime.combine(FECHA, time(8, 0)),
        creado_por_admin=False,
        eliminado=False,
    )
    db.session.add(fichaje)
    db.session.flush()
    db.session.add(
        RegistroHorario(
            fichaje_id=fichaje.id,
            tipo="entrada",
            timestamp=datetime.combine(FECHA, time(8, 0)),
            creado_por_admin=False,
            eliminado=False,
            origen="Tienda",
        )
    )
    db.session.commit()

    autofichar_salidas.autofichar_salidas(
        FECHA,
        time(14, 5),
        excluidos=[],
    )

    salidas = RegistroHorario.query.filter_by(
        fichaje_id=fichaje.id,
        tipo="salida",
    ).count()
    assert salidas == int(debe_crear_salida)


def test_autofichaje_consulta_ausencias_una_sola_vez(app, usuario):
    assert contar_selects_ausencias(
        app,
        lambda: autofichar_salidas.autofichar_salidas(
            FECHA,
            time(7, 0),
            excluidos=[],
        ),
    ) == 1


@pytest.mark.parametrize(
    ("tipos_hoy", "tipos_otro_dia", "debe_generar"),
    [
        ([], [], True),
        (["Medico"], [], True),
        (["  Médico "], [], True),
        (["Baja"], [], False),
        (["Medico", "Enfermedad"], [], False),
        ([], ["Vacaciones"], True),
    ],
)
def test_generador_json_respeta_ausencias_y_conserva_esquema(
    app,
    usuario,
    tmp_path,
    monkeypatch,
    tipos_hoy,
    tipos_otro_dia,
    debe_generar,
):
    guardar_ausencias(usuario, tipos_hoy, FECHA)
    guardar_ausencias(
        usuario,
        tipos_otro_dia,
        FECHA + timedelta(days=1),
    )
    preparar_tramo_unico(monkeypatch, generar_avisos_json, usuario.id)
    monkeypatch.setattr(generar_avisos_json, "es_festivo", lambda _fecha: False)
    destino = tmp_path / "avisos.json"
    if not debe_generar:
        destino.write_text("[]", encoding="utf-8")

    avisos = generar_avisos_json.generar_avisos(
        ahora=instante_operativo(),
        local_file=destino,
    )

    assert bool(avisos) is debe_generar
    assert destino.exists() is debe_generar
    if debe_generar:
        contenido = json.loads(destino.read_text(encoding="utf-8"))
        assert contenido == avisos
        assert set(contenido[0]) == {
            "usuario_id",
            "email",
            "nombre",
            "tipo",
            "tramo",
            "fecha",
            "mensaje",
        }
        assert contenido[0]["fecha"] == FECHA.isoformat()
        assert contenido[0]["tipo"] == "entrada"

    assert not (PROJECT_ROOT / "avisos.json").exists()


def test_generador_consulta_ausencias_una_sola_vez(
    app,
    usuario,
    tmp_path,
    monkeypatch,
):
    preparar_tramo_unico(monkeypatch, generar_avisos_json, usuario.id)
    monkeypatch.setattr(generar_avisos_json, "es_festivo", lambda _fecha: False)
    assert contar_selects_ausencias(
        app,
        lambda: generar_avisos_json.generar_avisos(
            ahora=instante_operativo(),
            local_file=tmp_path / "avisos.json",
        ),
    ) == 1


@pytest.mark.parametrize(
    ("tipos_hoy", "numero_mensajes"),
    [
        ([], 1),
        (["Medico"], 1),
        ([" Médico "], 1),
        (["Baja"], 0),
        (["Medico", "Asuntos propios"], 0),
    ],
)
def test_discord_recalcula_ausencias_sin_enviar_http(
    app,
    usuario,
    monkeypatch,
    tipos_hoy,
    numero_mensajes,
):
    guardar_ausencias(usuario, tipos_hoy, FECHA)
    preparar_tramo_unico(monkeypatch, avisar_fichajes_discord, usuario.id)
    mensajes = []
    monkeypatch.setattr(
        avisar_fichajes_discord,
        "enviar_discord",
        mensajes.append,
    )
    monkeypatch.setattr(
        avisar_fichajes_discord.requests,
        "post",
        lambda *_args, **_kwargs: pytest.fail("No debe existir HTTP real"),
    )

    avisar_fichajes_discord.procesar_avisos(
        ahora=instante_operativo(),
    )

    assert len(mensajes) == numero_mensajes
    if mensajes:
        assert "entrada" in mensajes[0]
        assert FECHA.strftime("%d/%m/%Y") in mensajes[0]


def test_push_solo_consume_json_y_no_envia(tmp_path, monkeypatch):
    destino = tmp_path / "avisos.json"
    avisos = [{"email": "empleado@example.test", "mensaje": "Aviso ficticio"}]
    generar_avisos_json.guardar_avisos(avisos, destino)
    monkeypatch.setattr(
        send_push_notifications,
        "webpush",
        lambda *_args, **_kwargs: pytest.fail("No debe enviarse push"),
    )

    assert send_push_notifications.cargar_avisos(destino) == avisos
    assert send_push_notifications.cargar_avisos(tmp_path / "ausente.json") == []

import inspect
from datetime import date, datetime, time

import pytest

from app import db
from app.models import Fichaje, RegistroHorario
from app.services.fichajes import (
    LECTURA_FICHAJE_ACTIVO_MULTIPLE,
    LECTURA_FICHAJE_ACTIVO_NINGUNO,
    LECTURA_FICHAJE_ACTIVO_UNICO,
    resolver_fichaje_activo,
)
import app.routes as routes
import autofichar_salidas
import avisar_fichajes_discord
import generar_avisos_json


FECHA_OPERATIVA = date(2026, 7, 21)


def login(client, usuario):
    return client.post(
        "/login",
        data={
            "email": usuario.email,
            "password": "password-correcta",
        },
    )


def crear_fichaje(
    usuario_id,
    fecha,
    *,
    eliminado=False,
    registros=(),
):
    fichaje = Fichaje(
        usuario_id=usuario_id,
        fecha=fecha,
        fecha_creacion=datetime.combine(fecha, time(7, 0)),
        creado_por_admin=False,
        eliminado=eliminado,
    )
    db.session.add(fichaje)
    db.session.flush()
    for tipo, hora in registros:
        db.session.add(
            RegistroHorario(
                fichaje_id=fichaje.id,
                tipo=tipo,
                timestamp=datetime.combine(fecha, hora),
                creado_por_admin=False,
                eliminado=False,
                origen="Tienda",
            )
        )
    return fichaje


def crear_ambiguedad(usuario_id, fecha):
    primero = crear_fichaje(
        usuario_id,
        fecha,
        registros=(("entrada", time(8, 11)),),
    )
    segundo = crear_fichaje(
        usuario_id,
        fecha,
        registros=(("entrada", time(17, 22)),),
    )
    db.session.commit()
    return primero, segundo


def configurar_tramo_unico(monkeypatch, modulo, usuario_id):
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


def test_resolvedor_distingue_cero_y_usuario_inexistente_sin_escribir(
    app,
    usuario,
    monkeypatch,
):
    cantidad_fichajes = Fichaje.query.count()
    monkeypatch.setattr(
        db.session,
        "commit",
        lambda: pytest.fail("El resolvedor no debe hacer commit"),
    )
    monkeypatch.setattr(
        db.session,
        "rollback",
        lambda: pytest.fail("El resolvedor no debe hacer rollback"),
    )

    resultado = resolver_fichaje_activo(
        db.session,
        usuario_id=usuario.id,
        fecha=FECHA_OPERATIVA,
    )
    inexistente = resolver_fichaje_activo(
        db.session,
        usuario_id=usuario.id + 9999,
        fecha=FECHA_OPERATIVA,
    )

    assert resultado.estado == LECTURA_FICHAJE_ACTIVO_NINGUNO
    assert resultado.fichaje is None
    assert resultado.cantidad_detectada == 0
    assert inexistente.estado == LECTURA_FICHAJE_ACTIVO_NINGUNO
    assert Fichaje.query.count() == cantidad_fichajes
    assert not db.session.new
    assert not db.session.dirty
    assert not db.session.deleted


def test_resolvedor_devuelve_la_unica_cabecera_activa_e_ignora_eliminadas(
    app,
    usuario,
):
    activa = crear_fichaje(usuario.id, FECHA_OPERATIVA)
    crear_fichaje(usuario.id, FECHA_OPERATIVA, eliminado=True)
    crear_fichaje(usuario.id, FECHA_OPERATIVA.replace(day=22))
    db.session.commit()

    resultado = resolver_fichaje_activo(
        db.session,
        usuario_id=usuario.id,
        fecha=FECHA_OPERATIVA,
    )

    assert resultado.estado == LECTURA_FICHAJE_ACTIVO_UNICO
    assert resultado.fichaje.id == activa.id
    assert resultado.cantidad_detectada == 1


def test_resolvedor_con_solo_eliminadas_devuelve_cero(app, usuario):
    crear_fichaje(usuario.id, FECHA_OPERATIVA, eliminado=True)
    db.session.commit()

    resultado = resolver_fichaje_activo(
        db.session,
        usuario_id=usuario.id,
        fecha=FECHA_OPERATIVA,
    )

    assert resultado.estado == LECTURA_FICHAJE_ACTIVO_NINGUNO
    assert resultado.fichaje is None


@pytest.mark.parametrize("cantidad", [2, 3])
def test_resolvedor_no_devuelve_objeto_con_multiples(app, usuario, cantidad):
    for _indice in range(cantidad):
        crear_fichaje(usuario.id, FECHA_OPERATIVA)
    db.session.commit()
    ids_antes = [fila.id for fila in Fichaje.query.order_by(Fichaje.id).all()]

    resultado = resolver_fichaje_activo(
        db.session,
        usuario_id=usuario.id,
        fecha=FECHA_OPERATIVA,
    )

    assert resultado.estado == LECTURA_FICHAJE_ACTIVO_MULTIPLE
    assert resultado.fichaje is None
    assert resultado.cantidad_detectada == 2
    assert [fila.id for fila in Fichaje.query.order_by(Fichaje.id).all()] == ids_antes
    assert not db.session.new
    assert not db.session.dirty
    assert not db.session.deleted


@pytest.mark.parametrize(
    ("usuario_id", "fecha"),
    [
        (None, FECHA_OPERATIVA),
        (0, FECHA_OPERATIVA),
        (True, FECHA_OPERATIVA),
        (1, None),
        (1, "2026-07-21"),
        (1, datetime(2026, 7, 21, 0, 0)),
    ],
)
def test_resolvedor_rechaza_entradas_invalidas(app, usuario_id, fecha):
    with pytest.raises(ValueError):
        resolver_fichaje_activo(
            db.session,
            usuario_id=usuario_id,
            fecha=fecha,
        )


def test_resolvedor_no_contiene_transacciones_ni_bloqueos():
    fuente = inspect.getsource(resolver_fichaje_activo)

    for patron in ("commit(", "rollback(", "flush(", "for_update", "with_for_update"):
        assert patron not in fuente
    assert ".limit(2)" in fuente


def test_rutas_personales_exponen_incidencia_sin_elegir_horas(
    client,
    usuario,
):
    crear_ambiguedad(usuario.id, date.today())
    login(client, usuario)

    inicio = client.get("/fichar")
    control = client.get("/control-horario")
    api = client.get("/api/debo_fichar")

    assert inicio.status_code == 200
    assert control.status_code == 200
    assert api.status_code == 200
    html_inicio = inicio.get_data(as_text=True)
    html_control = control.get_data(as_text=True)
    assert "Incidencia en el fichaje de hoy" in html_inicio
    assert "Contacta con administración" in html_inicio
    assert "Incidencia en el fichaje de hoy" in html_control
    assert "Contacta con administración" in html_control
    assert "08:11" not in html_control
    assert "17:22" not in html_control
    assert api.get_json() == {
        "debo_fichar": False,
        "estado": "incidencia",
        "codigo": "fichajes_activos_multiples",
    }


def test_dashboard_distingue_incidencia_y_no_muestra_horas_arbitrarias(
    client,
    administrador,
    usuario,
):
    crear_ambiguedad(usuario.id, date.today())
    login(client, administrador)

    respuesta = client.get("/admin/dashboard")
    html = respuesta.get_data(as_text=True)
    inicio_fila = html.index(f'data-usuario-id="{usuario.id}"')
    fin_fila = html.index("</tr>", inicio_fila)
    fila = html[inicio_fila:fin_fila]

    assert respuesta.status_code == 200
    assert "Incidencia: múltiples fichajes" in fila
    assert "Revisar historial" in fila
    assert "08:11" not in fila
    assert "17:22" not in fila
    assert "En curso" not in fila


def test_generador_json_omite_aviso_ambiguo_y_no_deja_datos(
    app,
    usuario,
    tmp_path,
    monkeypatch,
    caplog,
):
    crear_ambiguedad(usuario.id, FECHA_OPERATIVA)
    configurar_tramo_unico(monkeypatch, generar_avisos_json, usuario.id)
    monkeypatch.setattr(generar_avisos_json, "es_festivo", lambda _fecha: False)
    destino = tmp_path / "avisos.json"
    destino.write_text('[{"dato": "obsoleto"}]', encoding="utf-8")

    avisos = generar_avisos_json.generar_avisos(
        ahora=instante_operativo(),
        local_file=destino,
    )

    assert avisos == []
    assert not destino.exists()
    assert generar_avisos_json.estado_tramo(
        usuario.id,
        FECHA_OPERATIVA,
        "mañana",
    ) == "incidencia"
    assert caplog.text.count("FICHAJES_ACTIVOS_MULTIPLES") == 1
    assert usuario.email not in caplog.text
    assert usuario.nombre not in caplog.text


def test_discord_omite_aviso_ambiguo_sin_http(
    app,
    usuario,
    monkeypatch,
    caplog,
):
    crear_ambiguedad(usuario.id, FECHA_OPERATIVA)
    configurar_tramo_unico(monkeypatch, avisar_fichajes_discord, usuario.id)
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

    avisar_fichajes_discord.procesar_avisos(ahora=instante_operativo())

    assert mensajes == []
    assert avisar_fichajes_discord.estado_tramo(
        usuario.id,
        FECHA_OPERATIVA,
        "mañana",
    ) == "incidencia"
    assert caplog.text.count("FICHAJES_ACTIVOS_MULTIPLES") == 1
    assert usuario.email not in caplog.text


def test_autofichaje_no_preselecciona_una_cabecera_ambigua(
    app,
    usuario,
    caplog,
):
    crear_ambiguedad(usuario.id, FECHA_OPERATIVA)
    registros_antes = RegistroHorario.query.count()

    autofichar_salidas.autofichar_salidas(
        FECHA_OPERATIVA,
        time(14, 5),
        excluidos=[],
    )

    assert RegistroHorario.query.count() == registros_antes
    assert "varios fichajes activos" in caplog.text


def test_lectores_auditados_dependen_del_resolvedor_comun():
    lectores = (
        routes.fichar,
        routes.control_horario,
        routes.api_debo_fichar,
        routes.admin_dashboard,
        generar_avisos_json.estado_tramo,
        avisar_fichajes_discord.estado_tramo,
    )

    for lector in lectores:
        fuente = inspect.getsource(lector)
        assert "resolver_fichaje_activo(" in fuente
        assert "Fichaje.query.filter_by(" not in fuente
        assert "query(Fichaje)" not in fuente

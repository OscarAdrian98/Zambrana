from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytz
from sqlalchemy import select
from sqlalchemy.dialects import mysql, sqlite
from werkzeug.security import generate_password_hash

from app import db
from app.models import Ausencia, Fichaje, RegistroHorario, Usuario
from app.services.fichajes import (
    AUSENCIA_BLOQUEANTE,
    ENTRADA_DUPLICADA,
    ERROR_PERSISTENCIA,
    FICHAJES_ACTIVOS_MULTIPLES,
    OK_ENTRADA,
    OK_SALIDA,
    ORIGEN_INVALIDO,
    SALIDA_DUPLICADA,
    SALIDA_SIN_ENTRADA,
    SECUENCIA_ANOMALA,
    TIPO_INVALIDO,
    ErrorRegistroFichaje,
    _con_bloqueo_si_disponible,
    analizar_secuencia,
    normalizar_origen_usuario,
    normalizar_tipo,
    registrar_fichaje_usuario,
)


MADRID = pytz.timezone("Europe/Madrid")
INSTANTE = MADRID.localize(datetime(2026, 3, 10, 8, 0, 0))


def login(client, usuario):
    return client.post(
        "/login",
        data={"email": usuario.email, "password": "password-correcta"},
    )


def crear_fichaje(usuario, *, eliminado=False, fecha=None):
    fichaje = Fichaje(
        usuario_id=usuario.id,
        fecha=fecha or INSTANTE.date(),
        fecha_creacion=INSTANTE,
        creado_por_admin=False,
        eliminado=eliminado,
    )
    db.session.add(fichaje)
    db.session.flush()
    return fichaje


def crear_registro(
    fichaje,
    tipo,
    hora,
    *,
    origen="Tienda",
    eliminado=False,
    dia=None,
):
    timestamp = MADRID.localize(
        datetime.combine(dia or fichaje.fecha, hora)
    )
    registro = RegistroHorario(
        fichaje_id=fichaje.id,
        tipo=tipo,
        timestamp=timestamp,
        creado_por_admin=False,
        eliminado=eliminado,
        origen=origen,
    )
    db.session.add(registro)
    return registro


def codigo_error(funcion, *args, **kwargs):
    with pytest.raises(ErrorRegistroFichaje) as exc_info:
        funcion(*args, **kwargs)
    return exc_info.value.codigo


@pytest.mark.parametrize(
    ("recibido", "esperado"),
    [("entrada", "entrada"), (" SALIDA ", "salida"), ("EnTrAdA", "entrada")],
)
def test_normalizar_tipo_es_estricto_y_tolerante_en_formato(recibido, esperado):
    assert normalizar_tipo(recibido) == esperado


@pytest.mark.parametrize("recibido", [None, 1, "", "pausa", "<entrada>"])
def test_normalizar_tipo_rechaza_valores_invalidos(recibido):
    assert codigo_error(normalizar_tipo, recibido) == TIPO_INVALIDO


@pytest.mark.parametrize(
    ("recibido", "esperado"),
    [(" tienda ", "Tienda"), ("REMOTO", "Remoto"), ("TiEnDa", "Tienda")],
)
def test_normalizar_origen_usuario_devuelve_valor_canonico(recibido, esperado):
    assert normalizar_origen_usuario(recibido) == esperado


@pytest.mark.parametrize(
    "recibido",
    [None, 1, "", "Auto", "Casa", "Tienda\n", "<b>Tienda</b>", "x" * 21],
)
def test_normalizar_origen_usuario_rechaza_reservados_y_texto_hostil(recibido):
    assert codigo_error(normalizar_origen_usuario, recibido) == ORIGEN_INVALIDO


@pytest.mark.parametrize("dialecto", ["mysql", "mariadb"])
def test_bloqueo_for_update_se_activa_en_mysql_y_mariadb(dialecto):
    session = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name=dialecto))
    )
    statement = _con_bloqueo_si_disponible(session, select(Usuario))

    assert "FOR UPDATE" in str(statement.compile(dialect=mysql.dialect()))


def test_sqlite_no_finge_un_bloqueo_for_update():
    session = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    )
    statement = _con_bloqueo_si_disponible(session, select(Usuario))

    assert "FOR UPDATE" not in str(statement.compile(dialect=sqlite.dialect()))


def test_filtro_bit_y_bloqueo_compilan_para_mysql_sin_is_parametrizado():
    statement = (
        select(RegistroHorario)
        .where(RegistroHorario.eliminado == False)
        .with_for_update()
    )
    sql = str(statement.compile(dialect=mysql.dialect()))

    assert "eliminado = %s" in sql
    assert "eliminado IS %s" not in sql
    assert sql.endswith("FOR UPDATE")


def test_primera_entrada_crea_cabecera_y_registro_con_un_commit(usuario, monkeypatch):
    commit_real = db.session.commit
    commits = []

    def commit_contado():
        commits.append(True)
        return commit_real()

    monkeypatch.setattr(db.session, "commit", commit_contado)
    resultado = registrar_fichaje_usuario(
        db.session,
        usuario.id,
        " ENTRADA ",
        " remoto ",
        ahora=INSTANTE,
    )

    assert resultado.codigo == OK_ENTRADA
    assert resultado.tipo == "entrada"
    assert resultado.origen == "Remoto"
    assert resultado.fecha == INSTANTE.date()
    assert commits == [True]
    fichaje = Fichaje.query.one()
    registro = RegistroHorario.query.one()
    assert fichaje.usuario_id == usuario.id
    assert fichaje.creado_por_admin is False
    assert registro.tipo == "entrada"
    assert registro.origen == "Remoto"
    assert registro.creado_por_admin is False


def test_instante_unico_se_convierte_a_madrid_para_fecha_y_timestamps(usuario):
    utc = datetime(2026, 1, 1, 23, 30, tzinfo=timezone.utc)
    resultado = registrar_fichaje_usuario(
        db.session, usuario.id, "entrada", "Tienda", ahora=utc
    )

    fichaje = Fichaje.query.one()
    registro = RegistroHorario.query.one()
    assert resultado.instante.strftime("%Y-%m-%d %H:%M") == "2026-01-02 00:30"
    assert fichaje.fecha == date(2026, 1, 2)
    assert fichaje.fecha_creacion.strftime("%Y-%m-%d %H:%M") == "2026-01-02 00:30"
    assert registro.timestamp.strftime("%Y-%m-%d %H:%M") == "2026-01-02 00:30"


def test_salida_hereda_origen_y_ignora_origen_enviado(usuario):
    registrar_fichaje_usuario(
        db.session, usuario.id, "entrada", "Remoto", ahora=INSTANTE
    )
    resultado = registrar_fichaje_usuario(
        db.session,
        usuario.id,
        "salida",
        "<origen-manipulado>",
        ahora=INSTANTE + timedelta(hours=1),
    )

    assert resultado.codigo == OK_SALIDA
    assert resultado.origen == "Remoto"
    assert [r.origen for r in RegistroHorario.query.order_by(RegistroHorario.id)] == [
        "Remoto",
        "Remoto",
    ]


def test_salida_admite_auto_solo_como_origen_historico(usuario):
    fichaje = crear_fichaje(usuario)
    crear_registro(fichaje, "entrada", datetime.min.time().replace(hour=8), origen="Auto")
    db.session.commit()

    resultado = registrar_fichaje_usuario(
        db.session,
        usuario.id,
        "salida",
        "Casa",
        ahora=INSTANTE + timedelta(hours=1),
    )

    assert resultado.origen == "Auto"


def test_salida_usa_tienda_para_origen_historico_nulo(usuario):
    fichaje = crear_fichaje(usuario)
    crear_registro(fichaje, "entrada", datetime.min.time().replace(hour=8), origen=None)
    db.session.commit()

    resultado = registrar_fichaje_usuario(
        db.session, usuario.id, "salida", ahora=INSTANTE + timedelta(hours=1)
    )

    assert resultado.origen == "Tienda"


def test_varios_tramos_secuenciales_son_validos(usuario):
    instantes = [
        ("entrada", "Tienda", INSTANTE),
        ("salida", None, INSTANTE + timedelta(hours=1)),
        ("entrada", "Remoto", INSTANTE + timedelta(hours=2)),
        ("salida", None, INSTANTE + timedelta(hours=3)),
    ]
    codigos = [
        registrar_fichaje_usuario(
            db.session, usuario.id, tipo, origen, ahora=instante
        ).codigo
        for tipo, origen, instante in instantes
    ]

    assert codigos == [OK_ENTRADA, OK_SALIDA, OK_ENTRADA, OK_SALIDA]
    assert Fichaje.query.count() == 1
    assert RegistroHorario.query.count() == 4


def test_repeticiones_secuenciales_se_rechazan_sin_escritura(usuario):
    registrar_fichaje_usuario(
        db.session, usuario.id, "entrada", "Tienda", ahora=INSTANTE
    )
    assert codigo_error(
        registrar_fichaje_usuario,
        db.session,
        usuario.id,
        "entrada",
        "Remoto",
        ahora=INSTANTE + timedelta(seconds=1),
    ) == ENTRADA_DUPLICADA
    assert RegistroHorario.query.count() == 1

    registrar_fichaje_usuario(
        db.session,
        usuario.id,
        "salida",
        ahora=INSTANTE + timedelta(seconds=2),
    )
    assert codigo_error(
        registrar_fichaje_usuario,
        db.session,
        usuario.id,
        "salida",
        ahora=INSTANTE + timedelta(seconds=3),
    ) == SALIDA_DUPLICADA
    assert RegistroHorario.query.count() == 2


def test_salida_sin_cabecera_no_crea_nada(usuario):
    assert codigo_error(
        registrar_fichaje_usuario,
        db.session,
        usuario.id,
        "salida",
        ahora=INSTANTE,
    ) == SALIDA_SIN_ENTRADA
    assert Fichaje.query.count() == 0
    assert RegistroHorario.query.count() == 0


def test_cabecera_activa_vacia_admite_entrada_pero_no_salida(usuario):
    crear_fichaje(usuario)
    db.session.commit()

    assert codigo_error(
        registrar_fichaje_usuario,
        db.session,
        usuario.id,
        "salida",
        ahora=INSTANTE,
    ) == SALIDA_SIN_ENTRADA
    resultado = registrar_fichaje_usuario(
        db.session, usuario.id, "entrada", "Tienda", ahora=INSTANTE
    )
    assert resultado.codigo == OK_ENTRADA
    assert Fichaje.query.count() == 1


def test_fichaje_y_registro_eliminados_no_participan(usuario):
    borrado = crear_fichaje(usuario, eliminado=True)
    crear_registro(borrado, "entrada", datetime.min.time().replace(hour=7))
    activo = crear_fichaje(usuario)
    crear_registro(
        activo,
        "entrada",
        datetime.min.time().replace(hour=7, minute=30),
        eliminado=True,
    )
    db.session.commit()

    resultado = registrar_fichaje_usuario(
        db.session, usuario.id, "entrada", "Remoto", ahora=INSTANTE
    )

    assert resultado.codigo == OK_ENTRADA
    assert Fichaje.query.count() == 2
    assert RegistroHorario.query.filter_by(eliminado=False).count() == 2


def test_varias_cabeceras_activas_se_rechazan_sin_corregir(usuario):
    crear_fichaje(usuario)
    crear_fichaje(usuario)
    db.session.commit()

    assert codigo_error(
        registrar_fichaje_usuario,
        db.session,
        usuario.id,
        "entrada",
        "Tienda",
        ahora=INSTANTE,
    ) == FICHAJES_ACTIVOS_MULTIPLES
    assert Fichaje.query.count() == 2
    assert RegistroHorario.query.count() == 0


def test_ausencia_bloqueante_del_usuario_y_fecha_impide_escrituras(usuario):
    db.session.add(
        Ausencia(
            usuario_id=usuario.id,
            fecha=INSTANTE.date(),
            tipo="Vacaciones",
            creado_por_admin=False,
        )
    )
    db.session.commit()

    assert codigo_error(
        registrar_fichaje_usuario,
        db.session,
        usuario.id,
        "entrada",
        "Tienda",
        ahora=INSTANTE,
    ) == AUSENCIA_BLOQUEANTE
    assert Fichaje.query.count() == 0


def test_ausencias_ajenas_o_de_otro_dia_no_bloquean(usuario):
    otro = Usuario(
        nombre="Otro usuario",
        email="otro@example.test",
        password_hash=generate_password_hash("password-correcta"),
        admin=False,
    )
    db.session.add(otro)
    db.session.flush()
    db.session.add_all(
        [
            Ausencia(usuario_id=otro.id, fecha=INSTANTE.date(), tipo="Vacaciones"),
            Ausencia(
                usuario_id=usuario.id,
                fecha=INSTANTE.date() + timedelta(days=1),
                tipo="Vacaciones",
            ),
        ]
    )
    db.session.commit()

    resultado = registrar_fichaje_usuario(
        db.session, usuario.id, "entrada", "Tienda", ahora=INSTANTE
    )
    assert resultado.codigo == OK_ENTRADA


@pytest.mark.parametrize(
    ("registros", "codigo"),
    [
        ([SimpleNamespace(tipo="salida", timestamp=datetime(2026, 3, 10, 8))], SALIDA_SIN_ENTRADA),
        (
            [
                SimpleNamespace(tipo="entrada", timestamp=datetime(2026, 3, 10, 8)),
                SimpleNamespace(tipo="entrada", timestamp=datetime(2026, 3, 10, 9)),
            ],
            ENTRADA_DUPLICADA,
        ),
        (
            [
                SimpleNamespace(tipo="entrada", timestamp=datetime(2026, 3, 10, 8)),
                SimpleNamespace(tipo="salida", timestamp=datetime(2026, 3, 10, 9)),
                SimpleNamespace(tipo="salida", timestamp=datetime(2026, 3, 10, 10)),
            ],
            SALIDA_DUPLICADA,
        ),
        ([SimpleNamespace(tipo="pausa", timestamp=datetime(2026, 3, 10, 8))], SECUENCIA_ANOMALA),
        (
            [
                SimpleNamespace(tipo="entrada", timestamp=datetime(2026, 3, 10, 8)),
                SimpleNamespace(tipo="salida", timestamp=datetime(2026, 3, 10, 8)),
            ],
            SECUENCIA_ANOMALA,
        ),
        ([SimpleNamespace(tipo="entrada", timestamp=datetime(2026, 3, 11, 8))], SECUENCIA_ANOMALA),
    ],
)
def test_analizar_secuencia_rechaza_anomalias(registros, codigo):
    assert codigo_error(analizar_secuencia, registros, INSTANTE.date()) == codigo


def test_timestamp_nuevo_debe_ser_posterior_al_ultimo(usuario):
    registrar_fichaje_usuario(
        db.session, usuario.id, "entrada", "Tienda", ahora=INSTANTE
    )

    assert codigo_error(
        registrar_fichaje_usuario,
        db.session,
        usuario.id,
        "salida",
        ahora=INSTANTE,
    ) == SECUENCIA_ANOMALA
    assert RegistroHorario.query.count() == 1


def test_reloj_del_sistema_con_misma_resolucion_avanza_un_segundo(
    usuario,
    monkeypatch,
):
    fichaje = crear_fichaje(usuario)
    crear_registro(
        fichaje,
        "entrada",
        datetime.min.time().replace(hour=8),
        origen="Tienda",
    )
    db.session.commit()
    monkeypatch.setattr(
        "app.services.fichajes.ahora_madrid",
        lambda ahora=None: INSTANTE,
    )

    resultado = registrar_fichaje_usuario(db.session, usuario.id, "salida")

    assert resultado.instante == INSTANTE + timedelta(seconds=1)
    registros = RegistroHorario.query.order_by(RegistroHorario.timestamp).all()
    assert registros[1].timestamp > registros[0].timestamp


def test_servicio_rechaza_historial_anomalo_sin_escribir(usuario):
    fichaje = crear_fichaje(usuario)
    crear_registro(fichaje, "salida", datetime.min.time().replace(hour=8))
    db.session.commit()

    assert codigo_error(
        registrar_fichaje_usuario,
        db.session,
        usuario.id,
        "entrada",
        "Tienda",
        ahora=INSTANTE + timedelta(hours=1),
    ) == SALIDA_SIN_ENTRADA
    assert RegistroHorario.query.count() == 1


@pytest.mark.parametrize("fallo", ["add_registro", "flush", "commit"])
def test_fallos_de_persistencia_hacen_rollback_total(usuario, monkeypatch, fallo):
    rollback_real = db.session.rollback
    rollbacks = []

    def rollback_contado():
        rollbacks.append(True)
        return rollback_real()

    monkeypatch.setattr(db.session, "rollback", rollback_contado)

    if fallo == "add_registro":
        add_real = db.session.add

        def add_con_fallo(objeto):
            if isinstance(objeto, RegistroHorario):
                raise RuntimeError("fallo simulado")
            return add_real(objeto)

        monkeypatch.setattr(db.session, "add", add_con_fallo)
    elif fallo == "flush":
        monkeypatch.setattr(
            db.session,
            "flush",
            lambda: (_ for _ in ()).throw(RuntimeError("fallo simulado")),
        )
    else:
        monkeypatch.setattr(
            db.session,
            "commit",
            lambda: (_ for _ in ()).throw(RuntimeError("fallo simulado")),
        )

    assert codigo_error(
        registrar_fichaje_usuario,
        db.session,
        usuario.id,
        "entrada",
        "Tienda",
        ahora=INSTANTE,
    ) == ERROR_PERSISTENCIA
    assert rollbacks == [True]
    assert Fichaje.query.count() == 0
    assert RegistroHorario.query.count() == 0


def test_ruta_ignora_campos_administrativos_manipulados(client, usuario):
    login(client, usuario)
    response = client.post(
        "/fichar_registro",
        data={
            "tipo": "entrada",
            "origen": "Tienda",
            "usuario_id": "999999",
            "fecha": "2000-01-01",
            "timestamp": "2000-01-01T00:00:00",
            "creado_por_admin": "1",
            "eliminado": "1",
        },
    )

    assert response.status_code == 302
    fichaje = Fichaje.query.one()
    registro = RegistroHorario.query.one()
    assert fichaje.usuario_id == usuario.id
    assert fichaje.fecha != date(2000, 1, 1)
    assert fichaje.creado_por_admin is False
    assert fichaje.eliminado is False
    assert registro.creado_por_admin is False
    assert registro.eliminado is False


def test_vista_expone_una_unica_accion_siguiente(client, usuario):
    login(client, usuario)
    html_inicial = client.get("/fichar").get_data(as_text=True)
    assert 'id="form_entrada"' in html_inicial
    assert "Fichar entrada" in html_inicial
    assert 'id="form_salida"' not in html_inicial

    client.post(
        "/fichar_registro",
        data={"tipo": "entrada", "origen": "Tienda"},
    )
    html_dentro = client.get("/fichar").get_data(as_text=True)
    assert 'id="form_entrada"' not in html_dentro
    assert 'id="form_salida"' in html_dentro
    assert "Fichar salida" in html_dentro
    assert "disabled" not in html_dentro


def test_vista_oculta_ambas_acciones_ante_secuencia_anomala(client, usuario):
    hoy = date.today()
    fichaje = crear_fichaje(usuario, fecha=hoy)
    crear_registro(
        fichaje,
        "salida",
        datetime.min.time().replace(hour=8),
        dia=hoy,
    )
    db.session.commit()
    login(client, usuario)

    html = client.get("/fichar").get_data(as_text=True)
    assert 'id="form_entrada"' not in html
    assert 'id="form_salida"' not in html
    assert "No hay ninguna acción de fichaje disponible." in html

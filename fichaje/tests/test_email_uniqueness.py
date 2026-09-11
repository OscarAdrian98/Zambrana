import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Usuario
from app.services.autenticacion import (
    ErrorValidacionAutenticacion,
    normalizar_email,
)
from app.services.usuarios import (
    RESTRICCION_EMAIL_USUARIO,
    USUARIO_CREADO,
    USUARIO_EMAIL_DUPLICADO,
    USUARIO_ERROR_INTEGRIDAD,
    es_duplicado_email_usuario,
    persistir_usuario,
)
from crear_admin import crear_administrador_con_datos
import preflight_unicidad_email
from preflight_unicidad_email import CONSULTA, tiene_bloqueos, validar_entorno


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ErrorMotor(Exception):
    pass


def error_mysql(codigo, mensaje):
    return IntegrityError("INSERT", {}, ErrorMotor(codigo, mensaje))


def datos_registro(email="nuevo@example.test"):
    return {
        "nombre": "Usuario nuevo",
        "email": email,
        "password": "frase segura de registro",
        "confirmar_password": "frase segura de registro",
        "puesto": "Administración",
    }


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("USUARIO@example.test", "usuario@example.test"),
        (" usuario@example.test", "usuario@example.test"),
        ("usuario@example.test ", "usuario@example.test"),
        ("usuario@example.test", "usuario@example.test"),
    ],
)
def test_normalizacion_email_cubre_mayusculas_y_espacios(entrada, esperado):
    assert normalizar_email(entrada) == esperado


@pytest.mark.parametrize("entrada", [None, 3, "", "   "])
def test_normalizacion_email_rechaza_tipo_invalido_y_vacio(entrada):
    with pytest.raises(ErrorValidacionAutenticacion):
        normalizar_email(entrada)


def test_modelo_declara_una_sola_unicidad_fisica_nombrada(app):
    tabla = Usuario.__table__
    restricciones = [
        restriccion
        for restriccion in tabla.constraints
        if restriccion.__class__.__name__ == "UniqueConstraint"
    ]

    assert len(restricciones) == 1
    assert restricciones[0].name == RESTRICCION_EMAIL_USUARIO
    assert [columna.name for columna in restricciones[0].columns] == ["email"]
    assert Usuario.email.type.length == 100
    assert Usuario.email.nullable is False

    fisicas = inspect(db.engine).get_unique_constraints("usuarios")
    assert len(fisicas) == 1
    assert fisicas[0]["name"] == RESTRICCION_EMAIL_USUARIO
    assert fisicas[0]["column_names"] == ["email"]


def test_sqlite_impide_duplicado_fisico_y_se_clasifica(app):
    primero = persistir_usuario(
        db.session,
        Usuario,
        nombre="Primero",
        email="fisico@example.test",
        password_hash="hash",
        puesto="Administración",
        admin=False,
    )
    segundo = persistir_usuario(
        db.session,
        Usuario,
        nombre="Segundo",
        email="fisico@example.test",
        password_hash="hash",
        puesto="Administración",
        admin=False,
    )

    assert primero.codigo == USUARIO_CREADO
    assert segundo.codigo == USUARIO_EMAIL_DUPLICADO
    assert Usuario.query.filter_by(email="fisico@example.test").count() == 1
    assert db.session.is_active


@pytest.mark.parametrize(
    ("error", "esperado"),
    [
        (
            error_mysql(
                1062,
                "Duplicate entry '<redacted>' " "for key 'usuarios.uq_usuarios_email'",
            ),
            True,
        ),
        (
            error_mysql(1062, "Duplicate entry '<redacted>' for key 'otro'"),
            False,
        ),
        (
            error_mysql(1452, "Cannot add or update a child row"),
            False,
        ),
        (
            IntegrityError(
                "INSERT",
                {},
                sqlite3.IntegrityError("UNIQUE constraint failed: usuarios.email"),
            ),
            True,
        ),
        (
            IntegrityError(
                "INSERT",
                {},
                sqlite3.IntegrityError(
                    "UNIQUE constraint failed: otra_tabla.otro_campo"
                ),
            ),
            False,
        ),
    ],
)
def test_clasificador_solo_reconoce_unicidad_del_email(error, esperado):
    assert es_duplicado_email_usuario(error) is esperado


def test_registro_convierte_solo_integrity_error_del_email(
    client,
    monkeypatch,
):
    commit_real = db.session.commit

    def duplicado():
        raise error_mysql(
            1062,
            "Duplicate entry '<redacted>' " "for key 'usuarios.uq_usuarios_email'",
        )

    monkeypatch.setattr(db.session, "commit", duplicado)
    respuesta = client.post(
        "/registro",
        data=datos_registro(),
        follow_redirects=True,
    )
    assert "Ya existe un usuario con ese email." in respuesta.get_data(as_text=True)
    assert Usuario.query.count() == 0
    assert db.session.is_active

    monkeypatch.setattr(db.session, "commit", commit_real)
    segunda = client.post(
        "/registro",
        data=datos_registro("segundo@example.test"),
    )
    assert segunda.status_code == 302
    assert Usuario.query.filter_by(email="segundo@example.test").count() == 1


def test_registro_no_presenta_integridad_ajena_como_email_duplicado(
    client,
    monkeypatch,
):
    def integridad_ajena():
        raise error_mysql(1452, "Foreign key failure")

    monkeypatch.setattr(db.session, "commit", integridad_ajena)
    respuesta = client.post(
        "/registro",
        data=datos_registro(),
        follow_redirects=True,
    )
    texto = respuesta.get_data(as_text=True)

    assert "Ya existe un usuario con ese email." not in texto
    assert "No se pudo completar el registro." in texto
    assert Usuario.query.count() == 0
    assert db.session.is_active


def test_persistencia_devuelve_error_tecnico_ante_integridad_ajena(
    app,
    monkeypatch,
):
    def integridad_ajena():
        raise error_mysql(1062, "Duplicate entry '<redacted>' for key 'otro'")

    monkeypatch.setattr(db.session, "commit", integridad_ajena)
    resultado = persistir_usuario(
        db.session,
        Usuario,
        nombre="Usuario",
        email="tecnico@example.test",
        password_hash="hash",
        puesto="Administración",
        admin=False,
    )

    assert resultado.codigo == USUARIO_ERROR_INTEGRIDAD
    assert Usuario.query.count() == 0
    assert db.session.is_active


def test_conflicto_mariadb_1020_solo_es_duplicado_si_la_fila_existe(
    app,
    monkeypatch,
):
    existente = Usuario(
        nombre="Existente",
        email="maria-race@example.test",
        password_hash="hash",
        puesto="Administración",
        admin=False,
    )
    db.session.add(existente)
    db.session.commit()

    def conflicto_concurrente():
        from sqlalchemy.exc import OperationalError

        raise OperationalError(
            "INSERT",
            {},
            ErrorMotor(1020, "Record changed"),
        )

    monkeypatch.setattr(db.session, "commit", conflicto_concurrente)
    duplicado = persistir_usuario(
        db.session,
        Usuario,
        nombre="Concurrente",
        email="maria-race@example.test",
        password_hash="hash",
        puesto="Administración",
        admin=False,
    )
    no_duplicado = persistir_usuario(
        db.session,
        Usuario,
        nombre="Otro",
        email="maria-otro@example.test",
        password_hash="hash",
        puesto="Administración",
        admin=False,
    )

    assert duplicado.codigo == USUARIO_EMAIL_DUPLICADO
    assert duplicado.codigo_motor == 1020
    assert no_duplicado.codigo != USUARIO_EMAIL_DUPLICADO
    assert no_duplicado.codigo_motor == 1020


def test_crear_administrador_normaliza_y_no_concede_datos_incorrectos(app):
    resultado = crear_administrador_con_datos(
        db.session,
        Usuario,
        lambda password: f"hash:{len(password)}",
        nombre="  Administrador   Local  ",
        email="  ADMIN.NUEVO@example.test ",
        password="frase segura administrativa",
    )

    assert resultado.codigo == USUARIO_CREADO
    usuario = Usuario.query.one()
    assert usuario.nombre == "Administrador Local"
    assert usuario.email == "admin.nuevo@example.test"
    assert usuario.admin is True
    assert usuario.puesto == "Administración"


def test_crear_administrador_detecta_precheck_y_carrera_simulada(
    app,
    monkeypatch,
):
    existente = crear_administrador_con_datos(
        db.session,
        Usuario,
        lambda password: "hash",
        nombre="Primero",
        email="admin@example.test",
        password="frase segura administrativa",
    )
    assert existente.codigo == USUARIO_CREADO

    duplicado = crear_administrador_con_datos(
        db.session,
        Usuario,
        lambda password: "hash",
        nombre="Segundo",
        email=" ADMIN@example.test ",
        password="frase segura administrativa",
    )
    assert duplicado.codigo == USUARIO_EMAIL_DUPLICADO

    db.session.delete(Usuario.query.one())
    db.session.commit()

    def carrera():
        raise error_mysql(
            1062,
            "Duplicate entry '<redacted>' " "for key 'usuarios.uq_usuarios_email'",
        )

    monkeypatch.setattr(db.session, "commit", carrera)
    carrera_resultado = crear_administrador_con_datos(
        db.session,
        Usuario,
        lambda password: "hash",
        nombre="Carrera",
        email="carrera@example.test",
        password="frase segura administrativa",
    )

    assert carrera_resultado.codigo == USUARIO_EMAIL_DUPLICADO
    assert Usuario.query.count() == 0
    assert db.session.is_active


def test_migracion_solo_anade_y_elimina_la_restriccion_de_email():
    ruta = (
        PROJECT_ROOT
        / "migrations"
        / "versions"
        / "d44f21c6a82b_anade_unicidad_a_usuarios_email.py"
    )
    fuente = ruta.read_text(encoding="utf-8")

    assert 'revision = "d44f21c6a82b"' in fuente
    assert 'down_revision = "a9464fce2497"' in fuente
    assert fuente.count("create_unique_constraint") == 1
    assert fuente.count("drop_constraint") == 1
    assert "valor_nuevo" not in fuente
    for operacion_prohibida in (
        "add_column",
        "drop_column",
        "create_table",
        "drop_table",
        "execute(",
    ):
        assert operacion_prohibida not in fuente


def test_preflight_requiere_autorizacion_uri_y_usuario_no_root():
    with pytest.raises(RuntimeError, match="autorización"):
        validar_entorno({})
    with pytest.raises(RuntimeError, match="URI"):
        validar_entorno({"FICHAJE_EMAIL_PREFLIGHT": "1"})
    with pytest.raises(RuntimeError, match="root"):
        validar_entorno(
            {
                "FICHAJE_EMAIL_PREFLIGHT": "1",
                "FICHAJE_EMAIL_PREFLIGHT_DB_URL": (
                    "mysql+pymysql://root:change_me@127.0.0.1:3306/local"
                ),
            }
        )


def test_preflight_sql_es_exclusivamente_de_lectura():
    consulta = str(CONSULTA).upper()

    assert consulta.lstrip().startswith("SELECT")
    for operacion in (
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "ALTER",
        "CREATE",
        "COMMIT",
    ):
        assert operacion not in consulta


def test_preflight_detecta_todos_los_bloqueos_agregados():
    limpio = {
        "filas": 4,
        "grupos_exactos": 0,
        "grupos_normalizados": 0,
        "nulos": 0,
        "vacios": 0,
        "espacios_laterales": 0,
        "mayusculas": 0,
    }
    assert tiene_bloqueos(limpio) is False

    for indicador in (
        "grupos_exactos",
        "grupos_normalizados",
        "nulos",
        "vacios",
        "espacios_laterales",
        "mayusculas",
    ):
        resultado = dict(limpio)
        resultado[indicador] = 1
        assert tiene_bloqueos(resultado) is True


def test_preflight_devuelve_error_sin_mostrar_correos(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        preflight_unicidad_email,
        "validar_entorno",
        lambda: "mysql+pymysql://local",
    )
    monkeypatch.setattr(
        preflight_unicidad_email,
        "ejecutar_preflight",
        lambda _uri: {
            "filas": 2,
            "grupos_exactos": 0,
            "grupos_normalizados": 1,
            "nulos": 0,
            "vacios": 0,
            "espacios_laterales": 1,
            "mayusculas": 1,
        },
    )

    assert preflight_unicidad_email.main() == 2
    salida = capsys.readouterr().out
    assert "grupos_normalizados=1" in salida
    assert "@" not in salida


def test_preflight_limpio_devuelve_cero(monkeypatch):
    monkeypatch.setattr(
        preflight_unicidad_email,
        "validar_entorno",
        lambda: "mysql+pymysql://local",
    )
    monkeypatch.setattr(
        preflight_unicidad_email,
        "ejecutar_preflight",
        lambda _uri: {
            "filas": 2,
            "grupos_exactos": 0,
            "grupos_normalizados": 0,
            "nulos": 0,
            "vacios": 0,
            "espacios_laterales": 0,
            "mayusculas": 0,
        },
    )

    assert preflight_unicidad_email.main() == 0

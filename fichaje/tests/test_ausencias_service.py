import ast
from datetime import date, time, timedelta
import inspect

import pytest
from werkzeug.security import generate_password_hash

from app import app as flask_app
from app import db
from app.models import Ausencia, Usuario
from app.services.ausencias import (
    AUSENCIA_ACTUALIZADA,
    AUSENCIA_ADMINISTRADOR_INEXISTENTE,
    AUSENCIA_BLOQUE_AJENO,
    AUSENCIA_BLOQUE_INEXISTENTE,
    AUSENCIA_CONFLICTO_CONCURRENTE,
    AUSENCIA_CREADA,
    AUSENCIA_DATOS_INVALIDOS,
    AUSENCIA_DUPLICADA,
    AUSENCIA_ELIMINADA,
    AUSENCIA_ERROR_PERSISTENCIA,
    AUSENCIA_SIN_CAMBIOS,
    AUSENCIA_SIN_PERMISOS,
    AUSENCIA_SNAPSHOT_INVALIDO,
    AUSENCIA_USUARIO_INEXISTENTE,
    EntradaAusencia,
    EntradaEdicionAusencia,
    TIPO_BAJA,
    TIPO_ENFERMEDAD,
    TIPO_MEDICO,
    TIPO_VACACIONES,
    ausencia_bloquea_fichaje,
    crear_ausencia_administrativa,
    crear_ausencia_usuario,
    crear_snapshot_ausencia_firmado,
    editar_ausencia_usuario,
    eliminar_ausencia_usuario,
    preparar_edicion_ausencia_usuario,
)


FECHA = date(2099, 7, 10)


def entrada(**cambios):
    valores = {
        "fecha_desde": FECHA.isoformat(),
        "fecha_hasta": FECHA.isoformat(),
        "tipo": TIPO_VACACIONES,
        "observaciones": "Texto ficticio neutro",
        "hora_desde": "",
        "hora_hasta": "",
    }
    valores.update(cambios)
    return EntradaAusencia(**valores)


def entrada_edicion(snapshot, **cambios):
    valores = entrada(**cambios)
    return EntradaEdicionAusencia(
        snapshot=snapshot,
        fecha_desde=valores.fecha_desde,
        fecha_hasta=valores.fecha_hasta,
        tipo=valores.tipo,
        observaciones=valores.observaciones,
        hora_desde=valores.hora_desde,
        hora_hasta=valores.hora_hasta,
    )


def crear_usuario(email, *, admin=False):
    usuario = Usuario(
        nombre="Persona ficticia",
        email=email,
        password_hash=generate_password_hash("password-correcta"),
        admin=admin,
        puesto="Administración",
    )
    db.session.add(usuario)
    db.session.commit()
    return usuario


def crear_bloque(
    usuario,
    *,
    desde=FECHA,
    hasta=FECHA,
    tipo=TIPO_VACACIONES,
    observaciones="Texto ficticio neutro",
    hora_desde=None,
    hora_hasta=None,
    creado_por_admin=False,
):
    filas = []
    fecha = desde
    while fecha <= hasta:
        filas.append(
            Ausencia(
                usuario_id=usuario.id,
                fecha=fecha,
                tipo=tipo,
                observaciones=observaciones,
                hora_desde=hora_desde,
                hora_hasta=hora_hasta,
                creado_por_admin=creado_por_admin,
            )
        )
        fecha += timedelta(days=1)
    db.session.add_all(filas)
    db.session.commit()
    return tuple(filas)


def snapshot(usuario, filas):
    return crear_snapshot_ausencia_firmado(
        usuario.id,
        filas,
        flask_app.config["SECRET_KEY"],
    )


def editar(usuario, filas, **cambios):
    return editar_ausencia_usuario(
        usuario_id=usuario.id,
        entrada=entrada_edicion(snapshot(usuario, filas), **cambios),
        secret_key=flask_app.config["SECRET_KEY"],
        session=db.session,
    )


def eliminar(usuario, filas, token=None):
    return eliminar_ausencia_usuario(
        usuario_id=usuario.id,
        snapshot=token or snapshot(usuario, filas),
        secret_key=flask_app.config["SECRET_KEY"],
        session=db.session,
    )


def test_crear_un_dia_valido_y_bloqueante(usuario):
    resultado = crear_ausencia_usuario(
        usuario_id=usuario.id,
        entrada=entrada(tipo=TIPO_BAJA),
        session=db.session,
    )
    assert resultado.codigo == AUSENCIA_CREADA
    assert resultado.cantidad == 1
    assert ausencia_bloquea_fichaje(Ausencia.query.one())


def test_crear_rango_natural_inclusivo(usuario):
    resultado = crear_ausencia_usuario(
        usuario_id=usuario.id,
        entrada=entrada(fecha_hasta=(FECHA + timedelta(days=2)).isoformat()),
        session=db.session,
    )
    assert resultado.codigo == AUSENCIA_CREADA
    assert [fila.fecha for fila in Ausencia.query.order_by(Ausencia.fecha)] == [
        FECHA,
        FECHA + timedelta(days=1),
        FECHA + timedelta(days=2),
    ]


def test_crear_cita_medica_normaliza_alias_y_horas(usuario):
    resultado = crear_ausencia_usuario(
        usuario_id=usuario.id,
        entrada=entrada(
            tipo="  MÉDICO ",
            hora_desde="09:15",
            hora_hasta="10:30",
        ),
        session=db.session,
    )
    fila = Ausencia.query.one()
    assert resultado.codigo == AUSENCIA_CREADA
    assert fila.tipo == TIPO_MEDICO
    assert fila.hora_desde == time(9, 15)
    assert fila.hora_hasta == time(10, 30)
    assert not ausencia_bloquea_fichaje(fila)


def test_creacion_duplicada_secuencial_es_controlada(usuario):
    primero = crear_ausencia_usuario(
        usuario_id=usuario.id,
        entrada=entrada(),
        session=db.session,
    )
    segundo = crear_ausencia_usuario(
        usuario_id=usuario.id,
        entrada=entrada(),
        session=db.session,
    )
    assert primero.codigo == AUSENCIA_CREADA
    assert segundo.codigo == AUSENCIA_DUPLICADA
    assert Ausencia.query.count() == 1


def test_solapamiento_no_identico_se_preserva(usuario):
    crear_ausencia_usuario(
        usuario_id=usuario.id,
        entrada=entrada(),
        session=db.session,
    )
    segundo = crear_ausencia_usuario(
        usuario_id=usuario.id,
        entrada=entrada(tipo=TIPO_ENFERMEDAD),
        session=db.session,
    )
    assert segundo.codigo == AUSENCIA_CREADA
    assert Ausencia.query.count() == 2


def test_creacion_usuario_inexistente(usuario):
    resultado = crear_ausencia_usuario(
        usuario_id=999999,
        entrada=entrada(),
        session=db.session,
    )
    assert resultado.codigo == AUSENCIA_USUARIO_INEXISTENTE
    assert Ausencia.query.count() == 0


@pytest.mark.parametrize(
    "cambio",
    [
        {"fecha_desde": "fecha-invalida"},
        {"fecha_hasta": (FECHA - timedelta(days=1)).isoformat()},
        {"tipo": "tipo-no-permitido"},
        {"tipo": TIPO_MEDICO, "hora_desde": "09:00", "hora_hasta": ""},
    ],
)
def test_creacion_rechaza_campos_invalidos(usuario, cambio):
    resultado = crear_ausencia_usuario(
        usuario_id=usuario.id,
        entrada=entrada(**cambio),
        session=db.session,
    )
    assert resultado.codigo == AUSENCIA_DATOS_INVALIDOS
    assert Ausencia.query.count() == 0


@pytest.mark.parametrize("fallo_en", [1, 2, 3])
def test_fallo_en_cualquier_add_hace_rollback_total(
    usuario,
    monkeypatch,
    fallo_en,
):
    add_real = db.session.add
    contador = 0

    def add_con_error(objeto):
        nonlocal contador
        contador += 1
        if contador == fallo_en:
            raise RuntimeError("fallo controlado")
        add_real(objeto)

    monkeypatch.setattr(db.session, "add", add_con_error)
    resultado = crear_ausencia_usuario(
        usuario_id=usuario.id,
        entrada=entrada(fecha_hasta=(FECHA + timedelta(days=2)).isoformat()),
        session=db.session,
    )
    assert resultado.codigo == AUSENCIA_ERROR_PERSISTENCIA
    assert Ausencia.query.count() == 0
    assert not db.session.new and db.session.is_active


def test_fallo_commit_creacion_permite_reintento(usuario, monkeypatch):
    commit_real = db.session.commit
    monkeypatch.setattr(
        db.session,
        "commit",
        lambda: (_ for _ in ()).throw(RuntimeError("fallo controlado")),
    )
    primero = crear_ausencia_usuario(
        usuario_id=usuario.id,
        entrada=entrada(),
        session=db.session,
    )
    monkeypatch.setattr(db.session, "commit", commit_real)
    segundo = crear_ausencia_usuario(
        usuario_id=usuario.id,
        entrada=entrada(),
        session=db.session,
    )
    assert primero.codigo == AUSENCIA_ERROR_PERSISTENCIA
    assert segundo.codigo == AUSENCIA_CREADA
    assert Ausencia.query.count() == 1


@pytest.mark.parametrize(
    ("cambios", "fechas", "tipo"),
    [
        (
            {"observaciones": "Editado"},
            [FECHA],
            TIPO_VACACIONES,
        ),
        (
            {"fecha_hasta": (FECHA + timedelta(days=2)).isoformat()},
            [FECHA, FECHA + timedelta(days=1), FECHA + timedelta(days=2)],
            TIPO_VACACIONES,
        ),
        (
            {
                "fecha_desde": (FECHA + timedelta(days=1)).isoformat(),
                "fecha_hasta": (FECHA + timedelta(days=2)).isoformat(),
            },
            [FECHA + timedelta(days=1), FECHA + timedelta(days=2)],
            TIPO_VACACIONES,
        ),
        (
            {"tipo": TIPO_ENFERMEDAD},
            [FECHA],
            TIPO_ENFERMEDAD,
        ),
        (
            {
                "tipo": TIPO_MEDICO,
                "hora_desde": "11:00",
                "hora_hasta": "12:00",
            },
            [FECHA],
            TIPO_MEDICO,
        ),
    ],
)
def test_ediciones_validas(
    usuario,
    cambios,
    fechas,
    tipo,
):
    hasta_original = FECHA + timedelta(days=2) if len(fechas) == 2 else FECHA
    filas = crear_bloque(usuario, hasta=hasta_original)
    resultado = editar(usuario, filas, **cambios)
    persistidas = Ausencia.query.order_by(Ausencia.fecha).all()
    assert resultado.codigo == AUSENCIA_ACTUALIZADA
    assert [fila.fecha for fila in persistidas] == fechas
    assert {fila.tipo for fila in persistidas} == {tipo}


def test_edicion_sin_cambios(usuario):
    filas = crear_bloque(usuario)
    resultado = editar(usuario, filas)
    assert resultado.codigo == AUSENCIA_SIN_CAMBIOS
    assert [fila.id for fila in Ausencia.query.all()] == [filas[0].id]


def test_edicion_bloque_inexistente(usuario):
    filas = crear_bloque(usuario)
    token = snapshot(usuario, filas)
    db.session.delete(filas[0])
    db.session.commit()
    resultado = preparar_edicion_ausencia_usuario(
        usuario_id=usuario.id,
        snapshot=token,
        secret_key=flask_app.config["SECRET_KEY"],
        session=db.session,
    )
    assert resultado.codigo == AUSENCIA_BLOQUE_INEXISTENTE


def test_edicion_bloque_ajeno(usuario):
    otro = crear_usuario("otro-servicio@example.test")
    filas = crear_bloque(otro)
    resultado = editar_ausencia_usuario(
        usuario_id=usuario.id,
        entrada=entrada_edicion(
            snapshot(otro, filas),
            observaciones="Manipulado",
        ),
        secret_key=flask_app.config["SECRET_KEY"],
        session=db.session,
    )
    assert resultado.codigo == AUSENCIA_BLOQUE_AJENO
    assert Ausencia.query.count() == 1


def test_edicion_snapshot_manipulado(usuario):
    filas = crear_bloque(usuario)
    token = snapshot(usuario, filas) + "x"
    resultado = editar_ausencia_usuario(
        usuario_id=usuario.id,
        entrada=entrada_edicion(token, observaciones="Manipulado"),
        secret_key=flask_app.config["SECRET_KEY"],
        session=db.session,
    )
    assert resultado.codigo == AUSENCIA_SNAPSHOT_INVALIDO
    assert Ausencia.query.one().observaciones == "Texto ficticio neutro"


def test_edicion_snapshot_con_id_ajeno_firmado_no_mezcla_filas(usuario):
    otro = crear_usuario("id-ajeno@example.test")
    propia = crear_bloque(usuario)[0]
    ajena = crear_bloque(
        otro,
        desde=FECHA + timedelta(days=5),
        hasta=FECHA + timedelta(days=5),
    )[0]
    token = crear_snapshot_ausencia_firmado(
        usuario.id,
        (propia, ajena),
        flask_app.config["SECRET_KEY"],
    )
    resultado = editar_ausencia_usuario(
        usuario_id=usuario.id,
        entrada=entrada_edicion(token, observaciones="Manipulado"),
        secret_key=flask_app.config["SECRET_KEY"],
        session=db.session,
    )
    assert resultado.codigo == AUSENCIA_CONFLICTO_CONCURRENTE
    assert Ausencia.query.count() == 2


def test_edicion_snapshot_obsoleto_no_sobrescribe(usuario):
    filas = crear_bloque(usuario)
    token = snapshot(usuario, filas)
    filas[0].observaciones = "Cambio ganador"
    db.session.commit()
    resultado = editar_ausencia_usuario(
        usuario_id=usuario.id,
        entrada=entrada_edicion(token, observaciones="Cambio obsoleto"),
        secret_key=flask_app.config["SECRET_KEY"],
        session=db.session,
    )
    assert resultado.codigo == AUSENCIA_CONFLICTO_CONCURRENTE
    assert Ausencia.query.one().observaciones == "Cambio ganador"


def test_edicion_fallo_despues_de_delete_restaura_bloque(
    usuario,
    monkeypatch,
):
    filas = crear_bloque(usuario)
    flush_real = db.session.flush
    monkeypatch.setattr(
        db.session,
        "flush",
        lambda: (_ for _ in ()).throw(RuntimeError("fallo controlado")),
    )
    resultado = editar(usuario, filas, observaciones="Editado")
    monkeypatch.setattr(db.session, "flush", flush_real)
    assert resultado.codigo == AUSENCIA_ERROR_PERSISTENCIA
    assert Ausencia.query.one().observaciones == "Texto ficticio neutro"
    assert not db.session.new and db.session.is_active


def test_edicion_fallo_recreacion_restaura_bloque(usuario, monkeypatch):
    filas = crear_bloque(usuario)
    monkeypatch.setattr(
        db.session,
        "add",
        lambda _: (_ for _ in ()).throw(RuntimeError("fallo controlado")),
    )
    resultado = editar(usuario, filas, observaciones="Editado")
    assert resultado.codigo == AUSENCIA_ERROR_PERSISTENCIA
    assert Ausencia.query.one().observaciones == "Texto ficticio neutro"


def test_edicion_fallo_commit_permite_reintento(usuario, monkeypatch):
    filas = crear_bloque(usuario)
    token = snapshot(usuario, filas)
    solicitud = entrada_edicion(token, observaciones="Editado")
    commit_real = db.session.commit
    monkeypatch.setattr(
        db.session,
        "commit",
        lambda: (_ for _ in ()).throw(RuntimeError("fallo controlado")),
    )
    primero = editar_ausencia_usuario(
        usuario_id=usuario.id,
        entrada=solicitud,
        secret_key=flask_app.config["SECRET_KEY"],
        session=db.session,
    )
    monkeypatch.setattr(db.session, "commit", commit_real)
    segundo = editar_ausencia_usuario(
        usuario_id=usuario.id,
        entrada=solicitud,
        secret_key=flask_app.config["SECRET_KEY"],
        session=db.session,
    )
    assert primero.codigo == AUSENCIA_ERROR_PERSISTENCIA
    assert segundo.codigo == AUSENCIA_ACTUALIZADA
    assert Ausencia.query.one().observaciones == "Editado"


def test_eliminacion_valida_y_fisica(usuario):
    filas = crear_bloque(usuario, hasta=FECHA + timedelta(days=1))
    resultado = eliminar(usuario, filas)
    assert resultado.codigo == AUSENCIA_ELIMINADA
    assert resultado.cantidad == 2
    assert Ausencia.query.count() == 0


def test_eliminacion_bloque_ya_eliminado(usuario):
    filas = crear_bloque(usuario)
    token = snapshot(usuario, filas)
    assert eliminar(usuario, filas, token).codigo == AUSENCIA_ELIMINADA
    assert eliminar(usuario, filas, token).codigo == AUSENCIA_BLOQUE_INEXISTENTE


def test_eliminacion_bloque_ajeno(usuario):
    otro = crear_usuario("borrado-ajeno@example.test")
    filas = crear_bloque(otro)
    resultado = eliminar(usuario, filas, snapshot(otro, filas))
    assert resultado.codigo == AUSENCIA_BLOQUE_AJENO
    assert Ausencia.query.count() == 1


def test_eliminacion_snapshot_invalido(usuario):
    filas = crear_bloque(usuario)
    resultado = eliminar(usuario, filas, "token-invalido")
    assert resultado.codigo == AUSENCIA_SNAPSHOT_INVALIDO
    assert Ausencia.query.count() == 1


def test_eliminacion_snapshot_obsoleto(usuario):
    filas = crear_bloque(usuario)
    token = snapshot(usuario, filas)
    filas[0].tipo = TIPO_ENFERMEDAD
    db.session.commit()
    resultado = eliminar(usuario, filas, token)
    assert resultado.codigo == AUSENCIA_CONFLICTO_CONCURRENTE
    assert Ausencia.query.count() == 1


def test_eliminacion_fallo_delete_hace_rollback(usuario, monkeypatch):
    filas = crear_bloque(usuario)
    monkeypatch.setattr(
        db.session,
        "delete",
        lambda _: (_ for _ in ()).throw(RuntimeError("fallo controlado")),
    )
    resultado = eliminar(usuario, filas)
    assert resultado.codigo == AUSENCIA_ERROR_PERSISTENCIA
    assert Ausencia.query.count() == 1


def test_eliminacion_fallo_commit_permite_reintento(usuario, monkeypatch):
    filas = crear_bloque(usuario)
    token = snapshot(usuario, filas)
    commit_real = db.session.commit
    monkeypatch.setattr(
        db.session,
        "commit",
        lambda: (_ for _ in ()).throw(RuntimeError("fallo controlado")),
    )
    primero = eliminar(usuario, filas, token)
    monkeypatch.setattr(db.session, "commit", commit_real)
    segundo = eliminar(usuario, filas, token)
    assert primero.codigo == AUSENCIA_ERROR_PERSISTENCIA
    assert segundo.codigo == AUSENCIA_ELIMINADA
    assert Ausencia.query.count() == 0


def test_creacion_administrativa_valida(administrador, usuario):
    resultado = crear_ausencia_administrativa(
        administrador_id=administrador.id,
        usuario_id=usuario.id,
        entrada=entrada(),
        session=db.session,
    )
    assert resultado.codigo == AUSENCIA_CREADA
    assert Ausencia.query.one().creado_por_admin is True


def test_creacion_administrativa_admin_inexistente(usuario):
    resultado = crear_ausencia_administrativa(
        administrador_id=999999,
        usuario_id=usuario.id,
        entrada=entrada(),
        session=db.session,
    )
    assert resultado.codigo == AUSENCIA_ADMINISTRADOR_INEXISTENTE


def test_creacion_administrativa_sin_permisos(usuario):
    objetivo = crear_usuario("objetivo@example.test")
    resultado = crear_ausencia_administrativa(
        administrador_id=usuario.id,
        usuario_id=objetivo.id,
        entrada=entrada(),
        session=db.session,
    )
    assert resultado.codigo == AUSENCIA_SIN_PERMISOS
    assert Ausencia.query.count() == 0


def test_creacion_administrativa_objetivo_inexistente(administrador):
    resultado = crear_ausencia_administrativa(
        administrador_id=administrador.id,
        usuario_id=999999,
        entrada=entrada(),
        session=db.session,
    )
    assert resultado.codigo == AUSENCIA_USUARIO_INEXISTENTE


def test_duplicado_administrador_empleado_es_controlado(
    administrador,
    usuario,
):
    empleado = crear_ausencia_usuario(
        usuario_id=usuario.id,
        entrada=entrada(),
        session=db.session,
    )
    admin = crear_ausencia_administrativa(
        administrador_id=administrador.id,
        usuario_id=usuario.id,
        entrada=entrada(),
        session=db.session,
    )
    assert empleado.codigo == AUSENCIA_CREADA
    assert admin.codigo == AUSENCIA_DUPLICADA
    assert Ausencia.query.count() == 1


def test_api_administrativa_no_acepta_campos_arbitrarios():
    firma = inspect.signature(crear_ausencia_administrativa)
    for campo in (
        "creado_por_admin",
        "admin",
        "request",
        "current_user",
        "flash",
    ):
        assert campo not in firma.parameters


def test_rutas_de_ausencias_no_contienen_escrituras_orm_directas():
    import app.routes as rutas

    arbol = ast.parse(inspect.getsource(rutas))
    nombres = {
        "mis_ausencias",
        "editar_ausencia_usuario",
        "eliminar_ausencia_usuario",
        "admin_registrar_ausencia",
    }
    funciones = {
        nodo.name: nodo
        for nodo in arbol.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
        and nodo.name in nombres
    }
    assert set(funciones) == nombres
    prohibidos = {"add", "add_all", "delete", "flush", "commit", "rollback"}
    for nombre, funcion in funciones.items():
        for nodo in ast.walk(funcion):
            if isinstance(nodo, ast.Call):
                if isinstance(nodo.func, ast.Name):
                    assert nodo.func.id != "Ausencia", nombre
                if isinstance(nodo.func, ast.Attribute):
                    assert nodo.func.attr not in prohibidos, nombre


def test_rutas_csrf_y_autorizacion(
    client,
    usuario,
    administrador,
):
    assert client.post("/mis-ausencias", data={}).status_code == 302
    client.post(
        "/login",
        data={"email": usuario.email, "password": "password-correcta"},
    )
    assert (
        client.post(
            "/mis-ausencias",
            data={
                "fecha_desde": FECHA.isoformat(),
                "fecha_hasta": FECHA.isoformat(),
                "tipo": TIPO_VACACIONES,
            },
            incluir_csrf=False,
        ).status_code
        == 400
    )
    assert Ausencia.query.count() == 0
    assert (
        client.post(
            f"/admin/registrar-ausencia/{usuario.id}",
            data={
                "fecha_desde": FECHA.isoformat(),
                "fecha_hasta": FECHA.isoformat(),
                "tipo": TIPO_VACACIONES,
            },
        ).status_code
        == 302
    )
    assert Ausencia.query.count() == 0


def test_ruta_admin_ignora_campos_manipulados(
    client,
    administrador,
    usuario,
):
    otro = crear_usuario("otro-objetivo@example.test")
    client.post(
        "/login",
        data={
            "email": administrador.email,
            "password": "password-correcta",
        },
    )
    respuesta = client.post(
        f"/admin/registrar-ausencia/{usuario.id}",
        data={
            "fecha_desde": FECHA.isoformat(),
            "fecha_hasta": FECHA.isoformat(),
            "tipo": TIPO_VACACIONES,
            "usuario_id": str(otro.id),
            "creado_por_admin": "0",
            "admin": "0",
        },
    )
    assert respuesta.status_code == 302
    fila = Ausencia.query.one()
    assert fila.usuario_id == usuario.id
    assert fila.creado_por_admin is True


def test_ruta_edicion_sin_csrf_no_modifica(client, usuario):
    filas = crear_bloque(usuario)
    token = snapshot(usuario, filas)
    client.post(
        "/login",
        data={"email": usuario.email, "password": "password-correcta"},
    )
    respuesta = client.post(
        "/mis-ausencias",
        data={
            "editar_snapshot": token,
            "fecha_desde": FECHA.isoformat(),
            "fecha_hasta": FECHA.isoformat(),
            "tipo": TIPO_ENFERMEDAD,
        },
        incluir_csrf=False,
    )
    assert respuesta.status_code == 400
    assert Ausencia.query.one().tipo == TIPO_VACACIONES


def test_ruta_snapshot_obsoleto_muestra_conflicto_y_no_sobrescribe(
    client,
    usuario,
):
    filas = crear_bloque(usuario)
    token = snapshot(usuario, filas)
    filas[0].observaciones = "Cambio ganador"
    db.session.commit()
    client.post(
        "/login",
        data={"email": usuario.email, "password": "password-correcta"},
    )
    respuesta = client.post(
        "/mis-ausencias",
        data={
            "editar_snapshot": token,
            "fecha_desde": FECHA.isoformat(),
            "fecha_hasta": FECHA.isoformat(),
            "tipo": TIPO_VACACIONES,
            "observaciones": "Cambio obsoleto",
        },
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    assert "modificada por otra operación" in respuesta.get_data(as_text=True)
    assert Ausencia.query.one().observaciones == "Cambio ganador"

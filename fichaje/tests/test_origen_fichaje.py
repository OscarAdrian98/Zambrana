from datetime import datetime

import pytest

from app import db
from app.models import Fichaje, RegistroHorario
from app.routes import zona_es


def login(client, usuario):
    return client.post(
        "/login",
        data={
            "email": usuario.email,
            "password": "password-correcta",
        },
    )


def crear_entrada_activa(usuario, origen):
    ahora = datetime.now(zona_es)
    fichaje = Fichaje(
        usuario_id=usuario.id,
        fecha=ahora.date(),
        fecha_creacion=ahora,
        creado_por_admin=False,
        eliminado=False,
    )
    db.session.add(fichaje)
    db.session.flush()
    entrada = RegistroHorario(
        fichaje_id=fichaje.id,
        tipo="entrada",
        timestamp=ahora,
        creado_por_admin=False,
        eliminado=False,
        origen=origen,
    )
    db.session.add(entrada)
    db.session.commit()
    return fichaje, entrada


@pytest.mark.parametrize("origen", ["Tienda", "Remoto"])
def test_entrada_manual_admite_origenes_validos(client, usuario, origen):
    login(client, usuario)

    response = client.post(
        "/fichar_registro",
        data={"tipo": "entrada", "origen": origen},
    )

    assert response.status_code == 302
    registro = RegistroHorario.query.one()
    assert registro.tipo == "entrada"
    assert registro.origen == origen


@pytest.mark.parametrize("origen", ["Auto", "Casa"])
def test_entrada_manual_rechaza_origenes_no_permitidos(
    client,
    usuario,
    origen,
):
    login(client, usuario)

    response = client.post(
        "/fichar_registro",
        data={"tipo": "entrada", "origen": origen},
    )

    assert response.status_code == 302
    assert Fichaje.query.count() == 0
    assert RegistroHorario.query.count() == 0


@pytest.mark.parametrize("origen", ["Tienda", "Remoto"])
def test_salida_hereda_el_origen_de_la_entrada(client, usuario, origen):
    crear_entrada_activa(usuario, origen)
    login(client, usuario)

    response = client.post(
        "/fichar_registro",
        data={"tipo": "salida"},
    )

    assert response.status_code == 302
    registros = RegistroHorario.query.order_by(RegistroHorario.id).all()
    assert [registro.tipo for registro in registros] == ["entrada", "salida"]
    assert registros[1].origen == origen


def test_salida_manual_cierra_entrada_con_origen_auto(client, usuario):
    crear_entrada_activa(usuario, "Auto")
    login(client, usuario)

    response = client.post(
        "/fichar_registro",
        data={"tipo": "salida"},
    )

    assert response.status_code == 302
    registros = RegistroHorario.query.order_by(RegistroHorario.id).all()
    assert len(registros) == 2
    assert registros[1].tipo == "salida"
    assert registros[1].origen == "Auto"


def test_salida_ignora_un_origen_manipulado(client, usuario):
    crear_entrada_activa(usuario, "Remoto")
    login(client, usuario)

    response = client.post(
        "/fichar_registro",
        data={"tipo": "salida", "origen": "Tienda"},
    )

    assert response.status_code == 302
    salida = RegistroHorario.query.filter_by(tipo="salida").one()
    assert salida.origen == "Remoto"


def test_salida_usa_tienda_si_la_entrada_no_tiene_origen(client, usuario):
    crear_entrada_activa(usuario, None)
    login(client, usuario)

    response = client.post(
        "/fichar_registro",
        data={"tipo": "salida", "origen": "Auto"},
    )

    assert response.status_code == 302
    salida = RegistroHorario.query.filter_by(tipo="salida").one()
    assert salida.origen == "Tienda"

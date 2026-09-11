from datetime import date, datetime, time
from io import BytesIO
import re

import pytest
from openpyxl import load_workbook
from werkzeug.datastructures import MultiDict

from app import db
import app.services.fichajes as fichajes_service
from app.models import Fichaje, Modificacion, RegistroHorario
from app.services.edicion_fichajes import preparar_edicion
from app.services.exportaciones import preparar_fila_personal
from app.services.horarios import reconstruir_tramos


def login(client, usuario):
    return client.post(
        "/login",
        data={
            "email": usuario.email,
            "password": "password-correcta",
        },
    )


def crear_fichaje(usuario, registros, fecha=None):
    fecha = fecha or date.today()
    fichaje = Fichaje(
        usuario_id=usuario.id,
        fecha=fecha,
        fecha_creacion=datetime.combine(fecha, time(7, 0)),
        creado_por_admin=False,
        eliminado=False,
    )
    db.session.add(fichaje)
    db.session.flush()

    creados = []
    for tipo, hora, origen, eliminado in registros:
        registro = RegistroHorario(
            fichaje_id=fichaje.id,
            tipo=tipo,
            timestamp=datetime.combine(fecha, hora),
            creado_por_admin=False,
            eliminado=eliminado,
            origen=origen,
        )
        db.session.add(registro)
        creados.append(registro)

    db.session.commit()
    return fichaje, creados


def registros_tramos(*tramos):
    registros = []
    for entrada, salida, origen in tramos:
        registros.extend(
            [
                ("entrada", entrada, origen, False),
                ("salida", salida, origen, False),
            ]
        )
    return registros


def url_edicion(fichaje):
    return f"/admin/editar_fichaje/{fichaje.id}"


def activos(fichaje):
    return (
        RegistroHorario.query.filter_by(fichaje_id=fichaje.id, eliminado=False)
        .order_by(RegistroHorario.timestamp, RegistroHorario.id)
        .all()
    )


def extraer_snapshot(html):
    coincidencia = re.search(r'name="snapshot" value="([^"]+)"', html)
    assert coincidencia is not None
    return coincidencia.group(1)


def formulario_actual(client, fichaje):
    html = client.get(url_edicion(fichaje)).get_data(as_text=True)
    registros = activos(fichaje)
    preparacion = preparar_edicion(reconstruir_tramos(registros))
    data = {"snapshot": extraer_snapshot(html)}

    for tramo in preparacion.tramos:
        base = f"tramos[{tramo.clave}]"
        data[f"{base}[entrada_id]"] = str(tramo.entrada_id)
        data[f"{base}[salida_id]"] = str(tramo.salida_id or "")
        data[f"{base}[entrada]"] = tramo.entrada
        data[f"{base}[salida]"] = tramo.salida
        data[f"{base}[origen]"] = tramo.origen
        data[f"{base}[eliminar]"] = "0"

    for incidencia in preparacion.irregulares:
        base = f"irregulares[{incidencia.clave}]"
        data[f"{base}[registro_id]"] = str(incidencia.registro_id)

    return data, preparacion, html


def base_por_entrada(data, entrada_id):
    for nombre, valor in data.items():
        if nombre.endswith("[entrada_id]") and valor == str(entrada_id):
            return nombre[: -len("[entrada_id]")]
    raise AssertionError("No se encontró la fila del registro")


def agregar_tramo(data, clave, entrada, salida, origen="Tienda"):
    base = f"tramos[{clave}]"
    data[f"{base}[entrada_id]"] = ""
    data[f"{base}[salida_id]"] = ""
    data[f"{base}[entrada]"] = entrada
    data[f"{base}[salida]"] = salida
    data[f"{base}[origen]"] = origen
    data[f"{base}[eliminar]"] = "0"
    return base


def estado_registros(fichaje):
    return [
        (
            registro.id,
            registro.tipo,
            registro.timestamp,
            registro.origen,
            registro.eliminado,
        )
        for registro in RegistroHorario.query.filter_by(fichaje_id=fichaje.id)
        .order_by(RegistroHorario.id)
        .all()
    ]


def post_edicion(client, fichaje, data, follow_redirects=False):
    return client.post(
        url_edicion(fichaje),
        data=data,
        follow_redirects=follow_redirects,
    )


def test_carga_un_tramo_con_ids_y_origen(client, administrador):
    fichaje, registros = crear_fichaje(
        administrador,
        registros_tramos((time(9, 0), time(14, 0), "Remoto")),
    )
    login(client, administrador)

    _, _, html = formulario_actual(client, fichaje)

    assert f"value=\"{registros[0].id}\"" in html
    assert f"value=\"{registros[1].id}\"" in html
    assert 'value="09:00"' in html
    assert 'value="14:00"' in html
    assert '<option value="Remoto" selected>' in html


def test_carga_dos_tramos(client, administrador):
    fichaje, _ = crear_fichaje(
        administrador,
        registros_tramos(
            (time(8, 0), time(9, 0), "Tienda"),
            (time(10, 0), time(12, 0), "Remoto"),
        ),
    )
    login(client, administrador)

    _, _, html = formulario_actual(client, fichaje)

    assert html.count('data-existente="1"') == 2


def test_carga_tres_o_mas_tramos(client, administrador):
    fichaje, _ = crear_fichaje(
        administrador,
        registros_tramos(
            (time(8, 0), time(9, 0), "Tienda"),
            (time(10, 0), time(11, 0), "Tienda"),
            (time(12, 0), time(14, 0), "Auto"),
        ),
    )
    login(client, administrador)

    _, _, html = formulario_actual(client, fichaje)

    assert html.count('data-existente="1"') == 3
    assert 'value="12:00"' in html
    assert 'value="14:00"' in html


def test_carga_entrada_abierta_con_salida_vacia(client, administrador):
    fichaje, _ = crear_fichaje(
        administrador,
        [("entrada", time(9, 0), "Auto", False)],
    )
    login(client, administrador)

    _, preparacion, html = formulario_actual(client, fichaje)

    assert len(preparacion.tramos) == 1
    assert preparacion.tramos[0].incompleto is True
    assert preparacion.tramos[0].salida == ""
    assert "Entrada abierta" in html


def test_carga_no_muestra_registro_eliminado(client, administrador):
    fichaje, _ = crear_fichaje(
        administrador,
        [
            ("entrada", time(9, 0), "Tienda", False),
            ("salida", time(10, 0), "Tienda", False),
            ("entrada", time(12, 34), "Oculto", True),
        ],
    )
    login(client, administrador)

    _, _, html = formulario_actual(client, fichaje)

    assert "12:34" not in html
    assert "Oculto" not in html


@pytest.mark.parametrize(
    "registros,mensaje",
    [
        (
            [("salida", time(10, 0), "Tienda", False)],
            "Salida sin entrada",
        ),
        (
            [
                ("entrada", time(9, 0), "Tienda", False),
                ("entrada", time(10, 0), "Remoto", False),
            ],
            "Doble entrada",
        ),
        (
            [("pausa", time(10, 0), "Tienda", False)],
            "Tipo de registro desconocido",
        ),
    ],
)
def test_carga_muestra_incidencias_no_representables(
    client,
    administrador,
    registros,
    mensaje,
):
    fichaje, _ = crear_fichaje(administrador, registros)
    login(client, administrador)

    _, preparacion, html = formulario_actual(client, fichaje)

    assert mensaje in html
    assert len(preparacion.irregulares) >= 1
    assert "Se conservarán salvo" in html


def test_plantilla_no_contiene_linea_de_depuracion(app):
    plantilla, _, _ = app.jinja_loader.get_source(
        app.jinja_env,
        "editar_fichaje_admin.html",
    )

    assert "Registros visibles cargados" not in plantilla
    assert "print(" not in plantilla
    assert "entradas[]" not in plantilla
    assert "registro_ids[]" not in plantilla


def test_envio_identico_conserva_ids(client, administrador):
    fichaje, registros = crear_fichaje(
        administrador,
        registros_tramos((time(9, 0), time(14, 0), "Tienda")),
    )
    ids_antes = [registro.id for registro in registros]
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)

    response = post_edicion(client, fichaje, data, follow_redirects=True)

    assert "No había cambios que guardar" in response.get_data(as_text=True)
    assert [registro.id for registro in activos(fichaje)] == ids_antes


def test_envio_identico_no_crea_auditoria(client, administrador):
    fichaje, _ = crear_fichaje(
        administrador,
        registros_tramos((time(9, 0), time(14, 0), "Tienda")),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)

    post_edicion(client, fichaje, data)

    assert Modificacion.query.filter_by(fichaje_id=fichaje.id).count() == 0


def test_envio_identico_no_modifica_eliminado(client, administrador):
    fichaje, _ = crear_fichaje(
        administrador,
        registros_tramos((time(9, 0), time(14, 0), "Tienda")),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)

    post_edicion(client, fichaje, data)

    assert all(not registro.eliminado for registro in registros_del_fichaje(fichaje))


def registros_del_fichaje(fichaje):
    return (
        RegistroHorario.query.filter_by(fichaje_id=fichaje.id)
        .order_by(RegistroHorario.id)
        .all()
    )


@pytest.mark.parametrize(
    "cambios",
    [
        {"entrada": "08:30"},
        {"salida": "15:00"},
        {"entrada": "08:30", "salida": "15:00"},
    ],
    ids=["entrada", "salida", "ambas"],
)
def test_modificar_horas_elimina_solo_originales_cambiados_y_crea_activos(
    client,
    administrador,
    cambios,
):
    fichaje, originales = crear_fichaje(
        administrador,
        registros_tramos((time(9, 0), time(14, 0), "Remoto")),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    base = base_por_entrada(data, originales[0].id)
    for campo, valor in cambios.items():
        data[f"{base}[{campo}]"] = valor

    post_edicion(client, fichaje, data)

    db.session.refresh(originales[0])
    db.session.refresh(originales[1])
    assert originales[0].eliminado is ("entrada" in cambios)
    assert originales[1].eliminado is ("salida" in cambios)
    nuevos_activos = activos(fichaje)
    assert [r.timestamp.strftime("%H:%M") for r in nuevos_activos] == [
        cambios.get("entrada", "09:00"),
        cambios.get("salida", "14:00"),
    ]
    assert all(registro.origen == "Remoto" for registro in nuevos_activos)


@pytest.mark.parametrize("origen", ["Tienda", "Remoto", "Auto"])
def test_tramo_sin_cambios_conserva_cada_origen(
    client,
    administrador,
    origen,
):
    fichaje, originales = crear_fichaje(
        administrador,
        registros_tramos((time(9, 0), time(14, 0), origen)),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)

    post_edicion(client, fichaje, data)

    assert [registro.id for registro in activos(fichaje)] == [
        registro.id for registro in originales
    ]
    assert [registro.origen for registro in activos(fichaje)] == [origen, origen]


def test_cambiar_origen_elimina_originales_y_lo_aplica_al_tramo(
    client,
    administrador,
):
    fichaje, originales = crear_fichaje(
        administrador,
        registros_tramos((time(9, 0), time(14, 0), "Tienda")),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    base = base_por_entrada(data, originales[0].id)
    data[f"{base}[origen]"] = "Auto"

    post_edicion(client, fichaje, data)

    assert all(db.session.get(RegistroHorario, r.id).eliminado for r in originales)
    assert [registro.origen for registro in activos(fichaje)] == ["Auto", "Auto"]
    campos = {
        modificacion.campo_modificado
        for modificacion in Modificacion.query.filter_by(fichaje_id=fichaje.id)
    }
    assert "origen_mod" in campos


def test_auditoria_es_compacta_y_cabe_en_columnas(client, administrador):
    fichaje, originales = crear_fichaje(
        administrador,
        registros_tramos((time(9, 0), time(14, 0), "Tienda")),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    base = base_por_entrada(data, originales[0].id)
    data[f"{base}[entrada]"] = "09:05"
    data[f"{base}[salida]"] = "14:30"

    post_edicion(client, fichaje, data)

    auditorias = Modificacion.query.filter_by(fichaje_id=fichaje.id).all()
    assert auditorias
    assert all(len(mod.valor_anterior) <= 20 for mod in auditorias)
    assert all(len(mod.valor_nuevo) <= 20 for mod in auditorias)
    assert any(
        mod.valor_anterior == "09:00-14:00"
        and mod.valor_nuevo == "09:05-14:30"
        for mod in auditorias
    )


def test_anadir_tramo_nuevo(client, administrador):
    fichaje, _ = crear_fichaje(administrador, [])
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    agregar_tramo(data, "nuevo_1", "09:00", "14:00", "Tienda")

    post_edicion(client, fichaje, data)

    assert [registro.tipo for registro in activos(fichaje)] == ["entrada", "salida"]
    assert Modificacion.query.filter_by(
        fichaje_id=fichaje.id,
        campo_modificado="tramo_add",
    ).count() == 1


def test_anadir_tercer_tramo(client, administrador):
    fichaje, _ = crear_fichaje(
        administrador,
        registros_tramos(
            (time(8, 0), time(9, 0), "Tienda"),
            (time(10, 0), time(11, 0), "Tienda"),
        ),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    agregar_tramo(data, "nuevo_3", "12:00", "14:00", "Remoto")

    post_edicion(client, fichaje, data)

    resultado = reconstruir_tramos(activos(fichaje))
    assert len(resultado.tramos) == 3
    assert resultado.total_trabajado.total_seconds() == 4 * 3600


def test_anadir_entrada_abierta_explicita(client, administrador):
    fichaje, _ = crear_fichaje(
        administrador,
        registros_tramos((time(8, 0), time(9, 0), "Tienda")),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    agregar_tramo(data, "abierto", "10:00", "", "Auto")

    post_edicion(client, fichaje, data)

    resultado = reconstruir_tramos(activos(fichaje))
    assert resultado.estado == "Dentro"
    assert resultado.entrada_abierta.origen == "Auto"


def test_cerrar_entrada_abierta_crea_salida_y_auditoria(
    client,
    administrador,
):
    fichaje, registros = crear_fichaje(
        administrador,
        [("entrada", time(9, 0), "Remoto", False)],
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    base = base_por_entrada(data, registros[0].id)
    data[f"{base}[salida]"] = "11:00"

    post_edicion(client, fichaje, data)

    resultado = reconstruir_tramos(activos(fichaje))
    assert resultado.estado == "Fuera"
    assert resultado.total_trabajado.total_seconds() == 2 * 3600
    assert [registro.origen for registro in activos(fichaje)] == ["Remoto", "Remoto"]
    assert Modificacion.query.filter_by(
        fichaje_id=fichaje.id,
        campo_modificado="entrada_abierta",
    ).count() == 1


def test_modificar_hora_de_entrada_abierta_mantiene_estado_dentro(
    client,
    administrador,
):
    fichaje, registros = crear_fichaje(
        administrador,
        [("entrada", time(9, 0), "Auto", False)],
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    base = base_por_entrada(data, registros[0].id)
    data[f"{base}[entrada]"] = "09:30"

    post_edicion(client, fichaje, data)

    resultado = reconstruir_tramos(activos(fichaje))
    assert resultado.estado == "Dentro"
    assert resultado.entrada_abierta.timestamp.strftime("%H:%M") == "09:30"
    assert resultado.entrada_abierta.origen == "Auto"
    assert db.session.get(RegistroHorario, registros[0].id).eliminado is True


@pytest.mark.parametrize("origen", ["Tienda", "Remoto", "Auto"])
def test_tramo_nuevo_admite_origenes_controlados(
    client,
    administrador,
    origen,
):
    fichaje, _ = crear_fichaje(administrador, [])
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    agregar_tramo(data, "nuevo", "09:00", "10:00", origen)

    post_edicion(client, fichaje, data)

    assert [registro.origen for registro in activos(fichaje)] == [origen, origen]


def test_tramo_nuevo_rechaza_origen_invalido(client, administrador):
    fichaje, _ = crear_fichaje(administrador, [])
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    agregar_tramo(data, "nuevo", "09:00", "10:00", "Casa")
    antes = estado_registros(fichaje)

    response = post_edicion(client, fichaje, data, follow_redirects=True)

    assert "origen seleccionado no es válido" in response.get_data(as_text=True)
    assert estado_registros(fichaje) == antes


def test_eliminar_un_tramo_marca_sus_registros(client, administrador):
    fichaje, registros = crear_fichaje(
        administrador,
        registros_tramos(
            (time(8, 0), time(9, 0), "Tienda"),
            (time(10, 0), time(11, 0), "Remoto"),
        ),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    base = base_por_entrada(data, registros[0].id)
    data[f"{base}[eliminar]"] = "1"

    post_edicion(client, fichaje, data)

    assert db.session.get(RegistroHorario, registros[0].id).eliminado is True
    assert db.session.get(RegistroHorario, registros[1].id).eliminado is True
    assert [registro.id for registro in activos(fichaje)] == [
        registros[2].id,
        registros[3].id,
    ]


def test_eliminar_todos_mantiene_cabecera(client, administrador):
    fichaje, registros = crear_fichaje(
        administrador,
        registros_tramos((time(9, 0), time(14, 0), "Tienda")),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    data[f"{base_por_entrada(data, registros[0].id)}[eliminar]"] = "1"

    post_edicion(client, fichaje, data)

    assert activos(fichaje) == []
    db.session.refresh(fichaje)
    assert fichaje.eliminado is False
    assert Modificacion.query.filter_by(
        fichaje_id=fichaje.id,
        campo_modificado="tramo_del",
    ).count() == 1
    html = client.get(url_edicion(fichaje)).get_data(as_text=True)
    assert 'data-existente="1"' not in html
    assert "Añadir tramo" in html


def test_eliminar_entrada_abierta(client, administrador):
    fichaje, registros = crear_fichaje(
        administrador,
        [("entrada", time(9, 0), "Auto", False)],
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    data[f"{base_por_entrada(data, registros[0].id)}[eliminar]"] = "1"

    post_edicion(client, fichaje, data)

    assert activos(fichaje) == []
    assert db.session.get(RegistroHorario, registros[0].id).eliminado is True


def test_eliminar_un_tramo_conserva_ids_de_los_demas(client, administrador):
    fichaje, registros = crear_fichaje(
        administrador,
        registros_tramos(
            (time(8, 0), time(9, 0), "Tienda"),
            (time(10, 0), time(11, 0), "Remoto"),
        ),
    )
    ids_segundo = [registros[2].id, registros[3].id]
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    data[f"{base_por_entrada(data, registros[0].id)}[eliminar]"] = "1"

    post_edicion(client, fichaje, data)

    assert [registro.id for registro in activos(fichaje)] == ids_segundo


def test_eliminar_registro_irregular_es_explicito(client, administrador):
    fichaje, registros = crear_fichaje(
        administrador,
        [("salida", time(10, 0), "Tienda", False)],
    )
    login(client, administrador)
    data, preparacion, _ = formulario_actual(client, fichaje)
    incidencia = preparacion.irregulares[0]
    data[f"irregulares[{incidencia.clave}][eliminar]"] = "1"

    post_edicion(client, fichaje, data)

    assert db.session.get(RegistroHorario, registros[0].id).eliminado is True
    assert Modificacion.query.filter_by(
        fichaje_id=fichaje.id,
        campo_modificado="incidencia_del",
    ).count() == 1


def assert_rechazado_sin_cambios(client, fichaje, data, texto):
    antes = estado_registros(fichaje)
    response = post_edicion(client, fichaje, data, follow_redirects=True)
    assert texto in response.get_data(as_text=True)
    assert estado_registros(fichaje) == antes
    assert Modificacion.query.filter_by(fichaje_id=fichaje.id).count() == 0


def test_rechaza_id_de_otro_fichaje(client, administrador):
    fichaje, registros = crear_fichaje(
        administrador,
        registros_tramos((time(9, 0), time(10, 0), "Tienda")),
    )
    otro, otros = crear_fichaje(
        administrador,
        registros_tramos((time(11, 0), time(12, 0), "Remoto")),
        fecha=date.today().replace(day=1),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    base = base_por_entrada(data, registros[0].id)
    data[f"{base}[entrada_id]"] = str(otros[0].id)

    assert_rechazado_sin_cambios(
        client,
        fichaje,
        data,
        "no corresponden al fichaje editable",
    )
    assert len(activos(otro)) == 2


def test_rechaza_id_con_tipo_incorrecto(client, administrador):
    fichaje, registros = crear_fichaje(
        administrador,
        registros_tramos((time(9, 0), time(10, 0), "Tienda")),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    base = base_por_entrada(data, registros[0].id)
    data[f"{base}[entrada_id]"] = str(registros[1].id)
    data[f"{base}[salida_id]"] = str(registros[0].id)

    assert_rechazado_sin_cambios(
        client,
        fichaje,
        data,
        "no corresponden al fichaje editable",
    )


@pytest.mark.parametrize("identificador", ["abc", "-1", "0"])
def test_rechaza_id_no_entero_o_no_positivo(
    client,
    administrador,
    identificador,
):
    fichaje, registros = crear_fichaje(
        administrador,
        registros_tramos((time(9, 0), time(10, 0), "Tienda")),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    base = base_por_entrada(data, registros[0].id)
    data[f"{base}[entrada_id]"] = identificador

    assert_rechazado_sin_cambios(
        client,
        fichaje,
        data,
        "identificador de entrada no es válido",
    )


def test_rechaza_id_de_registro_inactivo(client, administrador):
    fichaje, registros = crear_fichaje(
        administrador,
        [
            ("entrada", time(9, 0), "Tienda", True),
            ("salida", time(10, 0), "Tienda", True),
        ],
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    base = agregar_tramo(data, "inactivo", "09:00", "10:00", "Tienda")
    data[f"{base}[entrada_id]"] = str(registros[0].id)
    data[f"{base}[salida_id]"] = str(registros[1].id)

    assert_rechazado_sin_cambios(
        client,
        fichaje,
        data,
        "no corresponden al fichaje editable",
    )


def test_rechaza_id_duplicado(client, administrador):
    fichaje, registros = crear_fichaje(
        administrador,
        registros_tramos((time(9, 0), time(10, 0), "Tienda")),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    base_nuevo = "tramos[duplicado]"
    base_original = base_por_entrada(data, registros[0].id)
    for campo in ("entrada_id", "salida_id", "entrada", "salida", "origen"):
        data[f"{base_nuevo}[{campo}]"] = data[f"{base_original}[{campo}]"]
    data[f"{base_nuevo}[eliminar]"] = "0"

    assert_rechazado_sin_cambios(
        client,
        fichaje,
        data,
        "más de un tramo",
    )


def test_entrada_sin_salida_se_conserva_segun_politica(client, administrador):
    fichaje, registros = crear_fichaje(
        administrador,
        [("entrada", time(9, 0), "Tienda", False)],
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)

    post_edicion(client, fichaje, data)

    assert [registro.id for registro in activos(fichaje)] == [registros[0].id]
    assert reconstruir_tramos(activos(fichaje)).estado == "Dentro"


@pytest.mark.parametrize(
    "entrada,salida,mensaje",
    [
        ("", "10:00", "salida sin entrada"),
        ("10:00", "10:00", "anterior a la salida"),
        ("11:00", "10:00", "anterior a la salida"),
        ("25:00", "26:00", "hora de entrada no es válida"),
    ],
)
def test_rechaza_horas_invalidas(
    client,
    administrador,
    entrada,
    salida,
    mensaje,
):
    fichaje, _ = crear_fichaje(administrador, [])
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    agregar_tramo(data, "invalido", entrada, salida, "Tienda")

    assert_rechazado_sin_cambios(client, fichaje, data, mensaje)


def test_rechaza_solapamiento(client, administrador):
    fichaje, _ = crear_fichaje(
        administrador,
        registros_tramos((time(9, 0), time(11, 0), "Tienda")),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    agregar_tramo(data, "solapado", "10:00", "12:00", "Remoto")

    assert_rechazado_sin_cambios(client, fichaje, data, "no pueden solaparse")


def test_rechaza_tramo_duplicado(client, administrador):
    fichaje, _ = crear_fichaje(
        administrador,
        registros_tramos((time(9, 0), time(11, 0), "Tienda")),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    agregar_tramo(data, "duplicado", "09:00", "11:00", "Remoto")

    assert_rechazado_sin_cambios(client, fichaje, data, "tramos duplicados")


def test_rechaza_mas_de_una_entrada_abierta(client, administrador):
    fichaje, _ = crear_fichaje(administrador, [])
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    agregar_tramo(data, "abierto_1", "09:00", "", "Tienda")
    agregar_tramo(data, "abierto_2", "10:00", "", "Remoto")

    assert_rechazado_sin_cambios(
        client,
        fichaje,
        data,
        "Solo puede existir una entrada abierta",
    )


def test_rechaza_manipulacion_de_origen(client, administrador):
    fichaje, registros = crear_fichaje(
        administrador,
        registros_tramos((time(9, 0), time(10, 0), "Tienda")),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    base = base_por_entrada(data, registros[0].id)
    data[f"{base}[origen]"] = "Servidor"

    assert_rechazado_sin_cambios(
        client,
        fichaje,
        data,
        "origen seleccionado no es válido",
    )


def test_rechaza_formulario_mal_formado(client, administrador):
    fichaje, registros = crear_fichaje(
        administrador,
        registros_tramos((time(9, 0), time(10, 0), "Tienda")),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    base = base_por_entrada(data, registros[0].id)
    del data[f"{base}[origen]"]

    assert_rechazado_sin_cambios(
        client,
        fichaje,
        data,
        "formulario de edición está incompleto",
    )


def test_rechaza_mas_de_cincuenta_tramos(client, administrador):
    fichaje, _ = crear_fichaje(administrador, [])
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    for indice in range(51):
        agregar_tramo(
            data,
            f"nuevo_{indice}",
            "09:00",
            "10:00",
            "Tienda",
        )

    assert_rechazado_sin_cambios(
        client,
        fichaje,
        data,
        "límite de tramos permitido",
    )


def test_rechaza_campos_duplicados(client, administrador):
    fichaje, registros = crear_fichaje(
        administrador,
        registros_tramos((time(9, 0), time(10, 0), "Tienda")),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    base = base_por_entrada(data, registros[0].id)
    pares = list(data.items())
    pares.append((f"{base}[entrada]", "09:30"))

    assert_rechazado_sin_cambios(
        client,
        fichaje,
        MultiDict(pares),
        "campos duplicados",
    )


def test_fallo_commit_hace_rollback_completo(
    client,
    administrador,
    monkeypatch,
):
    fichaje, registros = crear_fichaje(
        administrador,
        registros_tramos((time(9, 0), time(10, 0), "Tienda")),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    data[f"{base_por_entrada(data, registros[0].id)}[entrada]"] = "08:30"
    antes = estado_registros(fichaje)

    def commit_con_error():
        raise RuntimeError("fallo de commit simulado")

    monkeypatch.setattr(db.session, "commit", commit_con_error)
    post_edicion(client, fichaje, data)

    assert estado_registros(fichaje) == antes
    assert Modificacion.query.count() == 0
    assert RegistroHorario.query.count() == 2


def test_fallo_auditoria_hace_rollback_y_sesion_sigue_utilizable(
    client,
    administrador,
    monkeypatch,
):
    fichaje, registros = crear_fichaje(
        administrador,
        registros_tramos((time(9, 0), time(10, 0), "Tienda")),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    data[f"{base_por_entrada(data, registros[0].id)}[salida]"] = "11:00"
    antes = estado_registros(fichaje)

    def auditoria_con_error(*args, **kwargs):
        raise RuntimeError("fallo de auditoría simulado")

    monkeypatch.setattr(fichajes_service, "Modificacion", auditoria_con_error)
    post_edicion(client, fichaje, data)

    assert estado_registros(fichaje) == antes
    assert RegistroHorario.query.filter_by(fichaje_id=fichaje.id).count() == 2
    assert Fichaje.query.filter_by(id=fichaje.id).one().eliminado is False


def test_snapshot_valido_permite_guardar(client, administrador):
    fichaje, _ = crear_fichaje(administrador, [])
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    agregar_tramo(data, "nuevo", "09:00", "10:00", "Tienda")

    post_edicion(client, fichaje, data)

    assert len(activos(fichaje)) == 2


def test_snapshot_manipulado_rechaza(client, administrador):
    fichaje, _ = crear_fichaje(
        administrador,
        registros_tramos((time(9, 0), time(10, 0), "Tienda")),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    data["snapshot"] += "manipulado"

    assert_rechazado_sin_cambios(
        client,
        fichaje,
        data,
        "huella de edición no es válida",
    )


@pytest.mark.parametrize("cambio", ["modificado", "añadido", "eliminado"])
def test_snapshot_rechaza_cambio_externo(
    client,
    administrador,
    cambio,
):
    fichaje, registros = crear_fichaje(
        administrador,
        registros_tramos((time(9, 0), time(10, 0), "Tienda")),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)

    if cambio == "modificado":
        registros[0].origen = "Remoto"
    elif cambio == "añadido":
        db.session.add(
            RegistroHorario(
                fichaje_id=fichaje.id,
                tipo="entrada",
                timestamp=datetime.combine(fichaje.fecha, time(11, 0)),
                origen="Tienda",
                eliminado=False,
                creado_por_admin=True,
            )
        )
    else:
        registros[1].eliminado = True
    db.session.commit()
    estado_externo = estado_registros(fichaje)

    response = post_edicion(client, fichaje, data, follow_redirects=True)

    assert "modificado por otra operación" in response.get_data(as_text=True)
    assert estado_registros(fichaje) == estado_externo


def test_coherencia_total_despues_de_editar(
    client,
    administrador,
):
    fichaje, registros = crear_fichaje(
        administrador,
        registros_tramos((time(8, 0), time(10, 0), "Tienda")),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    data[f"{base_por_entrada(data, registros[0].id)}[salida]"] = "12:00"
    post_edicion(client, fichaje, data)

    resumen = client.get("/resumen").get_data(as_text=True)
    admin = client.get("/admin/fichajes").get_data(as_text=True)
    excel_response = client.get("/exportar_mis_fichajes")
    worksheet = load_workbook(BytesIO(excel_response.data))["Fichajes"]
    fila_pdf = preparar_fila_personal(
        fichaje.fecha,
        reconstruir_tramos(activos(fichaje)),
    )

    assert "04:00:00" in resumen
    assert "04:00:00" in admin
    assert worksheet["C4"].value == "04:00:00"
    assert fila_pdf.total_texto == "04:00:00"


def test_coherencia_despues_de_eliminar_un_tramo(client, administrador):
    fichaje, registros = crear_fichaje(
        administrador,
        registros_tramos(
            (time(8, 0), time(9, 0), "Tienda"),
            (time(10, 0), time(12, 0), "Remoto"),
        ),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    data[f"{base_por_entrada(data, registros[0].id)}[eliminar]"] = "1"
    post_edicion(client, fichaje, data)

    resumen = client.get("/resumen").get_data(as_text=True)
    admin = client.get("/admin/fichajes").get_data(as_text=True)
    fila_pdf = preparar_fila_personal(
        fichaje.fecha,
        reconstruir_tramos(activos(fichaje)),
    )

    assert "02:00:00" in resumen
    assert "02:00:00" in admin
    assert fila_pdf.total_texto == "02:00:00"


def test_entrada_abierta_editada_conserva_estado_dentro(
    client,
    administrador,
):
    fichaje, registros = crear_fichaje(
        administrador,
        registros_tramos((time(9, 0), time(10, 0), "Tienda")),
    )
    login(client, administrador)
    data, _, _ = formulario_actual(client, fichaje)
    data[f"{base_por_entrada(data, registros[0].id)}[salida]"] = ""
    post_edicion(client, fichaje, data)

    resultado = reconstruir_tramos(activos(fichaje))
    fichar = client.get("/fichar").get_data(as_text=True)

    assert resultado.estado == "Dentro"
    assert "Dentro del trabajo" in fichar

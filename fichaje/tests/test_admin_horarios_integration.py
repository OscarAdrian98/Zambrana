import re
from datetime import date, datetime, time

import pytest

from app import db
from app.models import Ausencia, Fichaje, RegistroHorario


def login(client, usuario):
    return client.post(
        "/login",
        data={
            "email": usuario.email,
            "password": "password-correcta",
        },
    )


def crear_fichaje(usuario, fecha, registros):
    fichaje = Fichaje(
        usuario_id=usuario.id,
        fecha=fecha,
        fecha_creacion=datetime.combine(fecha, time(7, 0)),
        creado_por_admin=False,
        eliminado=False,
    )
    db.session.add(fichaje)
    db.session.flush()

    for tipo, hora, origen, eliminado in registros:
        db.session.add(
            RegistroHorario(
                fichaje_id=fichaje.id,
                tipo=tipo,
                timestamp=datetime.combine(fecha, hora),
                creado_por_admin=False,
                eliminado=eliminado,
                origen=origen,
            )
        )

    db.session.commit()
    return fichaje


def html_admin_fichajes(client):
    return client.get("/admin/fichajes").get_data(as_text=True)


def html_admin_usuario(client, usuario):
    return client.get(f"/admin/fichajes/{usuario.id}").get_data(as_text=True)


def valor_metrica(html, elemento_id):
    coincidencia = re.search(
        rf'id="{elemento_id}"[^>]*>\s*([^<]+)',
        html,
    )
    assert coincidencia is not None
    return coincidencia.group(1).strip()


def fila_dashboard(html, usuario):
    inicio = html.index(f'<tr data-usuario-id="{usuario.id}"')
    fin = html.index("</tr>", inicio)
    return html[inicio:fin]


def test_admin_fichajes_calcula_un_tramo(client, administrador, usuario):
    crear_fichaje(
        usuario,
        date.today(),
        [
            ("entrada", time(9, 0), "Tienda", False),
            ("salida", time(10, 30), "Tienda", False),
        ],
    )
    login(client, administrador)

    html = html_admin_fichajes(client)

    assert "01:30:00" in html
    assert RegistroHorario.query.count() == 2


def test_admin_fichajes_calcula_dos_tramos(client, administrador, usuario):
    crear_fichaje(
        usuario,
        date.today(),
        [
            ("entrada", time(8, 0), "Tienda", False),
            ("salida", time(9, 0), "Tienda", False),
            ("entrada", time(10, 0), "Remoto", False),
            ("salida", time(12, 0), "Remoto", False),
        ],
    )
    login(client, administrador)

    assert "03:00:00" in html_admin_fichajes(client)


def test_admin_fichajes_suma_tres_tramos(client, administrador, usuario):
    crear_fichaje(
        usuario,
        date.today(),
        [
            ("entrada", time(8, 0), "Tienda", False),
            ("salida", time(9, 0), "Tienda", False),
            ("entrada", time(10, 0), "Tienda", False),
            ("salida", time(11, 0), "Tienda", False),
            ("entrada", time(12, 0), "Remoto", False),
            ("salida", time(14, 0), "Remoto", False),
        ],
    )
    login(client, administrador)

    assert "04:00:00" in html_admin_fichajes(client)


def test_admin_fichajes_excluye_registros_eliminados(
    client,
    administrador,
    usuario,
):
    crear_fichaje(
        usuario,
        date.today(),
        [
            ("entrada", time(8, 0), "Tienda", False),
            ("salida", time(9, 0), "Tienda", False),
            ("entrada", time(10, 0), "Remoto", True),
            ("salida", time(15, 0), "Remoto", True),
        ],
    )
    login(client, administrador)

    html = html_admin_fichajes(client)

    assert "01:00:00" in html
    assert "06:00:00" not in html
    assert RegistroHorario.query.filter_by(eliminado=True).count() == 2


def test_admin_fichajes_doble_entrada_no_inventa_tiempo(
    client,
    administrador,
    usuario,
):
    crear_fichaje(
        usuario,
        date.today(),
        [
            ("entrada", time(9, 0), "Tienda", False),
            ("entrada", time(10, 0), "Remoto", False),
            ("salida", time(11, 0), "Tienda", False),
        ],
    )
    login(client, administrador)

    html = html_admin_fichajes(client)

    assert "02:00:00" in html
    assert "01:00:00" not in html


def test_admin_fichajes_salida_aislada_no_inventa_tiempo(
    client,
    administrador,
    usuario,
):
    crear_fichaje(
        usuario,
        date.today(),
        [("salida", time(10, 0), "Tienda", False)],
    )
    login(client, administrador)

    html = html_admin_fichajes(client)

    assert "00:00:00" not in html
    assert "Total trabajado:</strong> -" in html


@pytest.mark.parametrize(
    "registros",
    [
        [],
        [("entrada", time(9, 0), "Tienda", False)],
        [("pausa", time(10, 0), "Tienda", False)],
    ],
    ids=["sin-registros", "entrada-abierta", "tipo-desconocido"],
)
def test_admin_fichajes_sin_tramos_validos_muestra_total_vacio(
    client,
    administrador,
    usuario,
    registros,
):
    crear_fichaje(usuario, date.today(), registros)
    login(client, administrador)

    html = html_admin_fichajes(client)

    assert "00:00:00" not in html
    assert "Total trabajado:</strong> -" in html


def test_admin_usuario_total_diario_coincide_con_resumen(
    client,
    administrador,
    usuario,
):
    crear_fichaje(
        usuario,
        date.today(),
        [
            ("entrada", time(8, 0), "Tienda", False),
            ("salida", time(10, 0), "Tienda", False),
            ("entrada", time(11, 0), "Remoto", False),
            ("salida", time(14, 0), "Remoto", False),
        ],
    )
    login(client, administrador)
    html_admin = html_admin_usuario(client, usuario)

    client.get("/logout")
    login(client, usuario)
    html_resumen = client.get("/resumen").get_data(as_text=True)

    assert "05:00:00" in html_admin
    assert "05:00:00" in html_resumen
    assert valor_metrica(html_admin, "total-horas") == "05:00"


def test_admin_usuario_incluye_tres_tramos(client, administrador, usuario):
    crear_fichaje(
        usuario,
        date.today(),
        [
            ("entrada", time(8, 0), "Tienda", False),
            ("salida", time(9, 0), "Tienda", False),
            ("entrada", time(10, 0), "Tienda", False),
            ("salida", time(11, 0), "Tienda", False),
            ("entrada", time(12, 0), "Remoto", False),
            ("salida", time(15, 0), "Remoto", False),
        ],
    )
    login(client, administrador)

    html = html_admin_usuario(client, usuario)

    assert "05:00:00" in html
    assert "Entrada - 12:00:00 (Remoto)" in html
    assert "Salida - 15:00:00 (Remoto)" in html
    assert valor_metrica(html, "total-dias") == "1"


def test_admin_usuario_entrada_abierta_cuenta_un_dia_incompleto(
    client,
    administrador,
    usuario,
):
    crear_fichaje(
        usuario,
        date.today(),
        [("entrada", time(9, 0), "Tienda", False)],
    )
    login(client, administrador)

    html = html_admin_usuario(client, usuario)

    assert valor_metrica(html, "dias-incompletos") == "1"
    assert valor_metrica(html, "total-dias") == "0"


def test_admin_usuario_doble_entrada_cuenta_un_solo_dia_incompleto(
    client,
    administrador,
    usuario,
):
    crear_fichaje(
        usuario,
        date.today(),
        [
            ("entrada", time(9, 0), "Tienda", False),
            ("entrada", time(10, 0), "Remoto", False),
        ],
    )
    login(client, administrador)

    html = html_admin_usuario(client, usuario)

    assert valor_metrica(html, "dias-incompletos") == "1"


def test_admin_usuario_no_muestra_registros_eliminados(
    client,
    administrador,
    usuario,
):
    crear_fichaje(
        usuario,
        date.today(),
        [
            ("entrada", time(9, 0), "Tienda", False),
            ("salida", time(10, 0), "Tienda", False),
            ("entrada", time(12, 34), "Remoto", True),
        ],
    )
    login(client, administrador)

    html = html_admin_usuario(client, usuario)

    assert "Entrada - 09:00:00 (Tienda)" in html
    assert "12:34:00" not in html
    assert RegistroHorario.query.filter_by(eliminado=True).count() == 1


def test_admin_usuario_media_diaria_usa_duraciones_reales(
    client,
    administrador,
    usuario,
):
    hoy = date.today()
    crear_fichaje(
        usuario,
        hoy.replace(day=1),
        [
            ("entrada", time(8, 0), "Tienda", False),
            ("salida", time(10, 0), "Tienda", False),
        ],
    )
    crear_fichaje(
        usuario,
        hoy.replace(day=2),
        [
            ("entrada", time(8, 0), "Tienda", False),
            ("salida", time(12, 0), "Tienda", False),
        ],
    )
    login(client, administrador)

    html = html_admin_usuario(client, usuario)

    assert valor_metrica(html, "total-dias") == "2"
    assert valor_metrica(html, "total-horas") == "06:00"
    assert valor_metrica(html, "media-horas") == "03:00"


def test_admin_usuario_total_superior_a_24_horas(
    client,
    administrador,
    usuario,
):
    hoy = date.today()
    for numero_dia in (1, 2, 3):
        crear_fichaje(
            usuario,
            hoy.replace(day=numero_dia),
            [
                ("entrada", time(8, 0), "Tienda", False),
                ("salida", time(18, 0), "Tienda", False),
            ],
        )
    login(client, administrador)

    html = html_admin_usuario(client, usuario)

    assert valor_metrica(html, "total-horas") == "30:00"
    assert valor_metrica(html, "media-horas") == "10:00"
    assert html.count("10:00:00") >= 3


def test_dashboard_muestra_estado_sin_fichaje(client, administrador, usuario):
    login(client, administrador)

    fila = fila_dashboard(
        client.get("/admin/dashboard").get_data(as_text=True),
        usuario,
    )

    assert "Sin fichaje" in fila


def test_dashboard_muestra_estado_dentro(client, administrador, usuario):
    crear_fichaje(
        usuario,
        date.today(),
        [("entrada", time(9, 0), "Tienda", False)],
    )
    login(client, administrador)

    fila = fila_dashboard(
        client.get("/admin/dashboard").get_data(as_text=True),
        usuario,
    )

    assert "Dentro" in fila
    assert "En curso" in fila


def test_dashboard_muestra_estado_fuera(client, administrador, usuario):
    crear_fichaje(
        usuario,
        date.today(),
        [
            ("entrada", time(9, 0), "Tienda", False),
            ("salida", time(10, 0), "Tienda", False),
        ],
    )
    login(client, administrador)

    fila = fila_dashboard(
        client.get("/admin/dashboard").get_data(as_text=True),
        usuario,
    )

    assert "Fuera" in fila
    assert "01:00:00" in fila


def test_dashboard_dos_tramos_rellenan_manana_y_tarde(
    client,
    administrador,
    usuario,
):
    crear_fichaje(
        usuario,
        date.today(),
        [
            ("entrada", time(8, 0), "Tienda", False),
            ("salida", time(9, 0), "Tienda", False),
            ("entrada", time(10, 0), "Remoto", False),
            ("salida", time(12, 0), "Remoto", False),
        ],
    )
    login(client, administrador)

    fila = fila_dashboard(
        client.get("/admin/dashboard").get_data(as_text=True),
        usuario,
    )

    for hora in ("08:00", "09:00", "10:00", "12:00"):
        assert hora in fila
    assert "03:00:00" in fila


def test_dashboard_tres_tramos_suman_todos_y_muestran_solo_dos(
    client,
    administrador,
    usuario,
):
    crear_fichaje(
        usuario,
        date.today(),
        [
            ("entrada", time(8, 0), "Tienda", False),
            ("salida", time(9, 0), "Tienda", False),
            ("entrada", time(10, 0), "Tienda", False),
            ("salida", time(11, 0), "Tienda", False),
            ("entrada", time(14, 0), "Remoto", False),
            ("salida", time(16, 0), "Remoto", False),
        ],
    )
    login(client, administrador)

    fila = fila_dashboard(
        client.get("/admin/dashboard").get_data(as_text=True),
        usuario,
    )

    assert "04:00:00" in fila
    assert "14:00" not in fila
    assert "16:00" not in fila


def test_dashboard_indica_tramos_adicionales_en_escritorio_y_movil(
    client,
    administrador,
    usuario,
):
    crear_fichaje(
        usuario,
        date.today(),
        [
            ("entrada", time(8, 0), "Tienda", False),
            ("salida", time(9, 0), "Tienda", False),
            ("entrada", time(10, 0), "Tienda", False),
            ("salida", time(11, 0), "Tienda", False),
            ("entrada", time(12, 0), "Tienda", False),
            ("salida", time(13, 0), "Tienda", False),
        ],
    )
    login(client, administrador)

    html = client.get("/admin/dashboard").get_data(as_text=True)

    assert html.count("+1 tramo") == 2


def test_dashboard_registro_eliminado_no_controla_el_estado(
    client,
    administrador,
    usuario,
):
    crear_fichaje(
        usuario,
        date.today(),
        [("entrada", time(9, 0), "Tienda", True)],
    )
    login(client, administrador)

    fila = fila_dashboard(
        client.get("/admin/dashboard").get_data(as_text=True),
        usuario,
    )

    assert "Sin fichaje" in fila
    assert "Dentro" not in fila
    assert RegistroHorario.query.filter_by(eliminado=True).count() == 1


def test_dashboard_salida_aislada_no_genera_duracion(
    client,
    administrador,
    usuario,
):
    crear_fichaje(
        usuario,
        date.today(),
        [("salida", time(10, 0), "Tienda", False)],
    )
    login(client, administrador)

    fila = fila_dashboard(
        client.get("/admin/dashboard").get_data(as_text=True),
        usuario,
    )

    assert "Fuera" in fila
    assert "00:00:00" not in fila


@pytest.mark.parametrize("tipo", ["Medico", "Médico"])
def test_dashboard_ausencia_medica_no_sustituye_el_estado(
    client,
    administrador,
    usuario,
    tipo,
):
    crear_fichaje(
        usuario,
        date.today(),
        [("entrada", time(9, 0), "Tienda", False)],
    )
    db.session.add(Ausencia(usuario_id=usuario.id, fecha=date.today(), tipo=tipo))
    db.session.commit()
    login(client, administrador)

    fila = fila_dashboard(
        client.get("/admin/dashboard").get_data(as_text=True),
        usuario,
    )

    assert "Dentro" in fila
    assert "Médico" in fila


def test_dashboard_total_cerrado_y_entrada_abierta_muestra_en_curso(
    client,
    administrador,
    usuario,
):
    crear_fichaje(
        usuario,
        date.today(),
        [
            ("entrada", time(8, 0), "Tienda", False),
            ("salida", time(9, 0), "Tienda", False),
            ("entrada", time(10, 0), "Remoto", False),
        ],
    )
    login(client, administrador)

    fila = fila_dashboard(
        client.get("/admin/dashboard").get_data(as_text=True),
        usuario,
    )

    assert "Dentro" in fila
    assert "01:00:00 — En curso" in fila


def test_dashboard_ausencia_bloqueante_no_oculta_el_fichaje(
    client,
    administrador,
    usuario,
):
    crear_fichaje(
        usuario,
        date.today(),
        [
            ("entrada", time(8, 0), "Tienda", False),
            ("salida", time(9, 0), "Tienda", False),
        ],
    )
    db.session.add(
        Ausencia(usuario_id=usuario.id, fecha=date.today(), tipo="Vacaciones")
    )
    db.session.commit()
    login(client, administrador)

    fila = fila_dashboard(
        client.get("/admin/dashboard").get_data(as_text=True),
        usuario,
    )

    assert "Fuera" in fila
    assert "01:00:00" in fila
    assert "Vacaciones" in fila


def test_dashboard_selecciona_ausencia_determinista_por_id(
    client,
    administrador,
    usuario,
):
    db.session.add_all(
        [
            Ausencia(usuario_id=usuario.id, fecha=date.today(), tipo="Vacaciones"),
            Ausencia(usuario_id=usuario.id, fecha=date.today(), tipo="Enfermedad"),
        ]
    )
    db.session.commit()
    login(client, administrador)

    fila = fila_dashboard(
        client.get("/admin/dashboard").get_data(as_text=True),
        usuario,
    )

    assert "Vacaciones" in fila
    assert "Enfermedad" not in fila


def test_tres_tramos_coinciden_en_usuario_y_todas_las_pantallas_admin(
    client,
    administrador,
):
    crear_fichaje(
        administrador,
        date.today(),
        [
            ("entrada", time(8, 0), "Tienda", False),
            ("salida", time(9, 0), "Tienda", False),
            ("entrada", time(10, 0), "Tienda", False),
            ("salida", time(12, 0), "Tienda", False),
            ("entrada", time(13, 0), "Remoto", False),
            ("salida", time(16, 0), "Remoto", False),
        ],
    )
    login(client, administrador)

    paginas = {
        "resumen": client.get("/resumen").get_data(as_text=True),
        "admin": html_admin_fichajes(client),
        "usuario": html_admin_usuario(client, administrador),
        "dashboard": client.get("/admin/dashboard").get_data(as_text=True),
    }

    for html in paginas.values():
        assert "06:00:00" in html

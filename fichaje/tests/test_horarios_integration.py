from datetime import date, datetime, time

from app import db
from app.models import Fichaje, RegistroHorario


def login(client, usuario):
    return client.post(
        "/login",
        data={
            "email": usuario.email,
            "password": "password-correcta",
        },
    )


def crear_dia(usuario, fecha, registros):
    fichaje = Fichaje(
        usuario_id=usuario.id,
        fecha=fecha,
        fecha_creacion=datetime.combine(fecha, time(8, 0)),
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


def paginas_usuario(client):
    return {
        "fichar": client.get("/fichar").get_data(as_text=True),
        "control": client.get("/control-horario").get_data(as_text=True),
        "resumen": client.get("/resumen").get_data(as_text=True),
    }


def test_dos_tramos_muestran_el_mismo_total_en_las_tres_pantallas(
    client,
    usuario,
):
    crear_dia(
        usuario,
        date.today(),
        [
            ("entrada", time(9, 0), "Tienda", False),
            ("salida", time(10, 0), "Tienda", False),
            ("entrada", time(11, 0), "Remoto", False),
            ("salida", time(13, 0), "Remoto", False),
        ],
    )
    login(client, usuario)

    paginas = paginas_usuario(client)

    assert 'id="contador-trabajo">03:00<' in paginas["fichar"]
    assert "Horas trabajadas: 03 h 00 m" in paginas["control"]
    assert "03:00:00" in paginas["resumen"]
    assert "3h 0m 0s" in paginas["resumen"]


def test_tres_tramos_se_contabilizan_completos(client, usuario):
    crear_dia(
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
    login(client, usuario)

    paginas = paginas_usuario(client)

    assert 'id="contador-trabajo">04:00<' in paginas["fichar"]
    assert paginas["control"].count("Entrada:") >= 3
    assert "Horas trabajadas: 04 h 00 m" in paginas["control"]
    assert "04:00:00" in paginas["resumen"]


def test_registro_eliminado_no_se_suma_en_ninguna_pantalla(client, usuario):
    crear_dia(
        usuario,
        date.today(),
        [
            ("entrada", time(9, 0), "Tienda", False),
            ("salida", time(10, 0), "Tienda", False),
            ("entrada", time(11, 0), "Remoto", True),
            ("salida", time(15, 0), "Remoto", True),
        ],
    )
    login(client, usuario)

    paginas = paginas_usuario(client)

    assert 'id="contador-trabajo">01:00<' in paginas["fichar"]
    assert "Horas trabajadas: 01 h 00 m" in paginas["control"]
    assert "01:00:00" in paginas["resumen"]
    assert "4h 0m 0s" not in paginas["resumen"]


def test_entrada_abierta_muestra_estado_dentro(client, usuario):
    crear_dia(
        usuario,
        date.today(),
        [("entrada", time(9, 0), "Auto", False)],
    )
    login(client, usuario)

    paginas = paginas_usuario(client)

    assert "Dentro del trabajo" in paginas["fichar"]
    assert ">Dentro<" in paginas["control"]
    assert "Origen: Auto" in paginas["fichar"]
    assert "const inicio = new Date" in paginas["fichar"]


def test_salida_final_muestra_estado_fuera(client, usuario):
    crear_dia(
        usuario,
        date.today(),
        [
            ("entrada", time(9, 0), "Tienda", False),
            ("salida", time(10, 0), "Tienda", False),
        ],
    )
    login(client, usuario)

    paginas = paginas_usuario(client)

    assert "Fuera del trabajo" in paginas["fichar"]
    assert ">Fuera<" in paginas["control"]
    assert "const inicio = new Date" not in paginas["fichar"]


def test_doble_entrada_no_genera_horas_inventadas(client, usuario):
    crear_dia(
        usuario,
        date.today(),
        [
            ("entrada", time(9, 0), "Tienda", False),
            ("entrada", time(10, 0), "Remoto", False),
            ("salida", time(11, 0), "Tienda", False),
        ],
    )
    login(client, usuario)

    paginas = paginas_usuario(client)

    assert 'id="contador-trabajo">02:00<' in paginas["fichar"]
    assert "Horas trabajadas: 02 h 00 m" in paginas["control"]
    assert "02:00:00" in paginas["resumen"]
    assert "3h 0m 0s" not in paginas["resumen"]


def test_salida_aislada_no_genera_horas(client, usuario):
    crear_dia(
        usuario,
        date.today(),
        [("salida", time(10, 0), "Tienda", False)],
    )
    login(client, usuario)

    paginas = paginas_usuario(client)

    assert 'id="contador-trabajo">00:00<' in paginas["fichar"]
    assert "Horas trabajadas: 00 h 00 m" in paginas["control"]
    assert "0h 0m 0s" in paginas["resumen"]


def test_total_global_de_resumen_supera_24_horas(client, usuario):
    hoy = date.today()
    for dia in (1, 2, 3):
        fecha = hoy.replace(day=dia)
        crear_dia(
            usuario,
            fecha,
            [
                ("entrada", time(8, 0), "Tienda", False),
                ("salida", time(18, 0), "Tienda", False),
            ],
        )
    login(client, usuario)

    html = client.get("/resumen").get_data(as_text=True)

    assert "30h 0m 0s" in html
    assert html.count("10:00:00") == 3


def test_ultima_entrada_str_solo_existe_para_entrada_abierta(client, usuario):
    _, registros = crear_dia(
        usuario,
        date.today(),
        [
            ("entrada", time(9, 0), "Tienda", False),
            ("salida", time(10, 0), "Tienda", False),
        ],
    )
    login(client, usuario)

    html_cerrado = client.get("/fichar").get_data(as_text=True)
    assert "const inicio = new Date" not in html_cerrado

    db.session.delete(registros[1])
    db.session.commit()

    html_abierto = client.get("/fichar").get_data(as_text=True)
    assert "const inicio = new Date" in html_abierto
    assert registros[0].timestamp.isoformat() in html_abierto


def test_contador_parte_del_total_cerrado_y_suma_solo_tramo_abierto(
    client,
    usuario,
):
    crear_dia(
        usuario,
        date.today(),
        [
            ("entrada", time(8, 0), "Tienda", False),
            ("salida", time(9, 0), "Tienda", False),
            ("entrada", time(10, 0), "Remoto", False),
        ],
    )
    login(client, usuario)

    html = client.get("/fichar").get_data(as_text=True)

    assert 'id="contador-trabajo">01:00<' in html
    assert "const totalCerradoSegundos = 3600;" in html
    assert "totalCerradoSegundos + segundosTramoAbierto" in html
    assert "(baseHoras * 3600)" not in html

from datetime import date, datetime, time
from pathlib import Path

import pytest

from app import db
from app.models import Ausencia, Fichaje, RegistroHorario


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = PROJECT_ROOT / "app" / "templates"


def login(client, usuario):
    return client.post(
        "/login",
        data={
            "email": usuario.email,
            "password": "password-correcta",
        },
    )


def crear_fichaje(usuario):
    fichaje = Fichaje(
        usuario_id=usuario.id,
        fecha=date.today(),
        fecha_creacion=datetime.now(),
        creado_por_admin=False,
        eliminado=False,
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
):
    registro = RegistroHorario(
        fichaje_id=fichaje.id,
        tipo=tipo,
        timestamp=datetime.combine(fichaje.fecha, hora),
        creado_por_admin=False,
        eliminado=eliminado,
        origen=origen,
    )
    db.session.add(registro)
    return registro


def guardar_y_cargar_inicio(client, usuario):
    db.session.commit()
    login(client, usuario)
    return client.get("/fichar").get_data(as_text=True)


def cargar_flash(client, category, message):
    with client.session_transaction() as session:
        session["_flashes"] = [(category, message)]
    return client.get("/login").get_data(as_text=True)


def cabecera_toast(html, message):
    posicion = html.index(message)
    inicio = html.rfind('<div class="toast ', 0, posicion)
    assert inicio >= 0
    return html[inicio:posicion]


def test_usuario_fuera_solo_muestra_entrada_y_selector(client, usuario):
    html = guardar_y_cargar_inicio(client, usuario)

    assert "Fichar entrada" in html
    assert 'id="origen_entrada"' in html
    assert 'id="form_entrada"' in html
    assert "Fichar salida" not in html
    assert 'id="form_salida"' not in html


def test_usuario_dentro_solo_muestra_salida_y_origen_abierto(client, usuario):
    fichaje = crear_fichaje(usuario)
    crear_registro(fichaje, "entrada", time(8), origen="Remoto")

    html = guardar_y_cargar_inicio(client, usuario)

    assert "Fichar salida" in html
    assert 'id="form_salida"' in html
    assert "Origen:" in html
    assert "Remoto" in html
    assert "Fichar entrada" not in html
    assert 'id="form_entrada"' not in html
    assert 'id="origen_entrada"' not in html


def test_ausencia_bloqueante_mantiene_aviso_y_oculta_acciones(
    client,
    usuario,
):
    db.session.add(
        Ausencia(
            usuario_id=usuario.id,
            fecha=date.today(),
            tipo="Vacaciones",
            creado_por_admin=False,
        )
    )

    html = guardar_y_cargar_inicio(client, usuario)

    assert "Hoy tienes una ausencia registrada" in html
    assert "Vacaciones" in html
    assert "No hay ninguna acción de fichaje disponible." in html
    assert 'id="form_entrada"' not in html
    assert 'id="form_salida"' not in html


def test_ausencia_medica_mantiene_la_accion_permitida(client, usuario):
    db.session.add(
        Ausencia(
            usuario_id=usuario.id,
            fecha=date.today(),
            tipo="Medico",
            creado_por_admin=False,
        )
    )

    html = guardar_y_cargar_inicio(client, usuario)

    assert 'id="form_entrada"' in html
    assert "Fichar entrada" in html
    assert 'id="form_salida"' not in html


def test_registro_eliminado_no_determina_el_estado_visible(client, usuario):
    fichaje = crear_fichaje(usuario)
    crear_registro(
        fichaje,
        "entrada",
        time(8),
        origen="Remoto",
        eliminado=True,
    )

    html = guardar_y_cargar_inicio(client, usuario)

    assert "Fuera del trabajo" in html
    assert 'id="form_entrada"' in html
    assert 'id="form_salida"' not in html


def test_varios_tramos_usan_el_ultimo_registro_activo_valido(client, usuario):
    fichaje = crear_fichaje(usuario)
    crear_registro(fichaje, "entrada", time(8), origen="Tienda")
    crear_registro(fichaje, "salida", time(9), origen="Tienda")
    crear_registro(fichaje, "entrada", time(10), origen="Remoto")

    html = guardar_y_cargar_inicio(client, usuario)

    assert 'id="form_entrada"' not in html
    assert 'id="form_salida"' in html
    assert "Fichar salida" in html
    assert "Origen:" in html
    assert "Remoto" in html


@pytest.mark.parametrize(
    ("category", "css_category", "delay", "autohide"),
    [
        ("success", "success", "4000", "true"),
        ("info", "info", "5000", "true"),
        ("warning", "warning", "8000", "true"),
        ("danger", "danger", "0", "false"),
    ],
)
def test_toast_respeta_categoria_duracion_y_autocierre(
    client,
    category,
    css_category,
    delay,
    autohide,
):
    message = f"Mensaje {category}"
    html = cargar_flash(client, category, message)
    toast = cabecera_toast(html, message)

    assert f"text-bg-{css_category}" in toast
    assert f'data-bs-delay="{delay}"' in toast
    assert f'data-bs-autohide="{autohide}"' in toast
    assert 'data-bs-dismiss="toast"' in html


def test_toast_sin_categoria_conocida_se_trata_como_info(client):
    html = cargar_flash(client, "message", "Mensaje sin categoría")
    toast = cabecera_toast(html, "Mensaje sin categoría")

    assert "text-bg-info" in toast
    assert 'data-bs-delay="5000"' in toast
    assert 'data-bs-autohide="true"' in toast


def test_toast_escapa_el_contenido(client):
    message = '<script>alert("toast")</script>'
    html = cargar_flash(client, "danger", message)

    assert message not in html
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;/script&gt;" in html


def test_toasts_permiten_varios_mensajes_apilados(client):
    with client.session_transaction() as session:
        session["_flashes"] = [
            ("success", "Primero"),
            ("warning", "Segundo"),
            ("danger", "Tercero"),
        ]

    html = client.get("/login").get_data(as_text=True)

    assert html.count('class="toast app-toast ') == 3
    assert "Primero" in html
    assert "Segundo" in html
    assert "Tercero" in html


def test_flashed_messages_solo_se_consumen_en_la_plantilla_base():
    consumidores = []
    for template in TEMPLATES_ROOT.glob("*.html"):
        source = template.read_text(encoding="utf-8")
        if "get_flashed_messages" in source:
            consumidores.append(template.name)

    assert consumidores == ["base.html"]


def test_alerta_persistente_convive_con_un_toast(client, usuario):
    db.session.add(
        Ausencia(
            usuario_id=usuario.id,
            fecha=date.today(),
            tipo="Baja",
            creado_por_admin=False,
        )
    )
    db.session.commit()
    login(client, usuario)
    with client.session_transaction() as session:
        session["_flashes"] = [("info", "Aviso transitorio")]

    html = client.get("/fichar").get_data(as_text=True)

    assert "Aviso transitorio" in html
    assert 'class="toast app-toast text-bg-info' in html
    assert "Hoy tienes una ausencia registrada" in html
    assert "Baja" in html
    assert 'class="alert alert-danger' in html

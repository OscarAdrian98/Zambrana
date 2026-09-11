import os

from script_guards import require_production_script


if __name__ == "__main__":
    require_production_script(
        "FICHAJE_ALLOW_DISCORD",
        "Discord notifications",
    )

import sys
import pytz
import logging
from datetime import time
from urllib.parse import urlsplit
import requests

# ======================================
# CONFIGURACIÓN GENERAL
# ======================================

def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("log_avisos_fichaje.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

from app import app, db
from app.models import Usuario, RegistroHorario, SabadoAsignado, Ausencia
from app.services.ausencias import (
    ahora_madrid,
    fecha_hoy_madrid,
    usuarios_con_ausencia_bloqueante,
)
from app.services.integrations import require_integration
from app.services.fichajes import (
    LECTURA_FICHAJE_ACTIVO_MULTIPLE,
    resolver_fichaje_activo,
)

zona_es = pytz.timezone("Europe/Madrid")

# ======================================
# CONFIGURACIÓN DE USUARIOS
# ======================================

EXCLUIDOS = [7, 15]
USUARIOS_COMPLETOS = [8, 9, 10, 11, 12, 13, 14, 16]
USUARIOS_SOLO_MAÑANA = []

# ======================================
# DEFINICIÓN DE TRAMOS (MISMA QUE JSON)
# ======================================

TRAMOS = {
    "mañana": {
        "inicio": time(6, 0),
        "fin": time(14, 30),
        "aviso_entrada": time(10, 1),
        "aviso_salida": time(14, 1),
        "usuarios": USUARIOS_COMPLETOS + USUARIOS_SOLO_MAÑANA,
    },
    "tarde": {
        "inicio": time(14, 30),
        "fin": time(21, 0),
        "aviso_entrada": time(16, 1),
        "aviso_salida": time(20, 1),
        "usuarios": USUARIOS_COMPLETOS,
    },
    "sábado": {
        "inicio": time(9, 0),
        "fin": time(13, 30),
        "aviso_entrada": time(10, 1),
        "aviso_salida": time(13, 31),
        "usuarios": [],  # se calcula dinámicamente
    },
}

# ======================================
# FUNCIONES AUXILIARES
# ======================================


DISCORD_WEBHOOK_HOSTS = frozenset({"discord.com", "discordapp.com"})
PLACEHOLDER_MARKERS = ("<", "placeholder", "replace", "changeme", "example.")


def _validate_discord_webhook(value):
    webhook = (value or "").strip()
    if not webhook:
        raise RuntimeError("Missing Discord webhook configuration.")
    lowered = webhook.lower()
    if any(marker in lowered for marker in PLACEHOLDER_MARKERS):
        raise RuntimeError("Invalid Discord webhook configuration.")

    parsed = urlsplit(webhook)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in DISCORD_WEBHOOK_HOSTS
        or not parsed.path.startswith("/api/webhooks/")
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise RuntimeError("Invalid Discord webhook configuration.")
    return webhook


def load_discord_webhook(environ=None):
    environ = os.environ if environ is None else environ
    require_production_script(
        "FICHAJE_ALLOW_DISCORD",
        "Discord notifications",
        environ,
    )
    return _validate_discord_webhook(environ.get("FICHAJE_DISCORD_WEBHOOK"))


def enviar_discord(mensaje, webhook=None):
    webhook = (
        load_discord_webhook()
        if webhook is None
        else _validate_discord_webhook(webhook)
    )
    try:
        r = requests.post(webhook, json={"content": mensaje}, timeout=10)
        if r.status_code == 204:
            logging.info("Mensaje enviado a Discord.")
        else:
            logging.error("Error Discord: HTTP %s.", r.status_code)
    except Exception as exc:
        logging.error(
            "Excepción enviando a Discord (%s).",
            type(exc).__name__,
        )


def estado_tramo(usuario_id, fecha, tramo):
    resultado_fichaje = resolver_fichaje_activo(
        db.session,
        usuario_id=usuario_id,
        fecha=fecha,
    )
    if resultado_fichaje.estado == LECTURA_FICHAJE_ACTIVO_MULTIPLE:
        return "incidencia"

    fichaje = resultado_fichaje.fichaje
    if not fichaje:
        return "no_iniciado"

    registros = (
        db.session.query(RegistroHorario)
        .filter_by(fichaje_id=fichaje.id, eliminado=False)
        .order_by(RegistroHorario.timestamp)
        .all()
    )

    inicio = TRAMOS[tramo]["inicio"]
    fin = TRAMOS[tramo]["fin"]

    entradas = []
    salidas = []

    for r in registros:
        hora = r.timestamp.astimezone(zona_es).time()
        if inicio <= hora <= fin:
            if r.tipo == "entrada":
                entradas.append(r)
            elif r.tipo == "salida":
                salidas.append(r)

    if not entradas:
        return "no_iniciado"

    if len(salidas) < len(entradas):
        return "en_curso"

    return "cerrado"


# ======================================
# FUNCIÓN PRINCIPAL
# ======================================


def procesar_avisos(ahora=None, webhook=None):
    ahora = ahora_madrid(ahora)
    logging.info(f"Hora actual: {ahora.strftime('%Y-%m-%d %H:%M:%S')}")
    fecha_hoy = fecha_hoy_madrid(ahora)
    hora_actual = ahora.time()
    dia_semana = ahora.weekday()
    es_sabado = dia_semana == 5
    es_agosto = ahora.month == 8
    incidencias_reportadas = set()

    if es_sabado and es_agosto:
        return

    ausencias_hoy = db.session.query(Ausencia).filter_by(
        fecha=fecha_hoy
    ).all()
    usuarios_bloqueados = usuarios_con_ausencia_bloqueante(
        ausencias_hoy,
        fecha_hoy,
    )

    for tramo, cfg in TRAMOS.items():

        if tramo == "sábado":
            if not es_sabado:
                continue
            usuarios = [
                s.usuario_id
                for s in db.session.query(SabadoAsignado)
                .filter_by(fecha=fecha_hoy)
                .all()
            ]
        else:
            if es_sabado:
                continue
            if tramo == "tarde" and es_agosto:
                continue
            usuarios = cfg["usuarios"]

        for uid in usuarios:
            if uid in EXCLUIDOS:
                continue
            if uid in usuarios_bloqueados:
                continue

            estado = estado_tramo(uid, fecha_hoy, tramo)
            if estado == "incidencia":
                if uid not in incidencias_reportadas:
                    logging.warning(
                        "FICHAJES_ACTIVOS_MULTIPLES: aviso Discord omitido."
                    )
                    incidencias_reportadas.add(uid)
                continue

            # 🔔 AVISO ENTRADA
            if hora_actual >= cfg["aviso_entrada"] and estado == "no_iniciado":
                tipo = "entrada"

            # 🔔 AVISO SALIDA
            elif hora_actual >= cfg["aviso_salida"] and estado == "en_curso":
                tipo = "salida"

            else:
                continue

            usuario = db.session.query(Usuario).filter_by(id=uid).first()
            if not usuario:
                continue

            mensaje = (
                f"🔔 {usuario.nombre} aún no ha fichado la **{tipo}** "
                f"de la {tramo} ({fecha_hoy.strftime('%d/%m/%Y')})"
            )

            logging.warning(mensaje)
            if webhook is None:
                enviar_discord(mensaje)
            else:
                enviar_discord(mensaje, webhook)


# ======================================
# EJECUCIÓN
# ======================================

if __name__ == "__main__":
    webhook = load_discord_webhook()
    configure_logging()
    require_integration(app, "ALLOW_DISCORD", "Discord notifications")
    with app.app_context():
        procesar_avisos(webhook=webhook)

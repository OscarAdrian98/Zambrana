import os

from script_guards import require_production_script


if __name__ == "__main__":
    require_production_script(
        "FICHAJE_ALLOW_PUSH",
        "Push notifications",
    )

import json
import logging
import requests
from pywebpush import webpush, WebPushException
from urllib.parse import urlsplit


PLACEHOLDER_MARKERS = ("<", "placeholder", "replace", "changeme", "example.")


def _require_external_value(environ, variable):
    value = (environ.get(variable) or "").strip()
    if not value:
        raise RuntimeError(f"Missing push configuration: {variable}")
    lowered = value.lower()
    if any(marker in lowered for marker in PLACEHOLDER_MARKERS):
        raise RuntimeError(f"Invalid push configuration: {variable}")
    return value


def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("log_envio_push.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

def load_push_configuration(environ=None):
    environ = os.environ if environ is None else environ
    if environ.get("FICHAJE_ENV") != "production":
        raise RuntimeError("Push notifications are disabled outside production.")
    if environ.get("FICHAJE_ALLOW_PUSH") != "1":
        raise RuntimeError(
            "Push notifications require explicit FICHAJE_ALLOW_PUSH=1."
        )

    required = {
        "private_key": "FICHAJE_VAPID_PRIVATE_KEY",
        "subject": "FICHAJE_VAPID_SUBJECT",
        "subscriptions_url": "FICHAJE_PUSH_SUBSCRIPTIONS_URL",
    }
    values = {
        name: _require_external_value(environ, variable)
        for name, variable in required.items()
    }
    parsed_url = urlsplit(values["subscriptions_url"])
    if (
        parsed_url.scheme != "https"
        or not parsed_url.hostname
        or parsed_url.username is not None
        or parsed_url.password is not None
    ):
        raise RuntimeError(
            "Invalid push configuration: FICHAJE_PUSH_SUBSCRIPTIONS_URL"
        )
    subject = values["subject"]
    if not (subject.startswith("mailto:") or subject.startswith("https://")):
        raise RuntimeError("Invalid push configuration: FICHAJE_VAPID_SUBJECT")
    return values

# Cargar suscripciones desde URL
def cargar_suscripciones_desde_url(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        lines = response.text.splitlines()
        return [json.loads(line) for line in lines if line.strip()]
    except Exception as exc:
        logging.error(
            "Error cargando suscripciones (%s).",
            type(exc).__name__,
        )
        return []

# Cargar avisos desde archivo local
def cargar_avisos(path="avisos.json"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logging.info("📭 El archivo 'avisos.json' no existe. Posiblemente se eliminó porque no había avisos que generar.")
        return []

# Enviar notificación push
def enviar_notificacion(subscription, mensaje, private_key, subject):
    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps({
                "title": "⏰ Aviso de fichaje",
                "body": mensaje
            }),
            vapid_private_key=private_key,
            vapid_claims={"sub": subject},
            timeout=10
        )
        return True
    except WebPushException as exc:
        status = exc.response.status_code if exc.response else None
        logging.error("Error al enviar notificación push (HTTP %s).", status)
        if status == 410:
            logging.warning("➡️ Suscripción caducada o inválida.")
        return False

def main():
    push_config = load_push_configuration()
    configure_logging()
    suscripciones = cargar_suscripciones_desde_url(
        push_config["subscriptions_url"]
    )
    avisos = cargar_avisos()

    if not suscripciones:
        logging.info("No hay suscriptores registrados.")
        return

    if not avisos:
        logging.info("⛔ No hay avisos para enviar. Se cancela el envío de notificaciones.")
        return

    enviados = 0

    for aviso in avisos:
        email = aviso.get("email")
        mensaje = aviso.get("mensaje")

        for suscripcion in suscripciones:
            if suscripcion.get("email") != email:
                continue

            subscription_data = suscripcion.get("subscription")
            if not subscription_data:
                continue

            if enviar_notificacion(
                subscription_data,
                mensaje,
                push_config["private_key"],
                push_config["subject"],
            ):
                logging.info(f"✅ Notificación enviada a {email}")
                enviados += 1

    logging.info(f"📬 Total de notificaciones enviadas: {enviados}")


if __name__ == "__main__":
    main()

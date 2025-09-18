import json
import logging
import requests
from pywebpush import webpush, WebPushException

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("log_envio_push.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# Claves VAPID (usa tu clave privada para firmar)
VAPID_PRIVATE_KEY = "" # Añadir aquí la clave privada VAPID
VAPID_PUBLIC_KEY = "" # Añadir aquí la clave pública VAPID
VAPID_SUBJECT = "" # Añadir aquí un correo de contacto o URL

# URL del archivo suscripciones.json en tu servidor
URL_SUSCRIPCIONES = "" # Añadir aquí la URL del archivo suscripciones.json

# Cargar suscripciones desde URL
def cargar_suscripciones_desde_url(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        lines = response.text.splitlines()
        return [json.loads(line) for line in lines if line.strip()]
    except Exception as e:
        logging.error(f"Error cargando suscripciones desde {url}: {e}")
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
def enviar_notificacion(subscription, mensaje):
    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps({
                "title": "⏰ Aviso de fichaje",
                "body": mensaje
            }),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_SUBJECT},
            timeout=10
        )
        return True
    except WebPushException as e:
        logging.error(f"❌ Error al enviar notificación: {e}")
        if e.response and e.response.status_code == 410:
            logging.warning("➡️ Suscripción caducada o inválida.")
        return False

# MAIN
if __name__ == "__main__":
    suscripciones = cargar_suscripciones_desde_url(URL_SUSCRIPCIONES)
    avisos = cargar_avisos()

    if not suscripciones:
        logging.info("No hay suscriptores registrados.")
        exit()

    if not avisos:
        logging.info("⛔ No hay avisos para enviar. Se cancela el envío de notificaciones.")
        exit()

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

            if enviar_notificacion(subscription_data, mensaje):
                logging.info(f"✅ Notificación enviada a {email}")
                enviados += 1

    logging.info(f"📬 Total de notificaciones enviadas: {enviados}")
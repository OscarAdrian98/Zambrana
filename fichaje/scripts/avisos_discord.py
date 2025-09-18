import os
import sys
import pytz
import logging
import io
from datetime import datetime, time
import requests

# Forzar salida UTF-8 en consola
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("log_avisos_fichaje.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Añadir la carpeta principal al sys.path para poder importar app
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

# Importar la app Flask y los modelos
from app import app, db
from app.models import Usuario, Fichaje, RegistroHorario, SabadoAsignado, Ausencia

# ---------- CONFIGURACIÓN ----------
zona_es = pytz.timezone("Europe/Madrid")
ahora = datetime.now(zona_es)
logging.info(f"Hora actual detectada: {ahora.strftime('%H:%M:%S')}")

EXCLUIDOS = [7, 15]
USUARIOS_COMPLETOS = [8, 9, 10, 11, 12, 13, 14]
USUARIOS_SOLO_MAÑANA = [16]

DISCORD_WEBHOOK = "" # Añadir aquí el webhook de Discord

# ---------- FUNCIONES ----------
def enviar_discord(mensaje):
    data = {"content": mensaje}
    try:
        response = requests.post(DISCORD_WEBHOOK, json=data)
        if response.status_code == 204:
            logging.info("Mensaje enviado a Discord correctamente.")
        else:
            logging.error(f"Fallo al enviar a Discord: {response.status_code} - {response.text}")
    except Exception as e:
        logging.error(f"Error enviando mensaje a Discord: {e}")

def ha_fichado_en_tramo(usuario_id, fecha, tipo_esperado, tramo):
    fichaje = db.session.query(Fichaje).filter_by(usuario_id=usuario_id, fecha=fecha, eliminado=False).first()
    if not fichaje:
        return False

    registros = db.session.query(RegistroHorario).filter_by(
        fichaje_id=fichaje.id,
        tipo=tipo_esperado,
        eliminado=False
    ).all()

    if tramo == "mañana":
        inicio = time(6, 0)
        fin = time(14, 29, 59)
    elif tramo == "tarde":
        inicio = time(15, 30)
        fin = time(21, 0)
    elif tramo == "sábado":
        inicio = time(9, 0)
        fin = time(13, 30)
    else:
        inicio = time(0, 0)
        fin = time(23, 59, 59)

    for registro in registros:
        hora_fichada = registro.timestamp.astimezone(zona_es).time()
        if inicio <= hora_fichada <= fin:
            return True

    return False

def esta_de_vacaciones(usuario_id, fecha):
    return db.session.query(Ausencia).filter_by(usuario_id=usuario_id, fecha=fecha).first() is not None

def procesar_usuarios():
    fecha_hoy = ahora.date()
    hora_actual = ahora.time()
    dia_semana = ahora.weekday()
    es_sabado = dia_semana == 5
    es_agosto = ahora.month == 8

    horas_objetivo = {
        "manana_entrada": time(10, 0),
        "manana_salida": time(14, 0),
        "tarde_entrada": time(16, 0),
        "tarde_salida": time(20, 0),
        "sabado_entrada": time(10, 0),
        "sabado_salida": time(13, 30),
    }

    reglas = []

    if not es_sabado:
        if hora_actual >= horas_objetivo["manana_entrada"]:
            for uid in USUARIOS_COMPLETOS + USUARIOS_SOLO_MAÑANA:
                reglas.append((uid, "entrada", "mañana"))
        if hora_actual >= horas_objetivo["manana_salida"]:
            for uid in USUARIOS_COMPLETOS + USUARIOS_SOLO_MAÑANA:
                reglas.append((uid, "salida", "mañana"))
        if hora_actual >= horas_objetivo["tarde_entrada"] and not es_agosto:
            for uid in USUARIOS_COMPLETOS:
                reglas.append((uid, "entrada", "tarde"))
        if hora_actual >= horas_objetivo["tarde_salida"] and not es_agosto:
            for uid in USUARIOS_COMPLETOS:
                reglas.append((uid, "salida", "tarde"))
    elif not es_agosto:
        sabados = db.session.query(SabadoAsignado).filter_by(fecha=fecha_hoy).all()
        ids_sabado = [s.usuario_id for s in sabados]
        if hora_actual >= horas_objetivo["sabado_entrada"]:
            for uid in ids_sabado:
                reglas.append((uid, "entrada", "sábado"))
        if hora_actual >= horas_objetivo["sabado_salida"]:
            for uid in ids_sabado:
                reglas.append((uid, "salida", "sábado"))

    if not reglas:
        logging.info("No hay reglas activas en este momento.")
        return

    for usuario_id, tipo, tramo in reglas:
        if usuario_id in EXCLUIDOS:
            logging.info(f"Usuario {usuario_id} excluido.")
            continue
        if esta_de_vacaciones(usuario_id, fecha_hoy):
            logging.info(f"Usuario {usuario_id} está de vacaciones.")
            continue
        if ha_fichado_en_tramo(usuario_id, fecha_hoy, tipo, tramo):
            logging.info(f"Usuario {usuario_id} ya fichó la {tipo} de la {tramo}.")
            continue

        usuario = db.session.query(Usuario).filter_by(id=usuario_id).first()
        if usuario:
            mensaje = f"🔔 {usuario.nombre} aún no ha fichado la **{tipo}** de la {tramo} ({fecha_hoy.strftime('%d/%m/%Y')})"
            logging.warning(f"Aviso: {mensaje}")
            enviar_discord(mensaje)

# ---------- EJECUCIÓN ----------
if __name__ == "__main__":
    with app.app_context():
        procesar_usuarios()
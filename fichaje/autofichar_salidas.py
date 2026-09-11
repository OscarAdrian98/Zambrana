import os

from script_guards import require_production_script


if __name__ == "__main__":
    require_production_script(
        "FICHAJE_ALLOW_AUTOFICHAJE",
        "Automatic clock-out",
    )

import sys
import pytz
import logging
from datetime import datetime, time
from app import app, db
from app.models import Usuario
from app.services.ausencias import (
    ahora_madrid,
    existe_ausencia_bloqueante,
    fecha_hoy_madrid,
)
from app.services.fichajes import (
    AUTO_AUSENCIA_BLOQUEANTE,
    AUTO_ERROR_PERSISTENCIA,
    AUTO_FICHAJES_ACTIVOS_MULTIPLES,
    AUTO_SALIDA_CREADA,
    AUTO_SECUENCIA_ANOMALA,
    AUTO_SIN_FICHAJE_ACTIVO,
    AUTO_SIN_TRAMO_ABIERTO,
    AUTO_TIMESTAMP_INVALIDO,
    AUTO_USUARIO_INEXISTENTE,
    AUTO_YA_CERRADO,
    ErrorRegistroFichaje,
    obtener_entrada_abierta_para_autofichaje,
    registrar_salida_automatica,
)
from app.services.integrations import require_integration

# ================================
# CONFIGURACIÓN Y LOGGING
# ================================

zona_es = pytz.timezone("Europe/Madrid")

def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("log_autofichar.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

EXCLUIDOS = [8]  # IDs de usuarios que NO deben autofichar

# Horas objetivo de autofichaje
HORA_SALIDA_MANANA = time(14, 5)
HORA_SALIDA_TARDE = time(20, 5)


# ================================
# FUNCIONES AUXILIARES
# ================================


def debe_autofichar_usuario(ausencias, fecha):
    """Evalúa solo la regla de ausencias, sin escribir ni comunicar."""
    return not existe_ausencia_bloqueante(ausencias, fecha)


def _hora_madrid(timestamp):
    if timestamp.tzinfo is None:
        return timestamp.time()
    return timestamp.astimezone(zona_es).time().replace(tzinfo=None)


def _instante_programado(fecha, hora_objetivo):
    return zona_es.localize(datetime.combine(fecha, hora_objetivo))


def _momento_salida(fecha, hora_actual, entrada_abierta):
    if entrada_abierta is None:
        hora_objetivo = (
            HORA_SALIDA_TARDE
            if hora_actual >= HORA_SALIDA_TARDE
            else HORA_SALIDA_MANANA
        )
        return _instante_programado(fecha, hora_objetivo), None

    hora_entrada = _hora_madrid(entrada_abierta.timestamp)
    if hora_entrada < time(15, 0) and hora_actual >= HORA_SALIDA_MANANA:
        return _instante_programado(fecha, HORA_SALIDA_MANANA), hora_entrada
    if hora_entrada >= time(15, 0) and hora_actual >= HORA_SALIDA_TARDE:
        return _instante_programado(fecha, HORA_SALIDA_TARDE), hora_entrada
    return None, hora_entrada


def registrar_log_resultado(usuario_nombre, resultado):
    if resultado.codigo == AUTO_SALIDA_CREADA:
        logging.info(
            f"✅ Salida autofichada para {usuario_nombre} "
            f"a las {resultado.instante.time()}"
        )
        return

    mensajes_info = {
        AUTO_AUSENCIA_BLOQUEANTE: (
            f"⏭️ {usuario_nombre} no se procesa porque tiene "
            "ausencia/vacaciones hoy."
        ),
        AUTO_SIN_FICHAJE_ACTIVO: (
            f"⏭️ {usuario_nombre} no tiene fichaje abierto hoy."
        ),
        AUTO_SIN_TRAMO_ABIERTO: (
            f"⏭️ {usuario_nombre} no tiene una entrada activa hoy."
        ),
        AUTO_YA_CERRADO: (
            f"ℹ️ {usuario_nombre} ya tenía cerrado el tramo de trabajo."
        ),
        AUTO_USUARIO_INEXISTENTE: "ℹ️ El usuario de autofichaje ya no existe.",
    }
    if resultado.codigo in mensajes_info:
        logging.info(mensajes_info[resultado.codigo])
        return

    if resultado.codigo == AUTO_ERROR_PERSISTENCIA:
        logging.error(
            f"❌ Error técnico al autofichar la salida de {usuario_nombre}."
        )
        return

    descripciones = {
        AUTO_FICHAJES_ACTIVOS_MULTIPLES: "varios fichajes activos",
        AUTO_SECUENCIA_ANOMALA: "secuencia horaria anómala",
        AUTO_TIMESTAMP_INVALIDO: "timestamp automático no válido",
    }
    logging.warning(
        f"⚠️ Autofichaje omitido para {usuario_nombre}: "
        f"{descripciones.get(resultado.codigo, 'estado no reconocido')}."
    )


def autofichar_salidas(fecha, hora_actual, excluidos=None):
    if excluidos is None:
        excluidos = []

    usuarios = db.session.query(Usuario).filter(~Usuario.id.in_(excluidos)).all()

    for usuario in usuarios:
        usuario_id = usuario.id
        usuario_nombre = usuario.nombre
        try:
            entrada_abierta = obtener_entrada_abierta_para_autofichaje(
                db.session,
                usuario_id,
                fecha,
            )
        except ErrorRegistroFichaje:
            entrada_abierta = None

        momento, hora_entrada = _momento_salida(
            fecha,
            hora_actual,
            entrada_abierta,
        )
        db.session.rollback()

        if momento is None:
            logging.info(
                f"⏳ {usuario_nombre} aún no cumple hora de autofichaje. "
                f"Entrada: {hora_entrada}, hora actual: {hora_actual}"
            )
            continue

        resultado = registrar_salida_automatica(
            db.session,
            usuario_id,
            momento,
        )
        registrar_log_resultado(usuario_nombre, resultado)


# ================================
# EJECUCIÓN PRINCIPAL
# ================================

if __name__ == "__main__":
    configure_logging()
    require_integration(app, "ALLOW_AUTOFICHAJE", "Automatic clock-out")

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    sys.path.append(BASE_DIR)

    ahora = ahora_madrid()
    fecha_hoy = fecha_hoy_madrid(ahora)
    hora_actual = ahora.time()

    with app.app_context():
        logging.info("📍 Ejecutando autofichar_salidas.py")
        logging.info(f"🕒 Fecha: {fecha_hoy} | Hora actual: {hora_actual}")
        autofichar_salidas(fecha_hoy, hora_actual, excluidos=EXCLUIDOS)

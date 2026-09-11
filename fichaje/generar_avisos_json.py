import os

from script_guards import require_production_script


if __name__ == "__main__":
    require_production_script(
        "FICHAJE_ALLOW_PUSH",
        "Push notification generation",
    )

import sys
import pytz
import logging
import json
import holidays
from datetime import time
from app import app, db
from app.models import Usuario, RegistroHorario, SabadoAsignado, Ausencia
from app.services.ausencias import (
    ahora_madrid,
    existe_ausencia_bloqueante,
    fecha_hoy_madrid,
    usuarios_con_ausencia_bloqueante,
)
from app.services.integrations import require_integration
from app.services.fichajes import (
    LECTURA_FICHAJE_ACTIVO_MULTIPLE,
    resolver_fichaje_activo,
)

# ======================================
# CONFIGURACIÓN GENERAL
# ======================================

def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("log_avisos_json.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

zona_es = pytz.timezone("Europe/Madrid")

# ======================================
# CONFIGURACIÓN DE USUARIOS
# ======================================

EXCLUIDOS = [7, 15]

USUARIOS_COMPLETOS = [8, 9, 10, 11, 12, 13, 14, 16]

USUARIOS_SOLO_MAÑANA = []

# ======================================
# DEFINICIÓN DE TRAMOS
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
        "usuarios": [],
    },
}

# ======================================
# FUNCIONES AUXILIARES
# ======================================


def es_festivo(fecha):

    # Festivos nacionales + autonómicos de Andalucía
    festivos = holidays.Spain(subdiv="AN", years=fecha.year)

    resultado = fecha in festivos

    if resultado:
        logging.info(
            f"📅 {fecha} es festivo ({festivos.get(fecha)}). No se generan avisos."
        )
    else:
        logging.info(f"📅 {fecha} no es festivo.")

    return resultado


def debe_generar_aviso_usuario(ausencias, fecha):
    """Evalúa solo la regla de ausencias, sin escribir ni comunicar."""
    return not existe_ausencia_bloqueante(ausencias, fecha)


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


def guardar_avisos(avisos, local_file="avisos.json"):
    if avisos:
        with open(local_file, "w", encoding="utf-8") as output:
            json.dump(avisos, output, ensure_ascii=False, indent=2)
        logging.info(f"avisos.json generado con {len(avisos)} aviso(s).")
        return

    if os.path.exists(local_file):
        os.remove(local_file)
        logging.info("avisos.json eliminado (sin avisos).")


def generar_avisos(ahora=None, local_file="avisos.json"):

    avisos = []
    incidencias_reportadas = set()

    ahora = ahora_madrid(ahora)

    logging.info(f"Hora actual: {ahora.strftime('%Y-%m-%d %H:%M:%S')}")

    fecha_hoy = fecha_hoy_madrid(ahora)
    hora_actual = ahora.time()

    dia_semana = ahora.weekday()

    es_sabado = dia_semana == 5
    es_agosto = ahora.month == 8

    if es_festivo(fecha_hoy):
        logging.info("Hoy es festivo. No se generan avisos.")
        return

    if es_sabado and es_agosto:
        logging.info("Sábado de agosto. No se generan avisos.")
        return avisos

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

            ids_sabado = [
                s.usuario_id
                for s in db.session.query(SabadoAsignado)
                .filter_by(fecha=fecha_hoy)
                .all()
            ]

            usuarios = ids_sabado

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
                        "FICHAJES_ACTIVOS_MULTIPLES: aviso ordinario omitido."
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

            avisos.append(
                {
                    "usuario_id": uid,
                    "email": usuario.email,
                    "nombre": usuario.nombre,
                    "tipo": tipo,
                    "tramo": tramo,
                    "fecha": fecha_hoy.isoformat(),
                    "mensaje": mensaje,
                }
            )

            logging.info(f"Aviso generado: {mensaje}")

    guardar_avisos(avisos, local_file)
    return avisos


# ======================================
# EJECUCIÓN
# ======================================

if __name__ == "__main__":
    configure_logging()
    require_integration(app, "ALLOW_PUSH", "Push notification generation")

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    sys.path.append(BASE_DIR)

    with app.app_context():
        generar_avisos()

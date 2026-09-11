"""Envío de una notificación operativa sin credenciales embebidas."""

import logging
import os
import re
import smtplib
from datetime import datetime
from email.message import EmailMessage
from email import encoders
from pathlib import Path


def nombre_visible_informe(ruta) -> str:
    """Convierte el prefijo interno YYYYMMDD en un nombre humano estable."""

    nombre = Path(ruta).name
    coincidencia = re.match(r"^(\d{8})_", nombre)
    if coincidencia is None:
        raise ValueError("El informe no tiene el nombre interno esperado")
    fecha = datetime.strptime(coincidencia.group(1), "%Y%m%d")
    return f"{fecha.strftime('%d-%m-%Y')}_cambios.txt"


def _configuracion_email() -> dict:
    destinatarios = [
        valor.strip()
        for valor in os.environ.get("STOCK_EMAIL_TO", "").split(",")
        if valor.strip()
    ]
    config = {
        "host": os.environ.get("STOCK_SMTP_HOST", "").strip(),
        "port": int(os.environ.get("STOCK_SMTP_PORT", "587")),
        "user": os.environ.get("STOCK_SMTP_USER", "").strip(),
        "password": os.environ.get("STOCK_SMTP_PASSWORD", ""),
        "to": destinatarios,
    }
    if not all((config["host"], config["user"], config["password"], config["to"])):
        raise RuntimeError("Configuración SMTP operativa incompleta")
    return config


def enviar_correo(
    asunto="Registro de Actualización",
    cuerpo="",
    *,
    informe_cambios=None,
) -> bool:
    """Envía el resumen y, como único adjunto, el informe funcional."""

    try:
        config = _configuracion_email()
        mensaje = EmailMessage()
        mensaje["From"] = config["user"]
        mensaje["To"] = ", ".join(config["to"])
        mensaje["Subject"] = asunto
        mensaje.set_content(cuerpo, subtype="plain", charset="utf-8")
        if informe_cambios is not None:
            ruta_informe = Path(informe_cambios)
            if not ruta_informe.name.endswith("_cambios.txt"):
                raise ValueError(
                    "Solo se permite adjuntar el informe funcional de cambios"
                )
            adjunto = EmailMessage()
            adjunto.set_type("text/plain")
            adjunto.set_param("charset", "utf-8")
            adjunto.set_payload(ruta_informe.read_bytes())
            encoders.encode_base64(adjunto)
            adjunto.add_header(
                "Content-Disposition",
                "attachment",
                filename=nombre_visible_informe(ruta_informe),
            )
            mensaje.make_mixed()
            mensaje.attach(adjunto)
        with smtplib.SMTP(config["host"], config["port"], timeout=30) as server:
            server.starttls()
            server.login(config["user"], config["password"])
            server.send_message(mensaje)
        logging.info("Notificación operativa enviada")
        return True
    except Exception:
        logging.exception("No se pudo enviar la notificación operativa")
        return False

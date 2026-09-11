"""
services/email_service.py - Envio SMTP de correo para pedido (texto + HTML).
"""
import html
import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import Settings

logger = logging.getLogger(__name__)

_jinja_env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html", "xml"]),
)


def enviar_email_cliente_pedido(
    *,
    settings: Settings,
    destinatario: str,
    asunto: str,
    cuerpo: str,
    id_pedido: int,
    referencia: str = "",
    fecha_pedido=None,
    total_pedido: float | None = None,
    nombre_cliente: str = "",
    products: list[dict] | None = None,
    products_extra_count: int = 0,
) -> None:
    to_email = (destinatario or "").strip()
    subject = (asunto or "").strip()
    body = (cuerpo or "").strip()

    if not to_email or "@" not in to_email:
        raise ValueError("Email destino invalido.")
    if not subject:
        raise ValueError("El asunto no puede estar vacio.")
    if not body:
        raise ValueError("El cuerpo del correo no puede estar vacio.")

    smtp_host = (settings.smtp_host or "").strip()
    smtp_user = (settings.smtp_user or "").strip()
    smtp_password = (settings.smtp_password or "").strip()
    smtp_from = (settings.smtp_from or "").strip() or smtp_user
    smtp_port = int(settings.smtp_port or 0)

    if not smtp_host:
        raise ValueError("SMTP_HOST no configurado.")
    if smtp_port <= 0:
        raise ValueError("SMTP_PORT invalido.")
    if not smtp_user:
        raise ValueError("SMTP_USER no configurado.")
    if not smtp_password:
        raise ValueError("SMTP_PASSWORD no configurado.")
    if not smtp_from:
        raise ValueError("SMTP_FROM no configurado.")

    customer_name = (nombre_cliente or "").strip() or "cliente"
    body_html = html.escape(body).replace("\n", "<br>")
    fecha_fmt = _formatear_fecha(fecha_pedido)
    total_fmt = _formatear_importe(total_pedido)
    site_url = (settings.email_site_url or "").strip() or "https://shop.example.invalid"

    context = {
        "company_name": (settings.email_company_name or "MX demo").strip(),
        "site_url": site_url,
        "support_email": (settings.email_support_email or smtp_from).strip(),
        "logo_url": (settings.email_logo_url or "").strip(),
        "subject": subject,
        "customer_name": customer_name,
        "body_text": body,
        "body_html": body_html,
        "id_pedido": id_pedido,
        "referencia": (referencia or "").strip(),
        "fecha_pedido": fecha_fmt,
        "total_pedido": total_fmt,
        "products": products or [],
        "products_extra_count": max(0, int(products_extra_count or 0)),
    }

    text_part = _jinja_env.get_template("emails/pedido_cliente.txt").render(context)
    html_part = _jinja_env.get_template("emails/pedido_cliente.html").render(context)

    logger.info(
        "Email pedido intento id_pedido=%s to=%s subject=%s",
        id_pedido,
        to_email,
        subject,
    )

    msg = MIMEMultipart("alternative")
    msg["From"] = smtp_from
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(text_part, "plain", "utf-8"))
    msg.attach(MIMEText(html_part, "html", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            server.ehlo()
            if settings.smtp_use_tls:
                server.starttls()
                server.ehlo()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        logger.info("Email pedido enviado id_pedido=%s to=%s", id_pedido, to_email)
    except smtplib.SMTPRecipientsRefused:
        logger.exception("Email pedido error id_pedido=%s to=%s", id_pedido, to_email)
        raise ValueError(
            "No se pudo enviar el correo. El destinatario no existe o fue rechazado por el servidor."
        )
    except Exception:
        logger.exception("Email pedido error id_pedido=%s to=%s", id_pedido, to_email)
        raise


def _formatear_fecha(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    if hasattr(value, "strftime"):
        try:
            return value.strftime("%d/%m/%Y %H:%M")
        except Exception:
            return str(value)
    return str(value)


def _formatear_importe(value: float | None) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):.2f} €"
    except Exception:
        return ""

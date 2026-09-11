import smtplib
import socket
from email.message import EmailMessage
import os
import logging
from app.services.empresa_service import obtener_empresa

def _traducir_error_smtp(e):
    err_str = str(e).lower()
    if isinstance(e, socket.timeout):
        return "Timeout: El servidor tardó demasiado en responder. Revisa el host y el puerto."
    if isinstance(e, smtplib.SMTPAuthenticationError):
        return "Autenticación incorrecta: Usuario o contraseña SMTP (de aplicación) inválidos."
    if isinstance(e, smtplib.SMTPConnectError):
        return "Error de conexión: El servidor rechazó la conexión inicial."
    if isinstance(e, socket.gaierror):
        return "Host inválido: No se pudo resolver la dirección del servidor SMTP."
    if isinstance(e, ConnectionRefusedError):
        return "Conexión rechazada: Verifica que el puerto sea correcto y el servidor esté activo."
    if isinstance(e, smtplib.SMTPNotSupportedError):
        return "Seguridad no soportada: El servidor no soporta STARTTLS en este puerto."

    # Errores que a veces envuelven socket.error o ssl.SSLError bajo OSError
    if "wrong version number" in err_str:
        return "Conflicto de Seguridad: Posible desajuste SSL/TLS (Ej. usar TLS en puerto 465 que espera SSL)."
    if "getaddrinfo failed" in err_str:
        return "Host inválido: DNS falló al resolver la dirección."

    return f"Error de red/SMTP: {str(e)}"

def _conectar_y_loguear(smtp_server, smtp_port, smtp_user, smtp_password, smtp_security):
    """
    Gestiona la conexión cruda teniendo en cuenta el timeout,
    los EHLOS y la directiva de seguridad.
    Retorna el objeto server instanciado y conectado. Lanza excepciones si falla.
    """
    server = None
    port_int = int(smtp_port)

    if smtp_security == "SSL":
        server = smtplib.SMTP_SSL(smtp_server, port_int, timeout=15)
        server.login(smtp_user, smtp_password)

    elif smtp_security == "TLS":
        server = smtplib.SMTP(smtp_server, port_int, timeout=15)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_user, smtp_password)

    else:  # "NINGUNA" o vacío
        server = smtplib.SMTP(smtp_server, port_int, timeout=15)
        server.login(smtp_user, smtp_password)

    return server

def enviar_email_con_adjunto(destinatario, asunto, cuerpo_mensaje, ruta_adjunto):
    """
    Envía un email usando los datos de Empresa.
    Rechaza ejecuciones si falta configuración.
    """
    empresa = obtener_empresa()
    if not empresa:
        return False, "No hay datos de empresa configurados."

    (
        nombre, cif, direccion, codigo_postal, poblacion, provincia, pais, email_empresa, telefono, logo, iban_empresa, creditor_id, bic, color_factura,
        smtp_server, smtp_port, smtp_user, smtp_password, smtp_security
    ) = empresa

    if not smtp_server or not smtp_port or not smtp_user or not smtp_password:
        return False, "La configuración SMTP está incompleta en los ajustes de Empresa."

    try:
        msg = EmailMessage()
        msg['Subject'] = asunto
        msg['From'] = f"{nombre} <{smtp_user}>" if nombre else smtp_user
        msg['To'] = destinatario
        msg.set_content(cuerpo_mensaje)

        file_name = None
        if ruta_adjunto and os.path.exists(ruta_adjunto):
            with open(ruta_adjunto, 'rb') as f:
                file_data = f.read()
                file_name = os.path.basename(ruta_adjunto)

            msg.add_attachment(file_data, maintype='application', subtype='pdf', filename=file_name)
        else:
            return False, f"No se encontró el archivo PDF adjunto: {ruta_adjunto}"

        # Conexión pura y envío
        server = _conectar_y_loguear(smtp_server, smtp_port, smtp_user, smtp_password, smtp_security)
        try:
            server.send_message(msg)
        finally:
            server.quit()

        logging.info(f"Email enviado con éxito a {destinatario}")
        return True, "Email enviado con éxito"

    except Exception as e:
        error_traducido = _traducir_error_smtp(e)
        logging.exception(f"Error enviando email: {error_traducido}")
        return False, error_traducido

def probar_conexion_smtp(smtp_server, smtp_port, smtp_user, smtp_password, smtp_security):
    """
    Realiza idéntica comprobación que enviar_email_con_adjunto,
    pero finaliza después de hacer el logueo para testear credenciales.
    """
    try:
        server = _conectar_y_loguear(smtp_server, smtp_port, smtp_user, smtp_password, smtp_security)
        server.quit()
        return True, "Conexión a SMTP y autenticación exitosas"
    except Exception as e:
        error_traducido = _traducir_error_smtp(e)
        return False, error_traducido

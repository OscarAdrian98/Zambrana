import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import logging

smtp_server = 'servidor' # Poner aqui vuestro servidor mail
smtp_port = 587
smtp_user = 'correo' # Poner vuestro correo
smtp_password = 'x78Yoe-x5Q-W'
email_destinatario = ['correo1', 'correo2'] # Lista a los que le llegaran los correos

# Función para enviar registro al correo.
def enviar_correo(asunto='Registro de Actualización', cuerpo='Procesamiento completado'):
    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = ', '.join(email_destinatario)
        msg['Subject'] = asunto

        # Añadir cuerpo del mensaje
        msg.attach(MIMEText(cuerpo, 'plain'))

        with open('Resumen-Stock.log', 'rb') as attachment: # Resumen-Stock.log es lo que va a enviar que es el resumen del programa con lo que ha hecho.
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', "attachment; filename= Resumen-Stock.log")
            msg.attach(part)

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()
        logging.info(f"Correo enviado exitosamente a {', '.join(email_destinatario)}")
    except Exception as e:
        logging.error(f"Error al enviar el correo: {e}")
        print(f"Error al enviar el correo a {', '.join(email_destinatario)}: {e}")

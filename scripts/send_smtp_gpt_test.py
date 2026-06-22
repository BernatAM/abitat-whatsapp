import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart




SMTP_HOST="hm17094.neodigit.net"
SMTP_PORT=587
SMTP_USERNAME="clientes@abitat.net"
SMTP_PASSWORD="Asdfgh123456"
SMTP_FROM_EMAIL="clientes@abitat.net"
SMTP_TO_EMAIL="bernat.amengual97@gmail.com"
SMTP_USE_TLS=True
SMTP_USE_SSL=False

# Contenido del email
subject = "Prueba SMTP"
body = """
Hola,

Este es un email de prueba enviado mediante SMTP.

Si recibes este correo, la configuración funciona correctamente.

Un saludo.
"""

# Crear mensaje
message = MIMEMultipart()
message["From"] = SMTP_FROM_EMAIL
message["To"] = SMTP_TO_EMAIL
message["Subject"] = subject

message.attach(MIMEText(body, "plain", "utf-8"))

try:
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()

        server.login(SMTP_USERNAME.strip(), SMTP_PASSWORD.strip())

        server.sendmail(
            SMTP_FROM_EMAIL,
            SMTP_TO_EMAIL,
            message.as_string()
        )

    print("Email enviado correctamente")

except smtplib.SMTPAuthenticationError as e:
    print("Error de autenticación SMTP")
    print(e)

except Exception as e:
    print("Error enviando el email")
    print(e)
import os
import smtplib
from email.message import EmailMessage
from langchain.tools import StructuredTool  
from dotenv import load_dotenv

load_dotenv()

def send_email_func(recipient: str, subject: str, body: str) -> str:
    """
    Invia un'email a un destinatario.

    Args:
        recipient: L'indirizzo email del destinatario.
        subject: L'oggetto dell'email.
        body: Il contenuto del messaggio.
    """
    try:
        sender = os.getenv("EMAIL_SENDER")
        password = os.getenv("EMAIL_PASSWORD")
        smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", 587))

        if not all([sender, password]):
            return "Errore: EMAIL_SENDER o EMAIL_PASSWORD non configurate."

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = recipient
        msg.set_content(body)

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)

        return f"Email inviata a {recipient} con oggetto: '{subject}'"
    except Exception as e:
        return f"Errore durante l'invio dell'email: {e}"

send_email_tool = StructuredTool.from_function(
    func=send_email_func,
    name="send_email",  
    description="Invia un'email specificando recipient, subject e body."
)

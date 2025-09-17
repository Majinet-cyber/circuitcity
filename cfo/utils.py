import os, tempfile
from django.core.mail import EmailMessage

def generate_pdf_receipt(intent):
    # TODO: replace with real PDF generator (weasyprint/reportlab). Stub writes a .txt as placeholder.
    fd, path = tempfile.mkstemp(prefix=f"receipt_{intent.id}_", suffix=".txt")
    with os.fdopen(fd, "w") as f:
        f.write(f"Receipt for {intent.purpose}\nAmount: {intent.amount} {intent.currency}\nStatus: {intent.status}\n")
    return path

def send_email(to, subject, body, attachments=None):
    msg = EmailMessage(subject, body, to=[to] if isinstance(to, str) else to)
    for a in attachments or []:
        with open(a, "rb") as fh:
            msg.attach(os.path.basename(a), fh.read())
    msg.send(fail_silently=True)

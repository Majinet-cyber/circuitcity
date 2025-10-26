# accounts/emails.py
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

def send_otp_email(to_email: str, code: str, minutes: int = 10, subject: str = "Your verification code"):
    ctx = {"code": code, "minutes": minutes}
    text_body = render_to_string("emails/otp_email.txt", ctx)
    html_body = render_to_string("emails/otp_email.html", ctx)

    msg = EmailMultiAlternatives(subject, text_body, to=[to_email])
    msg.attach_alternative(html_body, "text/html")
    msg.send()



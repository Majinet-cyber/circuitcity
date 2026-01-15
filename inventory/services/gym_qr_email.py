"""
Service for sending gym member QR code PDF via email.
"""
from __future__ import annotations

import logging
from typing import Optional

from django.conf import settings
from django.core.mail import EmailMessage
from django.urls import reverse

from inventory.models_verticals import GymMember
from inventory.views_gym_qr import _generate_member_card_pdf

logger = logging.getLogger(__name__)


def _build_public_status_url(member: GymMember) -> str:
    """
    Build the canonical public member status URL using SITE_BASE_URL.
    Returns a short, clean URL like: https://emajinet.africa/gym/m/<token>/
    """
    # Ensure public_token exists
    if not member.public_token:
        # Trigger save to generate token if missing
        member.save()

    base_url = getattr(settings, "SITE_BASE_URL", "https://emajinet.africa")
    path = reverse("gym:gym_public_member_status", args=[member.public_token])
    return f"{base_url}{path}"


def send_member_qr_email(member: GymMember, request=None) -> bool:
    """
    Send QR code PDF card to member's email address.

    Args:
        member: GymMember instance (must have email and qr_uuid)
        request: HttpRequest for building absolute URLs (optional, used for PDF generation)

    Returns:
        True if email sent successfully, False otherwise
    """
    if not member.email:
        logger.debug(f"Member {member.id} has no email, skipping QR email")
        return False

    if not member.qr_uuid:
        logger.warning(f"Member {member.id} has no qr_uuid, cannot send QR email")
        return False

    try:
        # Generate PDF (requires request for absolute URL in QR code)
        pdf_bytes = None
        if request:
            pdf_bytes = _generate_member_card_pdf(member, request)
            if not pdf_bytes:
                logger.warning(f"Failed to generate PDF for member {member.id}")
                # Continue without PDF attachment

        # Build email subject and body
        business_name = member.business.name if member.business else "Gym"
        subject = "Your Gym QR Code"

        # Build short, canonical public status URL (no click tracking redirect)
        public_url = _build_public_status_url(member)

        body = f"Hi {member.name},\n\n"
        body += f"Welcome to {business_name}! "
        if pdf_bytes:
            body += "Your member QR code is attached.\n\n"
            body += "You can use this QR code to check in at the gym.\n\n"
        else:
            body += "\n\n"
        body += "View your membership status:\n"
        body += f"{public_url}\n\n"
        body += "Thank you for joining!\n"
        body += f"{business_name}"

        # Create email message
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@emajinet.africa")
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_email,
            to=[member.email],
        )

        # Disable click tracking for this email (SendGrid / Anymail)
        # This ensures the link stays as https://emajinet.africa/gym/m/<token>/
        # instead of being wrapped with url8428.../ls/click tracking redirect
        email.esp_extra = {
            "tracking_settings": {
                "click_tracking": {"enable": False, "enable_text": False},
            }
        }

        # Attach PDF if generated
        if pdf_bytes:
            filename = f"Gym-QR-{member.member_number or member.id}.pdf"
            email.attach(filename, pdf_bytes, "application/pdf")

        # Send email
        email.send(fail_silently=False)
        logger.info(f"QR code PDF email sent to {member.email} for member {member.id}")
        return True

    except Exception as e:
        logger.error(f"Failed to send QR code email to {member.email}: {e}", exc_info=True)
        return False


def get_member_public_url(member: GymMember) -> str:
    """
    Get the public member status URL for a member.
    Convenience function for use in templates/views.
    """
    return _build_public_status_url(member)

"""
Service for sending gym member QR code PDF via email.
"""
from __future__ import annotations

import logging
from typing import Optional

from django.conf import settings
from django.core.mail import EmailMessage

from inventory.models_verticals import GymMember
from inventory.views_gym_qr import _generate_member_card_pdf

logger = logging.getLogger(__name__)


def send_member_qr_email(member: GymMember, request) -> bool:
    """
    Send QR code PDF card to member's email address.

    Args:
        member: GymMember instance (must have email and qr_uuid)
        request: HttpRequest for building absolute URLs

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
        # Generate PDF
        pdf_bytes = _generate_member_card_pdf(member, request)
        if not pdf_bytes:
            logger.warning(f"Failed to generate PDF for member {member.id}")
            return False

        # Build email subject and body
        business_name = member.business.name if member.business else "Gym"
        subject = "Your Gym QR Code"

        # Build public status page URL
        from django.urls import reverse

        public_url = request.build_absolute_uri(reverse("gym:member_qr_status_public", args=[str(member.qr_uuid)]))

        body = f"Hi {member.name},\n\n"
        body += f"Welcome to {business_name}! Your member QR code is attached.\n\n"
        body += "You can use this QR code to check in at the gym.\n\n"
        body += f"You can also view your member status online at:\n{public_url}\n\n"
        body += "Thank you for joining!\n"
        body += f"{business_name}"

        # Create email message
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@emajinet.com")
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_email,
            to=[member.email],
        )

        # Attach PDF
        filename = f"Gym-QR-{member.member_number or member.id}.pdf"
        email.attach(filename, pdf_bytes, "application/pdf")

        # Send email
        email.send(fail_silently=False)
        logger.info(f"QR code PDF email sent to {member.email} for member {member.id}")
        return True

    except Exception as e:
        logger.error(f"Failed to send QR code email to {member.email}: {e}", exc_info=True)
        return False

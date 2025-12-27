# notifications/emailer.py
"""
Email sending utilities using Django EmailMultiAlternatives.
Supports HTML and plain text templates.
"""
from __future__ import annotations

import logging
from typing import Optional

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import Context, Template
from django.template.loader import get_template, render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def send_email(
    recipient_email: str,
    subject: str,
    html_template_path: Optional[str] = None,
    text_template_path: Optional[str] = None,
    context: Optional[dict] = None,
    html_content: Optional[str] = None,
    text_content: Optional[str] = None,
    from_email: Optional[str] = None,
    fail_silently: bool = False,
) -> bool:
    """
    Send an email with both HTML and plain text versions.
    
    Args:
        recipient_email: Email address to send to
        subject: Email subject line
        html_template_path: Path to HTML template (e.g., "notifications/emails/welcome_manager.html")
        text_template_path: Path to plain text template (e.g., "notifications/emails/welcome_manager.txt")
        context: Template context dictionary
        html_content: Raw HTML content (alternative to template)
        text_content: Raw plain text content (alternative to template)
        from_email: From email address (defaults to settings.DEFAULT_FROM_EMAIL)
        fail_silently: If True, log errors but don't raise exceptions
    
    Returns:
        True if email was sent successfully, False otherwise
    """
    if context is None:
        context = {}
    
    # Add CANONICAL_HOST to context for email links (if not already present)
    if 'CANONICAL_HOST' not in context:
        context['CANONICAL_HOST'] = getattr(settings, 'CANONICAL_HOST', '')
        # If no canonical host, try to construct from request or use default
        if not context['CANONICAL_HOST']:
            # Fallback: use www.emajinet.africa in production, empty in dev
            context['CANONICAL_HOST'] = 'www.emajinet.africa' if not settings.DEBUG else ''
    
    from_email = from_email or settings.DEFAULT_FROM_EMAIL
    
    # Render templates if provided
    if html_template_path:
        try:
            html_content = render_to_string(html_template_path, context)
        except Exception as e:
            logger.error(f"Failed to render HTML template {html_template_path}: {e}")
            if not fail_silently:
                raise
            html_content = None
    
    if text_template_path:
        try:
            text_content = render_to_string(text_template_path, context)
        except Exception as e:
            logger.error(f"Failed to render text template {text_template_path}: {e}")
            if not fail_silently:
                raise
            text_content = None
    
    # If we have HTML but no text, strip HTML tags
    if html_content and not text_content:
        text_content = strip_tags(html_content)
    
    # Ensure we have at least text content
    if not text_content and not html_content:
        logger.error("No content to send in email")
        if not fail_silently:
            raise ValueError("Email must have either HTML or text content")
        return False
    
    try:
        # Create email message
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content or "",
            from_email=from_email,
            to=[recipient_email],
        )
        
        # Attach HTML alternative if available
        if html_content:
            msg.attach_alternative(html_content, "text/html")
        
        # Send email
        msg.send()
        logger.info(f"Email sent successfully to {recipient_email}: {subject}")
        return True
    
    except Exception as e:
        logger.exception(f"Failed to send email to {recipient_email}: {e}")
        if not fail_silently:
            raise
        return False


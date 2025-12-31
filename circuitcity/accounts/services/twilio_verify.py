"""
Twilio Verify API integration for SMS OTP 2FA.

This service provides:
- send_otp(phone_e164): Send verification code to phone number
- check_otp(phone_e164, code): Verify code against phone number

SECURITY NOTES:
- Never log OTP codes
- All exceptions are caught and returned as error messages
- Uses Twilio Verify API (not raw SMS) for built-in security
"""
from typing import Tuple
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


def send_otp(phone_e164: str) -> Tuple[bool, str | None]:
    """
    Send OTP to the given phone number using Twilio Verify.
    
    Args:
        phone_e164: Phone number in E.164 format (e.g. +265991234567)
    
    Returns:
        Tuple of (success: bool, error_message: str|None)
        - (True, None) on success
        - (False, "error message") on failure
    """
    if not phone_e164:
        return False, "Phone number is required"
    
    # Check if Twilio Verify is configured
    if not getattr(settings, 'TWILIO_VERIFY_ENABLED', False):
        return False, "SMS verification is not configured. Contact your administrator."
    
    try:
        from twilio.rest import Client
        from twilio.base.exceptions import TwilioRestException
        
        account_sid = settings.TWILIO_ACCOUNT_SID
        auth_token = settings.TWILIO_AUTH_TOKEN
        verify_service_sid = settings.TWILIO_VERIFY_SERVICE_SID
        
        client = Client(account_sid, auth_token)
        
        verification = client.verify.v2.services(verify_service_sid).verifications.create(
            to=phone_e164,
            channel='sms'
        )
        
        if verification.status in ('pending', 'approved'):
            # DO NOT LOG THE CODE - security requirement
            logger.info(f"OTP sent to phone ending in {phone_e164[-4:]}, status: {verification.status}")
            return True, None
        else:
            logger.warning(f"Twilio Verify send failed with status: {verification.status}")
            return False, f"Failed to send code (status: {verification.status})"
            
    except TwilioRestException as e:
        logger.error(f"Twilio REST error sending OTP: {e.code} - {e.msg}")
        
        # User-friendly error messages
        if e.code == 60200:
            return False, "Invalid phone number format. Use international format (e.g. +265991234567)"
        elif e.code == 60203:
            return False, "Maximum send attempts reached. Please try again later."
        else:
            return False, f"Unable to send verification code. Please try again later."
    
    except ImportError:
        logger.error("Twilio library not installed")
        return False, "SMS verification is not available. Contact your administrator."
    
    except Exception as e:
        logger.exception(f"Unexpected error sending OTP: {e}")
        return False, "An error occurred while sending the verification code."


def check_otp(phone_e164: str, code: str) -> Tuple[bool, str | None]:
    """
    Verify OTP code for the given phone number using Twilio Verify.
    
    Args:
        phone_e164: Phone number in E.164 format
        code: The OTP code to verify
    
    Returns:
        Tuple of (approved: bool, error_message: str|None)
        - (True, None) if code is correct
        - (False, "error message") if code is wrong or other error
    """
    if not phone_e164:
        return False, "Phone number is required"
    
    if not code:
        return False, "Verification code is required"
    
    # Check if Twilio Verify is configured
    if not getattr(settings, 'TWILIO_VERIFY_ENABLED', False):
        return False, "SMS verification is not configured. Contact your administrator."
    
    try:
        from twilio.rest import Client
        from twilio.base.exceptions import TwilioRestException
        
        account_sid = settings.TWILIO_ACCOUNT_SID
        auth_token = settings.TWILIO_AUTH_TOKEN
        verify_service_sid = settings.TWILIO_VERIFY_SERVICE_SID
        
        client = Client(account_sid, auth_token)
        
        verification_check = client.verify.v2.services(verify_service_sid).verification_checks.create(
            to=phone_e164,
            code=code
        )
        
        if verification_check.status == 'approved':
            # DO NOT LOG THE CODE - security requirement
            logger.info(f"OTP verified successfully for phone ending in {phone_e164[-4:]}")
            return True, None
        elif verification_check.status == 'pending':
            # Code was wrong
            logger.info(f"Invalid OTP attempt for phone ending in {phone_e164[-4:]}")
            return False, "Invalid verification code. Please try again."
        else:
            logger.warning(f"Twilio Verify check returned status: {verification_check.status}")
            return False, "Verification failed. Please request a new code."
    
    except TwilioRestException as e:
        logger.error(f"Twilio REST error checking OTP: {e.code} - {e.msg}")
        
        # User-friendly error messages
        if e.code == 60200:
            return False, "Invalid phone number"
        elif e.code == 60202:
            return False, "Maximum verification attempts reached. Please request a new code."
        elif e.code == 60223:
            return False, "Verification code has expired. Please request a new code."
        else:
            return False, "Unable to verify code. Please try again."
    
    except ImportError:
        logger.error("Twilio library not installed")
        return False, "SMS verification is not available. Contact your administrator."
    
    except Exception as e:
        logger.exception(f"Unexpected error checking OTP: {e}")
        return False, "An error occurred during verification."


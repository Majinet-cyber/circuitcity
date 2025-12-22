"""
Barcode and QR code generation utilities for gym members.
"""
import base64
from io import BytesIO
from typing import Optional

import qrcode
from qrcode.image.svg import SvgPathImage


def generate_member_qr_code(member_code: str, format: str = "base64") -> str:
    """
    Generate a QR code for a gym member.
    
    Args:
        member_code: The unique member code (e.g., "GYM-123456")
        format: Output format - "base64" (default) or "svg"
        
    Returns:
        Base64-encoded PNG image or SVG string
    """
    if not member_code:
        return ""
    
    # Create QR code instance
    qr = qrcode.QRCode(
        version=1,  # Auto-size
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    
    qr.add_data(member_code)
    qr.make(fit=True)
    
    if format == "svg":
        # Generate SVG
        img = qr.make_image(image_factory=SvgPathImage)
        buffer = BytesIO()
        img.save(buffer)
        return buffer.getvalue().decode('utf-8')
    else:
        # Generate PNG and encode as base64
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        img_bytes = buffer.getvalue()
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        return f"data:image/png;base64,{img_base64}"


def generate_member_qr_code_url(member_code: str) -> str:
    """
    Generate a QR code as a data URL (for direct use in <img> tags).
    
    Args:
        member_code: The unique member code
        
    Returns:
        Data URL string ready for <img src="">
    """
    return generate_member_qr_code(member_code, format="base64")


def get_scan_url_for_member(member_code: str, request=None) -> str:
    """
    Generate the scan URL that the QR code should encode.
    
    For now, just returns the member_code itself.
    In the future, could return a full URL like:
    https://yourdomain.com/gym/scan/result/?code=GYM-123456
    
    Args:
        member_code: The unique member code
        request: Optional Django request object to build absolute URL
        
    Returns:
        The scan payload (currently just the member_code)
    """
    # For now, QR code just contains the member_code
    # The scanner will look up the member by this code
    return member_code


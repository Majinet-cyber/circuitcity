# inventory/utils_gym_qr.py
"""
Utilities for gym QR code generation, color themes, and card creation.
"""
from __future__ import annotations

import hashlib
import io
from typing import Tuple

try:
    import qrcode
    from PIL import Image, ImageDraw, ImageFont
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False


def get_member_color_theme(member_id: int, qr_token: str) -> Tuple[str, str, str]:
    """
    Generate a unique, deterministic color theme for a member.
    
    Returns (primary_color, secondary_color, text_color) as hex strings.
    The colors are deterministic based on member_id and qr_token.
    
    Args:
        member_id: Member's database ID
        qr_token: Member's QR token
    
    Returns:
        Tuple of (primary_hex, secondary_hex, text_hex)
    """
    # Color palettes (vibrant, distinct colors)
    color_palettes = [
        ("#6366f1", "#818cf8", "#ffffff"),  # Indigo
        ("#8b5cf6", "#a78bfa", "#ffffff"),  # Purple
        ("#ec4899", "#f472b6", "#ffffff"),  # Pink
        ("#f59e0b", "#fbbf24", "#ffffff"),  # Amber
        ("#10b981", "#34d399", "#ffffff"),  # Emerald
        ("#06b6d4", "#22d3ee", "#ffffff"),  # Cyan
        ("#3b82f6", "#60a5fa", "#ffffff"),  # Blue
        ("#ef4444", "#f87171", "#ffffff"),  # Red
        ("#14b8a6", "#2dd4bf", "#ffffff"),  # Teal
        ("#a855f7", "#c084fc", "#ffffff"),  # Violet
        ("#f97316", "#fb923c", "#ffffff"),  # Orange
        ("#84cc16", "#a3e635", "#ffffff"),  # Lime
    ]
    
    # Generate deterministic hash
    seed = f"{member_id}:{qr_token}"
    hash_obj = hashlib.sha256(seed.encode())
    hash_int = int.from_bytes(hash_obj.digest()[:4], byteorder='big')
    
    # Select palette
    index = hash_int % len(color_palettes)
    return color_palettes[index]


def generate_qr_code_image(data: str, size: int = 300) -> bytes:
    """
    Generate QR code as PNG bytes.
    
    Args:
        data: Data to encode in QR code
        size: Size of QR code in pixels
    
    Returns:
        PNG image bytes
    """
    if not QR_AVAILABLE:
        raise ImportError("qrcode and PIL are required for QR code generation")
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img = img.resize((size, size), Image.Resampling.LANCZOS)
    
    # Convert to bytes
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    return buffer.getvalue()


def generate_member_card_image(
    member_name: str,
    member_phone: str,
    qr_token: str,
    member_id: int,
    business_name: str,
    expiry_date: str = None,
) -> bytes:
    """
    Generate a membership card image with QR code and member details.
    
    Args:
        member_name: Member's full name
        member_phone: Member's phone number
        qr_token: QR token for the member
        member_id: Member's database ID
        business_name: Name of the gym business
        expiry_date: Optional expiry date string
    
    Returns:
        PNG image bytes
    """
    if not QR_AVAILABLE:
        raise ImportError("qrcode and PIL are required for card generation")
    
    # Card dimensions (standard credit card ratio)
    width, height = 800, 500
    
    # Get color theme
    primary_color, secondary_color, text_color = get_member_color_theme(member_id, qr_token)
    
    # Convert hex to RGB
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    primary_rgb = hex_to_rgb(primary_color)
    secondary_rgb = hex_to_rgb(secondary_color)
    text_rgb = hex_to_rgb(text_color)
    
    # Create image with gradient background
    img = Image.new('RGB', (width, height), primary_rgb)
    draw = ImageDraw.Draw(img)
    
    # Draw gradient effect (simple two-tone)
    for y in range(height):
        ratio = y / height
        r = int(primary_rgb[0] * (1 - ratio) + secondary_rgb[0] * ratio)
        g = int(primary_rgb[1] * (1 - ratio) + secondary_rgb[1] * ratio)
        b = int(primary_rgb[2] * (1 - ratio) + secondary_rgb[2] * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    
    # Generate QR code
    qr_img_bytes = generate_qr_code_image(qr_token, size=200)
    qr_img = Image.open(io.BytesIO(qr_img_bytes))
    
    # Paste QR code (right side)
    qr_x = width - 220
    qr_y = (height - 200) // 2
    img.paste(qr_img, (qr_x, qr_y))
    
    # Try to load a font (fallback to default if not available)
    try:
        font_large = ImageFont.truetype("arial.ttf", 36)
        font_medium = ImageFont.truetype("arial.ttf", 24)
        font_small = ImageFont.truetype("arial.ttf", 18)
    except:
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()
    
    # Draw text (left side)
    text_x = 40
    
    # Business name
    draw.text((text_x, 40), business_name.upper(), fill=text_rgb, font=font_small)
    
    # "GYM MEMBERSHIP" label
    draw.text((text_x, 80), "GYM MEMBERSHIP", fill=text_rgb, font=font_medium)
    
    # Member name
    draw.text((text_x, 180), member_name.upper(), fill=text_rgb, font=font_large)
    
    # Member phone
    draw.text((text_x, 240), member_phone, fill=text_rgb, font=font_medium)
    
    # Member ID
    draw.text((text_x, 290), f"ID: {member_id}", fill=text_rgb, font=font_small)
    
    # Expiry date if provided
    if expiry_date:
        draw.text((text_x, 330), f"Valid Until: {expiry_date}", fill=text_rgb, font=font_small)
    
    # Add rounded corners effect (draw white circles at corners)
    corner_radius = 20
    draw.ellipse([0, 0, corner_radius * 2, corner_radius * 2], fill='white')
    draw.ellipse([width - corner_radius * 2, 0, width, corner_radius * 2], fill='white')
    draw.ellipse([0, height - corner_radius * 2, corner_radius * 2, height], fill='white')
    draw.ellipse([width - corner_radius * 2, height - corner_radius * 2, width, height], fill='white')
    
    # Convert to bytes
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    return buffer.getvalue()


def generate_member_card_pdf(
    member_name: str,
    member_phone: str,
    qr_token: str,
    member_id: int,
    business_name: str,
    expiry_date: str = None,
) -> bytes:
    """
    Generate a membership card as PDF.
    
    Args:
        member_name: Member's full name
        member_phone: Member's phone number
        qr_token: QR token for the member
        member_id: Member's database ID
        business_name: Name of the gym business
        expiry_date: Optional expiry date string
    
    Returns:
        PDF bytes
    """
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.utils import ImageReader
    except ImportError:
        raise ImportError("reportlab is required for PDF generation")
    
    # Generate card image first
    card_img_bytes = generate_member_card_image(
        member_name, member_phone, qr_token, member_id, business_name, expiry_date
    )
    
    # Create PDF
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    
    # Add card image to PDF
    img_reader = ImageReader(io.BytesIO(card_img_bytes))
    
    # Center the card on the page
    page_width, page_height = letter
    card_width = 400  # Scale down for PDF
    card_height = 250
    x = (page_width - card_width) / 2
    y = (page_height - card_height) / 2
    
    c.drawImage(img_reader, x, y, width=card_width, height=card_height)
    
    # Add title
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(page_width / 2, y + card_height + 30, "Gym Membership Card")
    
    # Add footer
    c.setFont("Helvetica", 10)
    c.drawCentredString(page_width / 2, 30, f"{business_name} - Scan QR code at gym entrance")
    
    c.save()
    return buffer.getvalue()


# inventory/context_processors_quotes.py
"""
Context processor for vertical-aware hourly quotes and time-based greetings.
Provides motivational quotes and greetings to all dashboard templates.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Dict, Any

from django.utils import timezone


# Vertical-aware quote pools (curated, no external API needed)
QUOTES_BY_VERTICAL = {
    "gym": [
        "Success is the sum of small efforts repeated day in and day out.",
        "The only bad workout is the one that didn't happen.",
        "Strength doesn't come from what you can do. It comes from overcoming the things you thought you couldn't.",
        "Your body can stand almost anything. It's your mind you have to convince.",
        "The pain you feel today will be the strength you feel tomorrow.",
        "Don't stop when you're tired. Stop when you're done.",
        "Fitness is not about being better than someone else. It's about being better than you used to be.",
        "Make fitness a priority, not an afterthought.",
        "The hard days are the best because that's when champions are made.",
        "Every workout is progress.",
        "Discipline is doing what needs to be done, even when you don't want to do it.",
        "Train insane or remain the same.",
    ],
    "clothing": [
        "Fashion is what you buy, style is what you do with it.",
        "Dress like you're already famous.",
        "Style is a way to say who you are without having to speak.",
        "Fashion fades, only style remains the same.",
        "Elegance is the only beauty that never fades.",
        "Create your own style. Let it be unique for yourself and identifiable for others.",
        "In order to be irreplaceable, one must always be different.",
        "Style is knowing who you are, what you want to say, and not giving a damn.",
        "Clothes mean nothing until someone lives in them.",
        "Fashion is about dressing according to what's fashionable. Style is more about being yourself.",
        "The joy of dressing is an art.",
        "Every day is a fashion show, and the world is your runway.",
    ],
    "liquor": [
        "Great service creates memorable experiences.",
        "Hospitality is making your guests feel at home, even when you wish they were.",
        "The customer's perception is your reality.",
        "People will forget what you said, but they'll never forget how you made them feel.",
        "Excellence is not a skill, it's an attitude.",
        "Your vibe attracts your tribe.",
        "Create moments that matter.",
        "The best way to find yourself is to lose yourself in the service of others.",
        "Serve with passion, lead with heart.",
        "Quality is remembered long after price is forgotten.",
        "Exceptional service is the art of making people feel special.",
        "Every interaction is an opportunity to create a loyal customer.",
    ],
    "pharmacy": [
        "Health is wealth. Help your community thrive.",
        "Caring is the essence of pharmacy practice.",
        "Your knowledge saves lives, one prescription at a time.",
        "Excellence in pharmacy is a commitment, not an act.",
        "Pharmacy is not just about medications, it's about care.",
        "Every patient deserves compassionate, professional care.",
        "Knowledge is the foundation, compassion is the catalyst.",
        "Be the trusted voice in your community's health journey.",
        "Precision in practice, compassion in care.",
        "Your attention to detail makes all the difference.",
        "Pharmacy: where science meets caring.",
        "Serve with integrity, care with excellence.",
    ],
    "phones": [
        "Technology is best when it brings people together.",
        "Innovation distinguishes between a leader and a follower.",
        "The best way to predict the future is to invent it.",
        "Stay hungry. Stay foolish.",
        "Great products don't just happen, they're built by great teams.",
        "Your work is going to fill a large part of your life. Make it count.",
        "Quality is more important than quantity.",
        "Technology is nothing. What's important is that you have faith in people.",
        "The customer's experience is your competitive advantage.",
        "Build something people want.",
        "Simplicity is the ultimate sophistication.",
        "Every sale is the beginning of a relationship.",
    ],
    "grocery": [
        "Fresh products, fresh opportunities every day.",
        "Quality service keeps customers coming back.",
        "Every customer is a neighbor. Treat them like family.",
        "Great service is the foundation of success.",
        "A smile is the universal welcome.",
        "Stock your shelves, stock your future.",
        "Every transaction is an opportunity to excel.",
        "Freshness is not just about products, it's about attitude.",
        "Success is built one customer at a time.",
        "Your attention to detail makes the difference.",
        "Consistency builds trust, trust builds loyalty.",
        "Serve with pride, stock with care.",
    ],
    "generic": [
        "Success is not final, failure is not fatal: it is the courage to continue that counts.",
        "The only way to do great work is to love what you do.",
        "Believe you can and you're halfway there.",
        "Quality is not an act, it is a habit.",
        "Excellence is never an accident.",
        "Dream big. Work hard. Stay focused.",
        "Your limitation—it's only your imagination.",
        "Great things never come from comfort zones.",
        "Success doesn't just find you. You have to go out and get it.",
        "The harder you work for something, the greater you'll feel when you achieve it.",
        "Stop doubting yourself. Work hard and make it happen.",
        "Every accomplishment starts with the decision to try.",
    ],
}


def get_greeting(user_first_name: str = "") -> str:
    """
    Get time-based greeting with user's first name.
    
    Morning: 00:00-11:59
    Afternoon: 12:00-17:59
    Evening: 18:00-23:59
    """
    now = timezone.localtime()
    hour = now.hour
    
    if 0 <= hour < 12:
        greeting = "Good morning"
    elif 12 <= hour < 18:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"
    
    if user_first_name:
        return f"{greeting}, {user_first_name}"
    return greeting


def get_hourly_quote(vertical: str = "generic") -> str:
    """
    Get deterministic hourly quote for the given vertical.
    
    Uses (vertical + date + hour) hash to select quote deterministically,
    so the same quote shows for the entire hour without changing on refresh.
    
    Args:
        vertical: One of "gym", "clothing", "liquor", "pharmacy", "phones", "grocery", "generic"
    
    Returns:
        str: Motivational quote
    """
    # Normalize vertical
    vertical = vertical.lower().strip()
    if vertical not in QUOTES_BY_VERTICAL:
        vertical = "generic"
    
    # Get quote pool
    quotes = QUOTES_BY_VERTICAL[vertical]
    if not quotes:
        quotes = QUOTES_BY_VERTICAL["generic"]
    
    # Generate deterministic hash from vertical + date + hour
    now = timezone.localtime()
    seed = f"{vertical}-{now.year}-{now.month}-{now.day}-{now.hour}"
    hash_obj = hashlib.sha256(seed.encode())
    hash_int = int.from_bytes(hash_obj.digest()[:4], byteorder='big')
    
    # Select quote by hash mod length
    index = hash_int % len(quotes)
    return quotes[index]


def quotes_and_greetings(request) -> Dict[str, Any]:
    """
    Context processor that adds quotes and greetings to all templates.
    
    Provides:
        - greeting: Time-based greeting with user's first name
        - motivational_quote: Vertical-aware hourly quote
        - quote_author: Always "Emajinet" (internal branding)
    """
    # Get user first name
    user_first_name = ""
    if request.user.is_authenticated:
        user_first_name = request.user.first_name or request.user.username.split('@')[0].split('.')[0].capitalize()
    
    # Get vertical from business or session
    vertical = "generic"
    try:
        # Try to get from utils (may not always be available)
        from inventory.utils_verticals import get_vertical_kind
        from inventory.helpers import get_active_business
        
        business = get_active_business(request)
        if business:
            vertical = get_vertical_kind(business)
    except Exception:
        # Fallback: try session or request.business
        try:
            if hasattr(request, 'business') and request.business:
                business_kind = getattr(request.business, 'business_kind', None)
                if business_kind:
                    vertical = str(business_kind).lower()
        except Exception:
            pass
    
    return {
        "greeting": get_greeting(user_first_name),
        "motivational_quote": get_hourly_quote(vertical),
        "quote_author": "Emajinet",
    }


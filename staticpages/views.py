from django.shortcuts import render
import random
from decimal import Decimal


def get_cfo_message(total_profit):
    """
    Generate CFO-style advice based on total profit (MWK).
    total_profit is monthly total profit * period
    """
    if total_profit <= 0:
        # loss
        return random.choice([
            "At this rate you're running at a loss. Consider raising your price, reducing costs, or increasing your monthly units sold.",
            "Your current settings show a loss. Try trimming your costs or adjusting your prices to break even and move to profit.",
        ])
    elif total_profit < 400_000:
        return random.choice([
            "You're slightly profitable. A bit more volume or a small price tweak could help you hit your first big milestone.",
            "Not bad – you're above water. Test new sales tactics to grow your monthly profit.",
        ])
    elif total_profit < 2_000_000:
        return random.choice([
            "Nice – this profit can comfortably cover better equipment or small team upgrades.",
            "Good progress. You could reinvest this profit into marketing, inventory, or staff training.",
        ])
    else:
        return random.choice([
            "Wow. With this profit you can start planning that car upgrade or major equipment purchase.",
            "Strong numbers – this level of profit can fund serious expansion or a well-deserved vacation.",
        ])


def home(request):
    """
    Public home page with hero section and marketing copy.
    """
    return render(request, 'staticpages/home.html', {
        'hide_nav': True,  # Don't show internal navigation
    })


def privacy(request):
    """
    Privacy Policy page.
    """
    return render(request, 'staticpages/privacy.html', {
        'hide_nav': True,
    })


def terms(request):
    """
    Terms of Service page.
    """
    return render(request, 'staticpages/terms.html', {
        'hide_nav': True,
    })


def get_cfo_mood(total_profit, profit_margin):
    """
    Determine CFO mood based on profit and margin.
    Returns 'happy', 'serious', or 'neutral'.
    """
    if total_profit <= 0:
        return "serious"
    elif total_profit >= 2_000_000 and profit_margin > 25:
        return "happy"
    elif total_profit < 400_000 or profit_margin < 10:
        return "serious"
    else:
        return "neutral"


def simulator(request):
    """
    Business Simulator page with interactive sliders and charts.
    """
    # Default values for initial page load
    units = 50
    price = 25000
    cost = 18000
    months = 6
    
    # Calculate default profit and margin
    monthly_profit = units * (price - cost)
    total_profit = monthly_profit * months
    monthly_revenue = units * price
    profit_margin = (monthly_profit / monthly_revenue * 100) if monthly_revenue > 0 else 0
    
    # Generate CFO message and mood
    cfo_message = get_cfo_message(total_profit)
    cfo_mood = get_cfo_mood(total_profit, profit_margin)
    
    return render(request, 'staticpages/simulator.html', {
        'hide_nav': True,
        'cfo_message': cfo_message,
        'cfo_mood': cfo_mood,
    })


def about(request):
    """
    About us page.
    """
    return render(request, 'staticpages/about.html', {
        'hide_nav': True,
    })

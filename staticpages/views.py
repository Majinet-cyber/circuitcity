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


def data_deletion(request):
    """
    Data Deletion Policy page (for Meta/WhatsApp compliance).
    """
    return render(request, 'staticpages/data_deletion.html', {
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


def onboarding_manager(request):
    """
    Onboarding guide for store managers and business owners.
    Shows structured content with sections and a PDF download link.
    """
    from django.contrib.auth.decorators import login_required
    
    # Read the markdown content
    import os
    from django.conf import settings
    
    content_path = os.path.join(settings.BASE_DIR, 'staticpages', 'content', 'onboarding_manager.md')
    content_html = ""
    
    try:
        with open(content_path, 'r', encoding='utf-8') as f:
            content_md = f.read()
            # Simple markdown to HTML conversion (basic)
            # For production, use a proper markdown library
            import re
            content_html = content_md
            # Convert headers
            content_html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', content_html, flags=re.MULTILINE)
            content_html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', content_html, flags=re.MULTILINE)
            content_html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', content_html, flags=re.MULTILINE)
            # Convert lists
            content_html = re.sub(r'^- (.+)$', r'<li>\1</li>', content_html, flags=re.MULTILINE)
            # Convert paragraphs
            content_html = content_html.replace('\n\n', '</p><p>')
            content_html = '<p>' + content_html + '</p>'
    except Exception as e:
        content_html = f"<p>Error loading content: {str(e)}</p>"
    
    return render(request, 'staticpages/onboarding_manager.html', {
        'content_html': content_html,
    })


def onboarding_hq(request):
    """
    Onboarding guide for HQ staff and platform administrators.
    Shows structured content with sections and a PDF download link.
    """
    from django.contrib.auth.decorators import login_required
    
    # Check if user is HQ staff
    if not request.user.is_authenticated or not (request.user.is_staff or request.user.is_superuser):
        from django.contrib import messages
        from django.shortcuts import redirect
        messages.error(request, "Only HQ staff can access this page.")
        return redirect('staticpages:home')
    
    # Read the markdown content
    import os
    from django.conf import settings
    
    content_path = os.path.join(settings.BASE_DIR, 'staticpages', 'content', 'onboarding_hq.md')
    content_html = ""
    
    try:
        with open(content_path, 'r', encoding='utf-8') as f:
            content_md = f.read()
            # Simple markdown to HTML conversion (basic)
            import re
            content_html = content_md
            # Convert headers
            content_html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', content_html, flags=re.MULTILINE)
            content_html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', content_html, flags=re.MULTILINE)
            content_html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', content_html, flags=re.MULTILINE)
            # Convert lists
            content_html = re.sub(r'^- (.+)$', r'<li>\1</li>', content_html, flags=re.MULTILINE)
            # Convert paragraphs
            content_html = content_html.replace('\n\n', '</p><p>')
            content_html = '<p>' + content_html + '</p>'
    except Exception as e:
        content_html = f"<p>Error loading content: {str(e)}</p>"
    
    return render(request, 'staticpages/onboarding_hq.html', {
        'content_html': content_html,
    })
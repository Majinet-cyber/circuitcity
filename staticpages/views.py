from django.shortcuts import render
import random
from decimal import Decimal
from django.http import HttpResponse
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.cache import never_cache


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


def get_all_verticals():
    """
    Returns list of all supported verticals (SINGLE SOURCE OF TRUTH).
    
    Each vertical has:
        - code: internal identifier (e.g., 'phones')
        - name: display name (e.g., 'Phones & Electronics')
        - description: short 1-line description
        - icon: emoji or icon representation
    
    This is the canonical list used for landing page, docs, and onboarding.
    """
    return [
        {
            'code': 'phones',
            'name': 'Phones & Electronics',
            'description': 'Track phone inventory, accessories, and repairs',
            'icon': '📱',
        },
        {
            'code': 'gym',
            'name': 'Gym & Fitness',
            'description': 'Manage memberships, check-ins, and trainers',
            'icon': '💪',
        },
        {
            'code': 'farm',
            'name': 'Farm Manager',
            'description': 'Crop & livestock tracking, season management, and farm profitability',
            'icon': '🌾',
        },
        {
            'code': 'pharmacy',
            'name': 'Pharmacy & Cosmetics',
            'description': 'Inventory tracking for medicines and cosmetics',
            'icon': '💊',
        },
        {
            'code': 'clothing',
            'name': 'Clothing Store',
            'description': 'Manage apparel inventory with sizes and colors',
            'icon': '👔',
        },
        {
            'code': 'car_dealer',
            'name': 'Car Dealer',
            'description': 'Vehicle dealership, stock management, sales & marketplace',
            'icon': '🏎️',
        },
        {
            'code': 'liquor',
            'name': 'Liquor Store',
            'description': 'Track bottles, shots, and bar credit',
            'icon': '🍺',
        },
        {
            'code': 'grocery',
            'name': 'Grocery Store',
            'description': 'General merchandise and daily essentials',
            'icon': '🛒',
        },
        {
            'code': 'hardware',
            'name': 'Hardware & General Dealers',
            'description': 'Building materials and hardware supplies',
            'icon': '🔨',
        },
        {
            'code': 'cement',
            'name': 'Cement / Building Materials',
            'description': 'Specialized cement and construction supplies',
            'icon': '🏗️',
        },
        {
            'code': 'welding',
            'name': 'Welding Workshop',
            'description': 'Job estimation and welding project invoicing',
            'icon': '🔥',
        },
        {
            'code': 'car_hire',
            'name': 'Car Hire Service',
            'description': 'Fleet management and vehicle rental bookings',
            'icon': '🚗',
        },
        {
            'code': 'energy',
            'name': 'Renewable Energy',
            'description': 'Monitor solar sites, assets, maintenance, and energy economics',
            'icon': '⚡',
        },
    ]


def get_platform_live_metrics():
    """
    Compute live aggregated platform metrics from actual database records.
    Uses 30-day rolling window. Cached for 10 minutes.

    Returns a dict with:
        has_data          – bool, True only if real records exist
        avg_daily_revenue – int (raw MWK value) or None
        avg_sales_per_day – int or None
        avg_margin_visibility – float (%) or None
    """
    from django.core.cache import cache

    cache_key = 'platform_live_metrics_v1'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = {'has_data': False}
    try:
        from inventory.models import InventoryItem
        from django.db.models import Sum, Count
        from django.db.models.functions import TruncDate
        from django.utils import timezone
        from datetime import timedelta

        thirty_days_ago = timezone.now() - timedelta(days=30)

        sold_qs = InventoryItem.objects.filter(
            status='SOLD',
            sold_at__isnull=False,
            sold_at__gte=thirty_days_ago,
            selling_price__isnull=False,
            order_price__gt=0,
        )

        agg = sold_qs.aggregate(
            total_revenue=Sum('selling_price'),
            total_cost=Sum('order_price'),
            total_count=Count('id'),
        )

        total_revenue = agg.get('total_revenue') or 0
        total_cost = agg.get('total_cost') or 0
        total_count = agg.get('total_count') or 0

        if total_count == 0 or total_revenue <= 0:
            cache.set(cache_key, result, 600)
            return result

        days_with_data = (
            sold_qs
            .annotate(day=TruncDate('sold_at'))
            .values('day')
            .distinct()
            .count()
        )

        if days_with_data == 0:
            cache.set(cache_key, result, 600)
            return result

        avg_daily_rev = int(total_revenue / days_with_data)
        avg_sales = max(1, round(total_count / days_with_data))
        avg_margin = (
            round(float((total_revenue - total_cost) / total_revenue * 100), 1)
            if total_revenue > 0 else None
        )

        result = {
            'has_data': True,
            'avg_daily_revenue': avg_daily_rev,
            'avg_sales_per_day': avg_sales,
            'avg_margin_visibility': avg_margin,
        }
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error('Live metrics error: %s', exc)

    cache.set(cache_key, result, 600)
    return result


@never_cache
def home(request):
    """
    Public home page with hero section and marketing copy.
    Never cached to ensure template updates are visible immediately.

    Uses PUBLIC_SITE_METRICS from settings as SINGLE SOURCE OF TRUTH
    to prevent metric inconsistency across the site.
    """
    from django.conf import settings
    
    # Get centralized metrics (SSOT) from settings
    metrics = getattr(settings, 'PUBLIC_SITE_METRICS', {
        "active_businesses": 34,
        "registered_agents": 0,
        "show_counters": True,
        "min_threshold": 5,
    })
    
    # Extract values
    marketing_businesses = metrics.get("active_businesses", 34)
    min_threshold = metrics.get("min_threshold", 5)
    show_counters_setting = metrics.get("show_counters", True)
    
    try:
        from tenants.models import Business, Membership
        from django.core.cache import cache
        
        # Try cache first (5 minute TTL)
        cache_key = 'platform_stats_home'
        cached_stats = cache.get(cache_key)
        
        if cached_stats:
            db_merchants = cached_stats.get('total_merchants', 0)
            db_agents = cached_stats.get('total_agents', 0)
        else:
            # Count all businesses (no is_active field exists)
            db_merchants = Business.objects.count()
            # Count distinct users with agent role (case-insensitive)
            db_agents = Membership.objects.filter(role__icontains='agent').values('user').distinct().count()
            
            # Cache for 5 minutes
            cache.set(cache_key, {
                'total_merchants': db_merchants,
                'total_agents': db_agents,
            }, 300)
        
        # Use the HIGHER of DB count or marketing constant (ensures consistency)
        total_merchants = max(db_merchants, marketing_businesses)
        total_agents = db_agents
        
    except Exception as e:
        # Graceful degradation if models not available
        import logging
        logging.error(f"Error fetching platform stats: {e}")
        total_merchants = marketing_businesses
        total_agents = 0
    
    # Determine what to show based on thresholds (prevent "0+ Agents" display)
    show_metrics = show_counters_setting and total_merchants >= min_threshold
    show_agents_counter = total_agents >= min_threshold
    
    # Get all supported verticals (SSOT)
    verticals = get_all_verticals()

    # ── Story metrics: live vertical-specific proof data for the carousel ──
    import json as _json
    from staticpages.story_metrics import get_all_story_metrics
    story_metrics_data = get_all_story_metrics()
    story_metrics_json = _json.dumps(story_metrics_data)

    # ── Live platform metrics: real aggregated data, never fake ──
    live_metrics = get_platform_live_metrics()

    return render(request, 'staticpages/home.html', {
        'hide_nav': True,
        'total_merchants': total_merchants,
        'total_agents': total_agents,
        'show_metrics': show_metrics,
        'show_agents_counter': show_agents_counter,
        'verticals': verticals,
        'story_metrics': story_metrics_data,
        'story_metrics_json': story_metrics_json,
        'live_metrics': live_metrics,
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
    Returns 'happy' or 'neutral' — only values with a backing static GIF.
    'serious' mapped to 'neutral' to avoid missing-file crash on collectstatic.
    """
    if total_profit >= 2_000_000 and profit_margin > 25:
        return "happy"
    return "neutral"


def simulator(request):
    """
    Public Business Simulator page - standalone version for anonymous users.
    This is a client-side-only simulator that doesn't require login or business data.
    """
    return render(request, 'staticpages/simulator.html', {
        'hide_nav': True,  # Don't show internal navigation
    })


@never_cache
def about(request):
    """
    About us page.
    """
    return render(request, 'staticpages/about.html', {
        'hide_nav': True,
    })


@never_cache
def pricing(request):
    """
    Premium pricing page with tiers and 30-day free trial.
    """
    return render(request, 'staticpages/pricing.html', {
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


def contact(request):
    """
    Contact form page for custom plan requests, feature requests, and support.
    Implements PRG (Post-Redirect-Get) pattern to prevent duplicate submissions.
    """
    from django.http import JsonResponse
    from django.core.mail import send_mail
    from django.conf import settings
    
    # Check if we're showing success message (after redirect from POST)
    show_success = request.GET.get('sent') == '1'
    
    if request.method == 'POST':
        # Handle AJAX form submission
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            name = request.POST.get('name', '')
            email = request.POST.get('email', '')
            subject = request.POST.get('subject', '')
            message = request.POST.get('message', '')
            
            # Create email body
            email_body = f"""
New contact form submission from Emajinet website:

Name: {name}
Email: {email}
Subject: {subject}

Message:
{message}
"""
            
            # Try to send email (fails gracefully if not configured)
            try:
                support_email = getattr(settings, 'SUPPORT_EMAIL', 'support@emajinet.africa')
                send_mail(
                    f'Emajinet Contact: {subject}',
                    email_body,
                    settings.DEFAULT_FROM_EMAIL,
                    [support_email],
                    fail_silently=True,
                )
            except Exception:
                pass  # Email not configured, that's OK
            
            return JsonResponse({'success': True})
        
        # Handle regular form submission (redirect to success)
        # PRG pattern: redirect to GET with success parameter
        from django.shortcuts import redirect
        from django.urls import reverse
        return redirect(reverse('staticpages:contact') + '?sent=1')
    
    return render(request, 'staticpages/contact.html', {
        'hide_nav': True,
        'show_success': show_success,
    })


def join_team(request):
    """
    Join the Team application page.
    Accepts applications and shows success message (even if email is not configured).
    Safe to use without email backend.
    """
    from django import forms
    from django.core.validators import EmailValidator
    from django.core.mail import send_mail
    from django.conf import settings
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Define form inline
    class JoinTeamForm(forms.Form):
        full_name = forms.CharField(
            max_length=200,
            required=True,
            widget=forms.TextInput(attrs={'placeholder': 'Your full name'})
        )
        email = forms.EmailField(
            required=True,
            validators=[EmailValidator()],
            widget=forms.EmailInput(attrs={'placeholder': 'your.email@example.com'})
        )
        role = forms.ChoiceField(
            required=True,
            choices=[
                ('', '-- Select a role --'),
                ('engineering', 'Engineering'),
                ('operations', 'Operations'),
                ('sales', 'Sales'),
                ('design', 'Design'),
                ('support', 'Customer Support'),
                ('other', 'Other'),
            ]
        )
        linkedin_portfolio = forms.URLField(
            required=False,
            widget=forms.URLInput(attrs={'placeholder': 'https://'})
        )
        message = forms.CharField(
            required=True,
            widget=forms.Textarea(attrs={
                'placeholder': 'Tell us about yourself, your experience, and why you want to join Emajinet...',
                'rows': 5
            })
        )
        
        def clean_role(self):
            role = self.cleaned_data.get('role')
            if not role or role == '':
                raise forms.ValidationError('Please select a role.')
            return role
    
    success = False
    
    if request.method == 'POST':
        form = JoinTeamForm(request.POST)
        
        if form.is_valid():
            # Extract form data
            full_name = form.cleaned_data['full_name']
            email = form.cleaned_data['email']
            role = form.cleaned_data['role']
            linkedin_portfolio = form.cleaned_data.get('linkedin_portfolio', '')
            message_text = form.cleaned_data['message']
            
            # Build email body
            email_body = f"""
New team application received from Emajinet website:

Name: {full_name}
Email: {email}
Role: {role}
LinkedIn/Portfolio: {linkedin_portfolio or 'Not provided'}

Message:
{message_text}
"""
            
            # Try to send email (fails gracefully if not configured)
            try:
                send_mail(
                    f'Team Application: {role} - {full_name}',
                    email_body,
                    settings.DEFAULT_FROM_EMAIL,
                    ['team@emajinet.africa'],
                    fail_silently=True,
                )
                logger.info(f"Team application email sent for {email}")
            except Exception as e:
                # Email not configured or failed - that's OK, don't crash
                logger.warning(f"Email sending failed for team application: {e}")
                pass
            
            # Show success message regardless of email status
            success = True
            messages.success(request, "Thank you! We received your message and we'll get back to you soon.")
            
            return render(request, 'staticpages/join_team.html', {
                'hide_nav': True,
                'success': success,
            })
    else:
        form = JoinTeamForm()
    
    return render(request, 'staticpages/join_team.html', {
        'hide_nav': True,
        'form': form,
        'success': success,
    })


def hq_onboarding_pdf(request):
    """
    Generate and download HQ Staff Onboarding Guide as PDF.
    HQ staff only. Never crashes - returns friendly error if generation fails.
    """
    # Check if user is HQ staff
    if not request.user.is_authenticated:
        return redirect('/accounts/login/')
    
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Only HQ staff can download this PDF.")
        return redirect('staticpages:onboarding_hq')
    
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
        from reportlab.lib.enums import TA_LEFT, TA_CENTER
        from io import BytesIO
        from .onboarding_content import HQ_ONBOARDING_CONTENT
        
        # Create PDF in memory
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=18,
        )
        
        # Container for PDF elements
        story = []
        
        # Get styles
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor='#DC3545',  # Bootstrap danger color
            spaceAfter=30,
            alignment=TA_CENTER,
        )
        
        heading2_style = ParagraphStyle(
            'CustomHeading2',
            parent=styles['Heading2'],
            fontSize=16,
            textColor='#212529',
            spaceAfter=12,
            spaceBefore=20,
        )
        
        heading3_style = ParagraphStyle(
            'CustomHeading3',
            parent=styles['Heading3'],
            fontSize=14,
            textColor='#495057',
            spaceAfter=10,
            spaceBefore=15,
        )
        
        body_style = ParagraphStyle(
            'CustomBody',
            parent=styles['BodyText'],
            fontSize=11,
            spaceAfter=10,
            leading=14,
        )
        
        bullet_style = ParagraphStyle(
            'CustomBullet',
            parent=styles['BodyText'],
            fontSize=11,
            leftIndent=20,
            bulletIndent=10,
            spaceAfter=6,
            leading=14,
        )
        
        alert_style = ParagraphStyle(
            'AlertStyle',
            parent=styles['BodyText'],
            fontSize=11,
            spaceAfter=12,
            spaceBefore=12,
            leftIndent=15,
            rightIndent=15,
            textColor='#721c24',  # Alert text color
        )
        
        # Build PDF content from shared structure
        for item in HQ_ONBOARDING_CONTENT:
            item_type = item.get('type')
            
            if item_type == 'title':
                story.append(Paragraph(item['text'], title_style))
                story.append(Spacer(1, 0.2 * inch))
                
            elif item_type == 'heading':
                level = item.get('level', 2)
                if level == 2:
                    story.append(Paragraph(item['text'], heading2_style))
                elif level == 3:
                    story.append(Paragraph(item['text'], heading3_style))
                    
            elif item_type == 'paragraph':
                story.append(Paragraph(item['text'], body_style))
                
            elif item_type == 'list':
                for list_item in item.get('items', []):
                    bullet_text = f'• {list_item}'
                    story.append(Paragraph(bullet_text, bullet_style))
                story.append(Spacer(1, 0.1 * inch))
                
            elif item_type == 'alert':
                alert_title = item.get('title', '')
                alert_text = item.get('text', '')
                if alert_title:
                    story.append(Paragraph(f'<b>⚠ {alert_title}</b>', alert_style))
                story.append(Paragraph(alert_text, alert_style))
                story.append(Spacer(1, 0.15 * inch))
        
        # Build PDF
        doc.build(story)
        
        # Get PDF from buffer
        pdf = buffer.getvalue()
        buffer.close()
        
        # Return as download
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="hq_staff_onboarding_guide.pdf"'
        return response
        
    except ImportError as e:
        # ReportLab not installed
        messages.error(request, "PDF generation is not available. Please contact support.")
        return redirect('staticpages:onboarding_hq')
    except Exception as e:
        # Any other error - log it but don't crash
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"PDF generation failed: {e}", exc_info=True)
        messages.error(request, "Unable to generate PDF at this time. Please try again later.")
        return redirect('staticpages:onboarding_hq')


def platform_stats_api(request):
    """
    Public API endpoint for live platform growth metrics.
    Returns JSON with total merchants and agents.
    
    Used by homepage to display real-time growth numbers.
    Cached for 5 minutes to prevent database overload.
    """
    from django.core.cache import cache
    from django.http import JsonResponse
    
    METRICS_THRESHOLD = 1  # Minimum credible value to show numbers
    
    # Try to get from cache first (5 minute TTL)
    cache_key = 'platform_stats_public'
    cached_stats = cache.get(cache_key)
    
    if cached_stats:
        return JsonResponse(cached_stats)
    
    # Calculate fresh stats
    try:
        from tenants.models import Business, Membership
        
        # Total merchants (businesses) - no is_active field exists
        total_merchants = Business.objects.count()
        
        # Total registered agents across all businesses (case-insensitive, distinct users)
        total_agents = Membership.objects.filter(
            role__icontains='agent'
        ).values('user').distinct().count()
        
        # Check if metrics meet credibility threshold
        show_metrics = (total_merchants >= METRICS_THRESHOLD) or (total_agents >= METRICS_THRESHOLD)
        
        stats = {
            'total_merchants': total_merchants,
            'total_agents': total_agents,
            'show_metrics': show_metrics,
            'status': 'success',
        }
        
        # Cache for 5 minutes
        cache.set(cache_key, stats, 300)
        
        return JsonResponse(stats)
    
    except Exception as e:
        # Graceful error handling - never crash the public page
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching platform stats: {e}", exc_info=True)
        
        return JsonResponse({
            'total_merchants': 0,
            'total_agents': 0,
            'show_metrics': False,
            'status': 'error',
            'message': 'Unable to fetch stats at this time'
        })


@never_cache
def landing_metrics_api(request):
    """
    Public JSON endpoint for live landing page metrics.
    Refreshed every 60 seconds by the frontend.

    Returns aggregated platform metrics — no merchant-level data exposed.
    Short TTL cache (30s) keeps DB load low while metrics stay fresh.

    Schema:
        active_businesses      int  — businesses with activity in last 30 days
        team_members           int  — active users linked to active businesses
        avg_daily_revenue      int  — MWK, 30-day rolling average
        sales_recorded_per_day int  — 30-day rolling average
        avg_margin_visibility  float|null — percent, null if cost data insufficient
        has_data               bool — True only when real records exist
        as_of                  str  — ISO timestamp of this response
    """
    from django.http import JsonResponse
    from django.core.cache import cache
    from django.utils import timezone

    cache_key = 'landing_metrics_api_v2'
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse(cached)

    # Start from the existing live metrics helper (already DB-aggregated + cached)
    live = get_platform_live_metrics()

    # Active businesses / team members — separate query with activity filter
    active_businesses = 0
    team_members = 0
    try:
        from tenants.models import Business, Membership
        from django.utils import timezone as tz
        from datetime import timedelta

        thirty_days_ago = tz.now() - timedelta(days=30)

        # Businesses active = has at least one sold item in last 30 days
        try:
            from inventory.models import InventoryItem
            active_biz_ids = (
                InventoryItem.objects
                .filter(status='SOLD', sold_at__gte=thirty_days_ago)
                .values_list('business_id', flat=True)
                .distinct()
            )
            active_businesses = active_biz_ids.count()
        except Exception:
            active_businesses = Business.objects.count()

        # Team members = distinct users who are active members of qualifying businesses
        team_members = (
            Membership.objects
            .filter(is_active=True)
            .values('user')
            .distinct()
            .count()
        )
    except Exception:
        pass

    payload = {
        'active_businesses': active_businesses,
        'team_members': team_members,
        'avg_daily_revenue': live.get('avg_daily_revenue') if live.get('has_data') else None,
        'sales_recorded_per_day': live.get('avg_sales_per_day') if live.get('has_data') else None,
        'avg_margin_visibility': live.get('avg_margin_visibility'),
        'has_data': bool(live.get('has_data')),
        'as_of': timezone.now().isoformat(),
        'status': 'success',
    }

    # 30-second TTL — fresh but light on DB
    cache.set(cache_key, payload, 30)
    return JsonResponse(payload)


def developers(request):
    """
    Public Developers page — IoT webhooks, ESP32 integration, credit scoring API foundation,
    and Mobile Money integrations.
    """
    webhook_example = """{
  "device_id": "esp32-energy-001",
  "type": "energy",
  "readings": {
    "voltage": 12.6,
    "current": 4.2,
    "power": 52.9,
    "battery_soc": 78,
    "temperature": 31.5
  },
  "timestamp": "2026-04-28T07:00:00Z"
}"""
    arduino_snippet = """// ESP32 → Emajinet Webhook Example
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

const char* ssid = "YOUR_WIFI";
const char* password = "YOUR_PASS";
const char* webhookUrl = "https://emajinet.africa/iot/webhook/";
const char* apiKey = "YOUR_DEVICE_API_KEY";

void sendReading(float voltage, float current, float power) {
  HTTPClient http;
  http.begin(webhookUrl);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", "Bearer " + String(apiKey));

  StaticJsonDocument<256> doc;
  doc["device_id"] = "esp32-energy-001";
  doc["type"] = "energy";
  doc["readings"]["voltage"] = voltage;
  doc["readings"]["current"] = current;
  doc["readings"]["power"] = power;
  doc["readings"]["temperature"] = 31.5;

  String body;
  serializeJson(doc, body);
  int code = http.POST(body);
  http.end();
}

void loop() {
  sendReading(12.6, 4.2, 52.9);
  delay(60000); // Every 60 seconds
}"""
    return render(request, "staticpages/developers.html", {
        "webhook_example": webhook_example,
        "arduino_snippet": arduino_snippet,
    })


def sitemap_xml(request):
    """
    Generate sitemap.xml with public, indexable pages only.
    Excludes auth, dashboard, and private routes.
    """
    from django.conf import settings
    
    # Get the domain from request
    protocol = 'https' if request.is_secure() else 'http'
    domain = request.get_host()
    base_url = f"{protocol}://{domain}"
    
    # Define public pages with their priorities and change frequencies
    public_pages = [
        {'loc': '/', 'priority': '1.0', 'changefreq': 'daily'},
        {'loc': '/landing/', 'priority': '1.0', 'changefreq': 'daily'},
        {'loc': '/landing/pricing/', 'priority': '0.9', 'changefreq': 'weekly'},
        {'loc': '/landing/about/', 'priority': '0.8', 'changefreq': 'monthly'},
        {'loc': '/landing/contact/', 'priority': '0.8', 'changefreq': 'monthly'},
        {'loc': '/landing/simulator/', 'priority': '0.7', 'changefreq': 'monthly'},
        {'loc': '/landing/join/', 'priority': '0.7', 'changefreq': 'monthly'},
        {'loc': '/landing/privacy/', 'priority': '0.5', 'changefreq': 'monthly'},
        {'loc': '/landing/terms/', 'priority': '0.5', 'changefreq': 'monthly'},
        {'loc': '/landing/data-deletion/', 'priority': '0.5', 'changefreq': 'monthly'},
    ]
    
    # Build XML
    xml_content = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_content.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    
    for page in public_pages:
        xml_content.append('  <url>')
        xml_content.append(f'    <loc>{base_url}{page["loc"]}</loc>')
        xml_content.append(f'    <changefreq>{page["changefreq"]}</changefreq>')
        xml_content.append(f'    <priority>{page["priority"]}</priority>')
        xml_content.append('  </url>')
    
    xml_content.append('</urlset>')
    
    return HttpResponse('\n'.join(xml_content), content_type='application/xml')
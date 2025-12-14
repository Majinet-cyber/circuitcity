# billing/middleware_subscription_gate.py
"""
Subscription gating middleware - enforces subscription status across the app.
Blocks access for businesses with revoked or expired subscriptions.
"""
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin


# URLs that should always be accessible (even for revoked businesses)
ALWAYS_ALLOWED_URLS = [
    "/accounts/login/",
    "/accounts/logout/",
    "/billing/",
    "/billing/subscribe/",
    "/billing/payment/",
    "/static/",
    "/media/",
    "/healthz",
    "/favicon.ico",
]

# URL prefixes that should bypass gating (HQ admin, public pages)
BYPASS_PREFIXES = [
    "/hq/",
    "/__admin__/",
    "/admin/",
    "/accounts/",
    "/api/public/",
]


class SubscriptionGateMiddleware(MiddlewareMixin):
    """
    Middleware that enforces subscription access control.
    
    Blocks access to app features for businesses with:
    - status = 'canceled' or 'expired'
    - current_period_end < now (for active/grace subscriptions)
    
    Allows access to:
    - Login/logout pages
    - Billing/payment pages
    - HQ admin (for support staff)
    - Public/static resources
    """
    
    def process_request(self, request):
        # Skip for non-authenticated users
        if not request.user.is_authenticated:
            return None
        
        # Skip for HQ staff/superusers
        if getattr(request.user, "is_staff", False) or getattr(request.user, "is_superuser", False):
            return None
        
        # Check if path should bypass gating
        path = request.path
        for prefix in BYPASS_PREFIXES:
            if path.startswith(prefix):
                return None
        
        for allowed_url in ALWAYS_ALLOWED_URLS:
            if path.startswith(allowed_url):
                return None
        
        # Get active business
        business = getattr(request, "business", None)
        if not business:
            try:
                from tenants.utils import get_active_business
                business = get_active_business(request)
            except Exception:
                return None
        
        if not business:
            return None
        
        # Check subscription
        try:
            subscription = business.subscription
        except Exception:
            # No subscription - allow access (will be handled by other logic)
            return None
        
        # Check if subscription allows access
        if not self._subscription_allows_access(subscription):
            # Subscription is revoked/expired - block access
            return self._render_subscription_blocked(request, business, subscription)
        
        return None
    
    def _subscription_allows_access(self, subscription) -> bool:
        """Check if subscription status allows access."""
        now = timezone.now()
        status = subscription.status
        
        # Explicitly blocked statuses
        if status in ["canceled", "expired"]:
            return False
        
        # Check if period has expired
        period_end = subscription.current_period_end
        if period_end and period_end < now:
            # Allow grace period if configured
            if status != "grace":
                return False
        
        # Check trial expiration
        if status == "trial":
            trial_end = subscription.trial_end
            if trial_end and trial_end < now:
                return False
        
        # Active, trial (not expired), or grace - allow access
        return True
    
    def _render_subscription_blocked(self, request, business, subscription):
        """Render the subscription blocked page."""
        context = {
            "business": business,
            "subscription": subscription,
            "status": subscription.status,
            "billing_url": reverse("billing:home") if self._has_url("billing:home") else "/billing/",
            "support_email": "support@circuitcity.com",  # Configure this
        }
        
        try:
            return render(request, "billing/subscription_blocked.html", context, status=403)
        except Exception:
            # Fallback if template doesn't exist
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Subscription Inactive</title>
                <style>
                    body {{
                        font-family: system-ui, -apple-system, sans-serif;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        min-height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }}
                    .card {{
                        background: white;
                        border-radius: 16px;
                        padding: 48px;
                        max-width: 500px;
                        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                        text-align: center;
                    }}
                    h1 {{
                        color: #1a202c;
                        font-size: 28px;
                        margin: 0 0 16px 0;
                    }}
                    p {{
                        color: #4a5568;
                        line-height: 1.6;
                        margin: 0 0 24px 0;
                    }}
                    .status {{
                        display: inline-block;
                        padding: 8px 16px;
                        background: #fed7d7;
                        color: #c53030;
                        border-radius: 8px;
                        font-weight: 600;
                        margin-bottom: 24px;
                    }}
                    .btn {{
                        display: inline-block;
                        padding: 12px 32px;
                        background: #667eea;
                        color: white;
                        text-decoration: none;
                        border-radius: 8px;
                        font-weight: 600;
                        transition: all 0.2s;
                    }}
                    .btn:hover {{
                        background: #5568d3;
                        transform: translateY(-2px);
                        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
                    }}
                    .support {{
                        margin-top: 32px;
                        padding-top: 32px;
                        border-top: 1px solid #e2e8f0;
                        color: #718096;
                        font-size: 14px;
                    }}
                </style>
            </head>
            <body>
                <div class="card">
                    <h1>🔒 Subscription Inactive</h1>
                    <div class="status">Status: {subscription.get_status_display()}</div>
                    <p>
                        Your subscription for <strong>{business.name}</strong> is currently inactive.
                        To continue using the platform, please update your subscription or contact support.
                    </p>
                    <a href="{context['billing_url']}" class="btn">View Billing & Payments</a>
                    <div class="support">
                        Need help? Contact us at <strong>{context['support_email']}</strong>
                    </div>
                </div>
            </body>
            </html>
            """
            return HttpResponse(html, status=403)
    
    def _has_url(self, name: str) -> bool:
        """Check if a URL name exists."""
        try:
            reverse(name)
            return True
        except Exception:
            return False


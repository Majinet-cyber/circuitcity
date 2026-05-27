"""
Regression test: Cement dashboard KPI cards must include border_style.

BUG FIX: 2026-01-15
Ensures cement dashboard KPI card dicts always contain 'border_style' key
to prevent VariableDoesNotExist template exceptions.

See: inventory/verticals/cement.py dashboard() view
"""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from inventory.models import Business, BusinessKind
from tenants.models import Membership

User = get_user_model()


@pytest.fixture
def cement_business(db):
    """Create a cement/hardware business."""
    return Business.objects.create(
        name="Test Cement & Hardware",
        business_kind=BusinessKind.CEMENT,
        is_active=True
    )


@pytest.fixture
def cement_user(db, cement_business):
    """Create a user with manager access to cement business."""
    user = User.objects.create_user(
        username="cement_manager",
        email="cement@example.com",
        password="testpass123"
    )
    Membership.objects.create(
        user=user,
        business=cement_business,
        role="MANAGER"
    )
    return user


@pytest.mark.django_db
class TestCementDashboardKPIs:
    """Ensure cement dashboard KPI cards have all required fields."""

    def test_cement_dashboard_kpis_have_border_style(self, client, cement_user, cement_business):
        """
        REGRESSION: Every cement KPI card dict must include 'border_style'.
        
        Before fix: Template tried to resolve card.border_style and logged
        VariableDoesNotExist exceptions, causing test noise and potential issues.
        
        After fix: Each KPI card dict includes border_style derived from color.
        """
        client.force_login(cement_user)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = cement_business.id
        session.save()
        
        # GET cement dashboard
        url = reverse('cement:dashboard')
        response = client.get(url)
        
        # Assert response is successful
        assert response.status_code == 200, "Cement dashboard should render successfully"
        
        # Extract KPI cards from context
        dashboard_config = response.context.get('dashboard_config')
        assert dashboard_config is not None, "dashboard_config must be in context"
        
        kpi_cards = dashboard_config.get('kpis')
        assert kpi_cards is not None, "kpis must be in dashboard_config"
        assert len(kpi_cards) > 0, "At least one KPI card should exist"
        
        # CRITICAL CHECK: Every KPI card must have border_style
        for idx, card in enumerate(kpi_cards):
            assert 'border_style' in card, (
                f"KPI card #{idx} (title='{card.get('title')}') is missing 'border_style' key"
            )
            assert isinstance(card['border_style'], str), (
                f"KPI card #{idx} border_style must be a string"
            )
            assert card['border_style'], (
                f"KPI card #{idx} border_style must not be empty"
            )
            # Verify it looks like valid CSS
            assert 'border:' in card['border_style'] or 'border-' in card['border_style'], (
                f"KPI card #{idx} border_style should contain border CSS: {card['border_style']}"
            )

    def test_cement_dashboard_kpis_structure(self, client, cement_user, cement_business):
        """
        Verify cement KPI cards have expected structure.
        """
        client.force_login(cement_user)
        
        session = client.session
        session['active_business_id'] = cement_business.id
        session.save()
        
        url = reverse('cement:dashboard')
        response = client.get(url)
        
        dashboard_config = response.context['dashboard_config']
        kpi_cards = dashboard_config['kpis']
        
        # Expected KPI titles for cement vertical
        expected_titles = {'Revenue', 'Profit', 'Stock Value', 'Costs'}
        actual_titles = {card['title'] for card in kpi_cards}
        
        assert expected_titles.issubset(actual_titles), (
            f"Missing expected KPIs. Expected: {expected_titles}, Got: {actual_titles}"
        )
        
        # Each card should have required fields
        required_fields = {'title', 'icon', 'value', 'subtitle', 'color', 'border_style'}
        for card in kpi_cards:
            missing = required_fields - card.keys()
            assert not missing, f"Card '{card.get('title')}' missing fields: {missing}"

    def test_cement_dashboard_border_style_derived_from_color(self, client, cement_user, cement_business):
        """
        Verify border_style is correctly derived from card color hex.
        
        Implementation uses 20% opacity (0x33 alpha) for glass-morphic effect.
        """
        client.force_login(cement_user)
        
        session = client.session
        session['active_business_id'] = cement_business.id
        session.save()
        
        url = reverse('cement:dashboard')
        response = client.get(url)
        
        dashboard_config = response.context['dashboard_config']
        kpi_cards = dashboard_config['kpis']
        
        for card in kpi_cards:
            color = card['color']
            border_style = card['border_style']
            
            # Border style should reference the card's color
            assert color in border_style, (
                f"Card '{card['title']}' border_style should reference its color {color}"
            )
            
            # Should contain opacity suffix (like 33 for 20% alpha)
            assert f"{color}33" in border_style or "rgba" in border_style, (
                f"Card '{card['title']}' border_style should have transparency"
            )


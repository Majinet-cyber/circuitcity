"""
Tests for the Business Simulator on the public home page.

The simulator is a purely illustrative, front-end tool that does NOT 
interact with real business data, wallets, costs, or inventory.

These tests ensure:
1. The simulator section renders correctly
2. The formula logic is correct and predictable
3. Default values are consistent
4. The simulator is NOT coupled to real database models
"""
import pytest
from django.urls import reverse
from staticpages.utils_simulator import simulator_defaults, simulator_compute


pytestmark = pytest.mark.django_db


# ============================================
# RENDERING TESTS
# ============================================

def test_home_page_contains_business_simulator(client):
    """Test that the home page contains the business simulator section."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check for simulator container
    assert 'id="business-simulator"' in content
    
    # Check for section title
    assert "Business Simulator" in content
    
    
def test_simulator_has_all_input_elements(client):
    """Test that the simulator contains all required input elements."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check for input elements with stable IDs
    assert 'id="sim-customers"' in content
    assert 'id="sim-average-sale"' in content
    assert 'id="sim-cost-percent"' in content
    

def test_simulator_has_all_display_elements(client):
    """Test that the simulator contains all KPI display elements."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check for display elements with stable IDs
    assert 'id="sim-revenue"' in content
    assert 'id="sim-costs"' in content
    assert 'id="sim-profit"' in content


def test_simulator_has_descriptive_labels(client):
    """Test that the simulator has clear, user-friendly labels."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check for descriptive labels
    assert "Number of customers per month" in content or "customers per month" in content.lower()
    assert "Average spend per customer" in content or "average spend" in content.lower()
    assert "Costs as % of revenue" in content or "costs as %" in content.lower()
    
    # Check for result labels
    assert "revenue" in content.lower()
    assert "costs" in content.lower() or "cost" in content.lower()
    assert "profit" in content.lower()


def test_simulator_has_educational_hint(client):
    """Test that the simulator includes educational hints for users."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check for hint text
    assert "This is a quick simulator" in content or "not your actual data" in content.lower()
    assert "Emajinet" in content and ("track real numbers" in content.lower() or "install" in content.lower())


# ============================================
# FORMULA & LOGIC TESTS
# ============================================

def test_simulator_defaults_are_reasonable():
    """Test that default simulator values are reasonable."""
    defaults = simulator_defaults()
    
    assert "customers" in defaults
    assert "average_sale" in defaults
    assert "cost_pct" in defaults
    
    # Check that defaults are positive
    assert defaults["customers"] > 0
    assert defaults["average_sale"] > 0
    assert defaults["cost_pct"] > 0
    
    # Check that cost percentage is between 0 and 100
    assert 0 <= defaults["cost_pct"] <= 100


def test_simulator_formula_with_defaults():
    """Test that the simulator formula works correctly with default values."""
    defaults = simulator_defaults()
    revenue, costs, profit = simulator_compute(
        defaults["customers"],
        defaults["average_sale"],
        defaults["cost_pct"],
    )
    
    # Check formula correctness
    expected_revenue = defaults["customers"] * defaults["average_sale"]
    expected_costs = expected_revenue * (defaults["cost_pct"] / 100.0)
    expected_profit = expected_revenue - expected_costs
    
    assert revenue == expected_revenue
    assert costs == expected_costs
    assert profit == expected_profit


def test_simulator_formula_basic_case():
    """Test the simulator formula with a simple example."""
    # 100 customers, MWK 10,000 per customer, 40% costs
    revenue, costs, profit = simulator_compute(100, 10000, 40)
    
    assert revenue == 1_000_000  # 100 * 10,000
    assert costs == 400_000  # 1,000,000 * 0.4
    assert profit == 600_000  # 1,000,000 - 400,000


def test_simulator_formula_zero_customers():
    """Test simulator formula when there are zero customers."""
    revenue, costs, profit = simulator_compute(0, 10000, 40)
    
    assert revenue == 0
    assert costs == 0
    assert profit == 0


def test_simulator_formula_zero_average_sale():
    """Test simulator formula when average sale is zero."""
    revenue, costs, profit = simulator_compute(100, 0, 40)
    
    assert revenue == 0
    assert costs == 0
    assert profit == 0


def test_simulator_formula_zero_cost_percent():
    """Test simulator formula when cost percentage is zero (100% profit margin)."""
    revenue, costs, profit = simulator_compute(100, 10000, 0)
    
    assert revenue == 1_000_000
    assert costs == 0
    assert profit == 1_000_000


def test_simulator_formula_100_percent_cost():
    """Test simulator formula when cost percentage is 100% (no profit)."""
    revenue, costs, profit = simulator_compute(100, 10000, 100)
    
    assert revenue == 1_000_000
    assert costs == 1_000_000
    assert profit == 0


def test_simulator_formula_high_cost_percent():
    """Test simulator formula with high cost percentage (80%)."""
    revenue, costs, profit = simulator_compute(100, 10000, 80)
    
    assert revenue == 1_000_000
    assert costs == 800_000
    assert profit == 200_000


def test_simulator_formula_different_values():
    """Test simulator formula with various different input values."""
    # Test case 1: 50 customers, MWK 25,000 avg, 30% costs
    revenue, costs, profit = simulator_compute(50, 25000, 30)
    assert revenue == 1_250_000
    assert costs == 375_000
    assert profit == 875_000
    
    # Test case 2: 200 customers, MWK 5,000 avg, 50% costs
    revenue, costs, profit = simulator_compute(200, 5000, 50)
    assert revenue == 1_000_000
    assert costs == 500_000
    assert profit == 500_000
    
    # Test case 3: 1,000 customers, MWK 1,000 avg, 20% costs
    revenue, costs, profit = simulator_compute(1000, 1000, 20)
    assert revenue == 1_000_000
    assert costs == 200_000
    assert profit == 800_000


def test_simulator_formula_handles_floats():
    """Test that the simulator formula handles float inputs correctly."""
    revenue, costs, profit = simulator_compute(100.5, 9999.99, 40.5)
    
    expected_revenue = 100.5 * 9999.99
    expected_costs = expected_revenue * 0.405
    expected_profit = expected_revenue - expected_costs
    
    # Use approximate equality for floating point
    assert abs(revenue - expected_revenue) < 0.01
    assert abs(costs - expected_costs) < 0.01
    assert abs(profit - expected_profit) < 0.01


def test_simulator_profit_always_equals_revenue_minus_costs():
    """Test that profit always equals revenue minus costs (invariant)."""
    import random
    
    # Test with 10 random combinations
    for _ in range(10):
        customers = random.randint(0, 1000)
        avg_sale = random.randint(0, 50000)
        cost_pct = random.randint(0, 100)
        
        revenue, costs, profit = simulator_compute(customers, avg_sale, cost_pct)
        
        # Invariant: profit = revenue - costs (with floating point tolerance)
        assert abs(profit - (revenue - costs)) < 0.01, \
            f"Invariant broken for customers={customers}, avg_sale={avg_sale}, cost_pct={cost_pct}"


# ============================================
# NO DATABASE COUPLING TESTS
# ============================================

def test_simulator_utils_do_not_import_models():
    """Test that simulator utilities don't import real business models."""
    import staticpages.utils_simulator as sim_utils
    import inspect
    
    source = inspect.getsource(sim_utils)
    
    # Ensure no imports of real business models
    forbidden_imports = [
        "from wallet",
        "from inventory",
        "from dashboard",
        "import wallet",
        "import inventory",
        "import dashboard",
        "models.Wallet",
        "models.Cost",
        "models.Order",
    ]
    
    for forbidden in forbidden_imports:
        assert forbidden not in source, \
            f"Simulator utilities should not import real models, found: {forbidden}"


def test_simulator_functions_are_pure():
    """Test that simulator compute function is pure (no side effects)."""
    # Pure function should return same output for same input
    result1 = simulator_compute(100, 10000, 40)
    result2 = simulator_compute(100, 10000, 40)
    
    assert result1 == result2
    
    # Result should be tuple of 3 floats
    assert len(result1) == 3
    assert all(isinstance(x, float) for x in result1)


# ============================================
# INTEGRATION TESTS
# ============================================

def test_simulator_does_not_break_home_page(client):
    """Test that adding the simulator doesn't break the home page."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Ensure other sections still exist
    assert "How It Works" in content
    assert "Powerful Features" in content or "Features" in content
    assert "Our Mission" in content
    assert "Emajinet" in content


def test_home_page_has_simulator_javascript(client):
    """Test that the home page includes the simulator JavaScript."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check for key JavaScript functions
    assert "initBusinessSimulator" in content
    assert "formatMoney" in content or "formatCurrency" in content
    assert "recalc" in content or "calculate" in content


def test_simulator_inputs_have_default_values(client):
    """Test that simulator inputs have sensible default values."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Extract default values from HTML (simple check)
    # Should have value attributes on inputs
    assert 'value=' in content
    
    # Values should be positive numbers (not checking exact values)
    # Just ensuring the inputs aren't empty


def test_simulator_is_mobile_responsive(client):
    """Test that the simulator section includes responsive design."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check for responsive grid (grid-template-columns with auto-fit or similar)
    assert "grid-template-columns" in content.lower()
    assert "auto-fit" in content.lower() or "repeat" in content.lower()


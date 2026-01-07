/**
 * Cypress E2E tests for Clothing Sales History
 * Tests clickable dashboard elements, sales history page, and CSV export
 */

describe('Clothing Sales History', () => {
  let testUser;
  let testBusiness;

  before(() => {
    // Create test data via Django management command or API
    cy.exec('python manage.py shell -c "' +
      'from django.contrib.auth import get_user_model; ' +
      'from tenants.models import Business, Membership; ' +
      'from inventory.business_kinds import BusinessKind; ' +
      'from inventory.models import MerchProduct; ' +
      'from inventory.models_verticals import ClothingSale, PaymentMethod; ' +
      'from decimal import Decimal; ' +
      'from django.utils import timezone; ' +
      'User = get_user_model(); ' +
      'user = User.objects.get_or_create(username=\\"clothingtest\\", defaults={\\"email\\": \\"clothing@test.com\\"})[0]; ' +
      'user.set_password(\\"test123\\"); ' +
      'user.save(); ' +
      'biz = Business.objects.get_or_create(name=\\"Test Clothing Store\\", defaults={\\"business_type\\": BusinessKind.CLOTHING, \\"owner\\": user})[0]; ' +
      'Membership.objects.get_or_create(user=user, business=biz, defaults={\\"role\\": \\"manager\\"}); ' +
      'product = MerchProduct.objects.get_or_create(business=biz, name=\\"Test Suit - L - Black\\", defaults={\\"kind\\": BusinessKind.CLOTHING, \\"category\\": \\"suit\\", \\"cost_price\\": Decimal(\\"200\\"), \\"selling_price\\": Decimal(\\"350\\"), \\"quantity_in_stock\\": 10})[0]; ' +
      'ClothingSale.objects.get_or_create(business=biz, product=product, defaults={\\"quantity\\": 1, \\"unit_price\\": Decimal(\\"350\\"), \\"total_price\\": Decimal(\\"350\\"), \\"unit_cost\\": Decimal(\\"200\\"), \\"total_cost\\": Decimal(\\"200\\"), \\"payment_method\\": PaymentMethod.CASH, \\"sold_by\\": user}); ' +
      '"'
    );

    testUser = { username: 'clothingtest', password: 'test123' };
  });

  beforeEach(() => {
    // Login before each test
    cy.visit('/accounts/login/');
    cy.get('input[name="username"]').type(testUser.username);
    cy.get('input[name="password"]').type(testUser.password);
    cy.get('button[type="submit"]').click();
    cy.url().should('not.include', '/login');
  });

  it('should load clothing dashboard', () => {
    cy.visit('/verticals/clothing/dashboard/');
    cy.contains('Clothing').should('be.visible');
    cy.contains('Sales').should('be.visible');
  });

  it('should have clickable sales card on dashboard', () => {
    cy.visit('/verticals/clothing/dashboard/');

    // Find and click the Sales card
    cy.contains('Sales').parents('a').first().should('have.attr', 'href').and('include', '/verticals/clothing/sales/');
    cy.contains('Sales').parents('a').first().click();

    // Should navigate to sales history page
    cy.url().should('include', '/verticals/clothing/sales/');
    cy.contains('Sales History').should('be.visible');
  });

  it('should load sales history page', () => {
    cy.visit('/verticals/clothing/sales/');

    cy.contains('Sales History').should('be.visible');
    cy.contains('Download CSV').should('be.visible');
    cy.get('table').should('be.visible');
  });

  it('should display sales in table', () => {
    cy.visit('/verticals/clothing/sales/');

    // Check table headers
    cy.get('table thead').within(() => {
      cy.contains('Timestamp').should('be.visible');
      cy.contains('Item').should('be.visible');
      cy.contains('Payment').should('be.visible');
      cy.contains('Cashier').should('be.visible');
    });

    // Check that at least one sale is displayed
    cy.get('table tbody tr').should('have.length.at.least', 1);
  });

  it('should filter sales by date range', () => {
    cy.visit('/verticals/clothing/sales/');

    const today = new Date().toISOString().split('T')[0];

    // Set date filters
    cy.get('input[name="start"]').type(today);
    cy.get('input[name="end"]').type(today);
    cy.contains('Apply Filters').click();

    // URL should include filter params
    cy.url().should('include', 'start=' + today);
    cy.url().should('include', 'end=' + today);
  });

  it('should filter sales by search query', () => {
    cy.visit('/verticals/clothing/sales/');

    // Enter search query
    cy.get('input[name="q"]').type('Suit');
    cy.contains('Apply Filters').click();

    // URL should include search param
    cy.url().should('include', 'q=Suit');
  });

  it('should download CSV export', () => {
    cy.visit('/verticals/clothing/sales/');

    // Click download button
    cy.contains('Download CSV').should('have.attr', 'href').and('include', '/verticals/clothing/sales/export.csv');

    // Verify the endpoint returns 200
    cy.request('/verticals/clothing/sales/export.csv').then((response) => {
      expect(response.status).to.eq(200);
      expect(response.headers['content-type']).to.include('text/csv');
      expect(response.headers['content-disposition']).to.include('attachment');
      expect(response.headers['content-disposition']).to.include('clothing_sales_');
    });
  });

  it('should fetch sales trend JSON', () => {
    cy.request('/verticals/clothing/api/sales-trend/').then((response) => {
      expect(response.status).to.eq(200);
      expect(response.headers['content-type']).to.include('application/json');

      // Check JSON structure
      expect(response.body).to.have.property('labels');
      expect(response.body).to.have.property('revenue');
      expect(response.body).to.have.property('count');
      expect(response.body).to.have.property('timestamp');

      // Arrays should have same length
      expect(response.body.labels.length).to.eq(response.body.revenue.length);
      expect(response.body.labels.length).to.eq(response.body.count.length);
    });
  });

  it('should have working Recent Sales section on dashboard', () => {
    cy.visit('/verticals/clothing/dashboard/');

    // Check Recent Sales section exists
    cy.contains('Recent Sales').should('be.visible');
    cy.contains('View All').should('be.visible');

    // Click View All button
    cy.contains('View All').click();

    // Should navigate to sales history
    cy.url().should('include', '/verticals/clothing/sales/');
  });

  it('should update sales trend dynamically', () => {
    cy.visit('/verticals/clothing/dashboard/');

    // Wait for dynamic update
    cy.wait(2000);

    // Check that sales trend container exists
    cy.get('#sales-trend-container').should('be.visible');
    cy.get('.trend-day-row').should('have.length.at.least', 1);
  });

  it('should clear filters correctly', () => {
    cy.visit('/verticals/clothing/sales/');

    const today = new Date().toISOString().split('T')[0];

    // Set filters
    cy.get('input[name="start"]').type(today);
    cy.get('input[name="q"]').type('test');
    cy.contains('Apply Filters').click();

    // URL should have params
    cy.url().should('include', 'start=');
    cy.url().should('include', 'q=');

    // Click Clear
    cy.contains('Clear').click();

    // URL should be clean
    cy.url().should('not.include', 'start=');
    cy.url().should('not.include', 'q=');
  });

  it('should show empty state when no sales match filters', () => {
    cy.visit('/verticals/clothing/sales/');

    // Search for something that doesn't exist
    cy.get('input[name="q"]').type('NONEXISTENT_PRODUCT_XYZ123');
    cy.contains('Apply Filters').click();

    // Should show empty state
    cy.contains('No Sales Found').should('be.visible');
  });
});

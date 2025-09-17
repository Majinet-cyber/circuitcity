from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ExpenseCategoryViewSet, ExpenseViewSet, BudgetViewSet, CashLedgerViewSet,
    PaymentIntentViewSet, ForecastViewSet, AlertViewSet, RecommendationViewSet,
    PersonalExpenseViewSet, airtel_webhook
)

router = DefaultRouter()
router.register(r'expense-categories', ExpenseCategoryViewSet, basename='expense-category')
router.register(r'expenses', ExpenseViewSet, basename='expense')
router.register(r'budgets', BudgetViewSet, basename='budget')
router.register(r'ledger', CashLedgerViewSet, basename='ledger')
router.register(r'payouts', PaymentIntentViewSet, basename='payouts')
router.register(r'cfo/forecast', ForecastViewSet, basename='forecast')
router.register(r'cfo/alerts', AlertViewSet, basename='alerts')
router.register(r'cfo/recommendations', RecommendationViewSet, basename='recs')
router.register(r'personal-expenses', PersonalExpenseViewSet, basename='personal-expenses')

urlpatterns = [
    path('', include(router.urls)),
    path('payouts/webhook/airtel/', airtel_webhook, name='airtel-webhook'),
]

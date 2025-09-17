from rest_framework import serializers
from .models import ExpenseCategory, Expense, Budget, CashLedger, PaymentIntent, ForecastSnapshot, Alert, Recommendation, PersonalExpense

class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = "__all__"

class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = "__all__"
        read_only_fields = ("created_at",)

class BudgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Budget
        fields = "__all__"

class CashLedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashLedger
        fields = "__all__"

class PaymentIntentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentIntent
        fields = ("payee_type","payee_id","purpose","amount","currency","scheduled_for","idempotency_key","meta")

class PaymentIntentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentIntent
        fields = "__all__"

class ForecastSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = ForecastSnapshot
        fields = "__all__"

class AlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alert
        fields = "__all__"

class RecommendationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recommendation
        fields = "__all__"

class PersonalExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonalExpense
        fields = "__all__"
        read_only_fields = ("created_at",)

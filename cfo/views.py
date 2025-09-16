from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from .models import ExpenseCategory, Expense, Budget, CashLedger, PaymentIntent, ForecastSnapshot, Alert, Recommendation, PersonalExpense
from .serializers import (
    ExpenseCategorySerializer, ExpenseSerializer, BudgetSerializer, CashLedgerSerializer,
    PaymentIntentCreateSerializer, PaymentIntentSerializer, ForecastSnapshotSerializer,
    AlertSerializer, RecommendationSerializer, PersonalExpenseSerializer
)
from .permissions import IsAdminOrReadOnly
from .services.forecast import compute_forecast
from .services.rules import run_rules
from .services.recommend import recommend_affordability
from .payments import create_or_get_intent, approve_intent, handle_airtel_webhook

class ExpenseCategoryViewSet(viewsets.ModelViewSet):
    queryset = ExpenseCategory.objects.all()
    serializer_class = ExpenseCategorySerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]

class ExpenseViewSet(viewsets.ModelViewSet):
    queryset = Expense.objects.all().order_by("-date")
    serializer_class = ExpenseSerializer
    permission_classes = [IsAuthenticated]

class BudgetViewSet(viewsets.ModelViewSet):
    queryset = Budget.objects.all()
    serializer_class = BudgetSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]

class CashLedgerViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CashLedger.objects.all().order_by("-date","-id")
    serializer_class = CashLedgerSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]

class PaymentIntentViewSet(viewsets.GenericViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    queryset = PaymentIntent.objects.all().order_by("-created_at")
    serializer_class = PaymentIntentSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]

    @action(detail=False, methods=["post"])
    def create_intent(self, request):
        s = PaymentIntentCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        obj = create_or_get_intent(user=request.user, **s.validated_data)
        return Response(PaymentIntentSerializer(obj).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        intent = self.get_object()
        obj = approve_intent(intent, approver=request.user)
        return Response(PaymentIntentSerializer(obj).data)

class ForecastViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def list(self, request):
        qs = ForecastSnapshot.objects.all().order_by("-created_at")[:5]
        return Response(ForecastSnapshotSerializer(qs, many=True).data)

    @action(detail=False, methods=["post"])
    def compute(self, request):
        opening = request.data.get("opening_balance","0")
        snap = compute_forecast(int(request.data.get("horizon",30)), opening_balance=Decimal(opening))
        return Response(ForecastSnapshotSerializer(snap).data, status=201)

class AlertViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Alert.objects.all().order_by("-created_at")
    serializer_class = AlertSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]

class RecommendationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Recommendation.objects.all().order_by("-created_at")
    serializer_class = RecommendationSerializer
    permission_classes = [IsAuthenticated]

class PersonalExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = PersonalExpenseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Agents/admins see only their own personal expenses
        return PersonalExpense.objects.filter(user=self.request.user).order_by("-date")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

@method_decorator(csrf_exempt, name='dispatch')
@api_view(["POST"])
@permission_classes([])
def airtel_webhook(request):
    sig = request.headers.get("X-Airtel-Signature","")
    ok = handle_airtel_webhook(request.body, sig)
    return Response({"ok": ok})

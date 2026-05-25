from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.shortcuts import redirect, render
from django.urls import reverse

from applications.models import FinancingApplication
from commissions.models import Commission
from rewards.models import SpinReward, SpinWallet
from rewards.services import NoSpinsAvailable, SpinDisabled, perform_spin

from .models import Wallet


COMPLETED_STATUSES = ["approved", "completed"]


@login_required
def earnings_home(request):
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    transactions = wallet.transactions.all()[:20]
    commissions = Commission.objects.filter(user=request.user)
    pending_commissions = commissions.filter(status=Commission.STATUS_PENDING)
    paid_commissions = commissions.filter(status=Commission.STATUS_PAID)
    spin_wallet, _ = SpinWallet.objects.get_or_create(user=request.user)
    latest_rewards = SpinReward.objects.filter(user=request.user)[:5]

    return render(request, "earnings/home.html", {
        "wallet": wallet,
        "transactions": transactions,
        "commissions": commissions[:20],
        "pending_commission_total": pending_commissions.aggregate(total=Sum("amount"))["total"] or Decimal("0.00"),
        "paid_commission_total": paid_commissions.aggregate(total=Sum("amount"))["total"] or Decimal("0.00"),
        "total_commission_earned": commissions.exclude(status=Commission.STATUS_CANCELLED).aggregate(total=Sum("amount"))[
            "total"
        ]
        or Decimal("0.00"),
        "spin_wallet": spin_wallet,
        "latest_rewards": latest_rewards,
    })


def leaderboard_rows():
    rows = list(
        FinancingApplication.objects.filter(status__in=COMPLETED_STATUSES)
        .values("created_by", "created_by__username", "created_by__first_name", "created_by__last_name")
        .annotate(sales_count=Count("id"))
        .order_by("-sales_count", "created_by__username")
    )
    earnings_by_user = {
        row["user"]: row["total"] or Decimal("0.00")
        for row in Commission.objects.filter(role=Commission.ROLE_MERCHANT)
        .exclude(status=Commission.STATUS_CANCELLED)
        .values("user")
        .annotate(total=Sum("amount"))
    }

    for index, row in enumerate(rows, start=1):
        full_name = f"{row['created_by__first_name']} {row['created_by__last_name']}".strip()
        row["rank"] = index
        row["merchant_name"] = full_name or row["created_by__username"]
        row["total_commission"] = earnings_by_user.get(row["created_by"], Decimal("0.00"))
    return rows


@login_required
def merchant_leaderboard(request):
    rows = leaderboard_rows()
    current_user_row = next((row for row in rows if row["created_by"] == request.user.id), None)
    return render(
        request,
        "earnings/leaderboard.html",
        {
            "leaders": rows[:10],
            "current_user_row": current_user_row,
            "period_label": "All-time",
        },
    )


@login_required
def spin_rewards(request):
    spin_wallet, _ = SpinWallet.objects.get_or_create(user=request.user)
    won_reward = None
    if request.method == "POST":
        try:
            won_reward = perform_spin(request.user)
            messages.success(request, f"You won MWK {won_reward.amount}.")
            return redirect(f"{reverse('spin_rewards')}?won={won_reward.id}")
        except NoSpinsAvailable:
            messages.error(request, "No spins available.")
        except SpinDisabled:
            messages.error(request, "Spin rewards are currently disabled.")

    won_id = request.GET.get("won")
    if won_id:
        won_reward = SpinReward.objects.filter(id=won_id, user=request.user).first()
    spin_wallet.refresh_from_db()

    return render(
        request,
        "earnings/spin.html",
        {
            "spin_wallet": spin_wallet,
            "latest_rewards": SpinReward.objects.filter(user=request.user)[:10],
            "won_reward": won_reward,
        },
    )

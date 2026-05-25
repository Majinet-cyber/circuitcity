from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Wallet


@login_required
def earnings_home(request):
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    transactions = wallet.transactions.all()[:20]

    return render(request, "earnings/home.html", {
        "wallet": wallet,
        "transactions": transactions,
    })
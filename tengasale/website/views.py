"""Website views — public-facing pages for /site/."""
from django.shortcuts import render


def landing(request):
    return render(request, "website/landing.html", {})


def about(request):
    return render(request, "website/landing.html", {"section": "about"})


def how_it_works(request):
    return render(request, "website/landing.html", {"section": "how_it_works"})


def merchants(request):
    return render(request, "website/landing.html", {"section": "merchants"})


def customers(request):
    return render(request, "website/landing.html", {"section": "customers"})


def faq(request):
    return render(request, "website/landing.html", {"section": "faq"})


def contact(request):
    return render(request, "website/landing.html", {"section": "contact"})


def terms(request):
    return render(request, "website/terms.html", {})


def privacy(request):
    return render(request, "website/privacy.html", {})


def payment_terms(request):
    return render(request, "website/payment_terms.html", {})


def merchant_terms(request):
    return render(request, "website/merchant_terms.html", {})

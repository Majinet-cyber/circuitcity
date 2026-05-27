"""Website views — stubs; fully implemented in Phase 3."""
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


def integrations(request):
    return render(request, "website/landing.html", {"section": "integrations"})


def faq(request):
    return render(request, "website/landing.html", {"section": "faq"})


def contact(request):
    return render(request, "website/landing.html", {"section": "contact"})

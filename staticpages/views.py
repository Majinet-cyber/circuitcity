from django.shortcuts import render


def home(request):
    """
    Public home page with hero section and marketing copy.
    """
    return render(request, 'staticpages/home.html', {
        'hide_nav': True,  # Don't show internal navigation
    })


def privacy(request):
    """
    Privacy Policy page.
    """
    return render(request, 'staticpages/privacy.html', {
        'hide_nav': True,
    })


def terms(request):
    """
    Terms of Service page.
    """
    return render(request, 'staticpages/terms.html', {
        'hide_nav': True,
    })


def simulator(request):
    """
    Business Simulator page with interactive sliders and charts.
    """
    return render(request, 'staticpages/simulator.html', {
        'hide_nav': True,
    })

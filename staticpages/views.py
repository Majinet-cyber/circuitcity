from django.shortcuts import render


def home(request):
    """
    Public home page with hero section and marketing copy.
    """
    return render(request, 'staticpages/home.html', {
        'hide_nav': True,  # Don't show internal navigation
    })


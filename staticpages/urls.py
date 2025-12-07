from django.urls import path
from . import views

app_name = 'staticpages'

urlpatterns = [
    path('', views.home, name='home'),
    path('privacy/', views.privacy, name='privacy'),
    path('terms/', views.terms, name='terms'),
    path('data-deletion/', views.data_deletion, name='data_deletion'),
    path('about/', views.about, name='about'),
    path('simulator/', views.simulator, name='simulator'),
    
    # Onboarding guides
    path('onboarding/manager/', views.onboarding_manager, name='onboarding_manager'),
    path('onboarding/hq/', views.onboarding_hq, name='onboarding_hq'),
]


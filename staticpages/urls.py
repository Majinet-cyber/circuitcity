from django.urls import path
from . import views

app_name = 'staticpages'

urlpatterns = [
    path('', views.home, name='home'),
    path('privacy/', views.privacy, name='privacy'),
    path('terms/', views.terms, name='terms'),
    path('about/', views.about, name='about'),
    path('simulator/', views.simulator, name='simulator'),
]


from django.urls import path
from . import views

app_name = 'staticpages'

urlpatterns = [
    path('', views.home, name='home'),
]


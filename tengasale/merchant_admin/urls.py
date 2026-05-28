from django.urls import path
from . import views

urlpatterns = [
    path("",                          views.ma_dashboard,    name="ma_dashboard"),
    path("leads/",                    views.ma_leads,        name="ma_leads"),
    path("leads/<int:lead_id>/",      views.ma_lead_detail,  name="ma_lead_detail"),
    path("leads/<int:lead_id>/kyc/",  views.ma_lead_kyc,     name="ma_lead_kyc"),
    path("leads/<int:lead_id>/checklist/", views.ma_checklist, name="ma_checklist"),
    path("leads/<int:lead_id>/status/",    views.ma_lead_status, name="ma_lead_status"),
    path("leads/<int:lead_id>/recommend/", views.ma_recommend,   name="ma_recommend"),
]

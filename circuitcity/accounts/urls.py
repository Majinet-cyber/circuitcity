from django.urls import path
from . import views

urlpatterns = [
    path("me/avatar/", views.upload_my_avatar, name="upload_my_avatar"),
    path("agents/<int:agent_id>/avatar/", views.upload_agent_avatar, name="upload_agent_avatar"),
]

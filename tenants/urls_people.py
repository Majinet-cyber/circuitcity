from django.urls import path
from . import views_people as v


app_name = "tenants"


urlpatterns = [
# People
path("org/people/", v.people_index, name="people_index"),
path("org/people/invite/", v.invite_agent, name="invite_agent"),
path("org/people/invite/<str:token>/cancel/", v.cancel_invite, name="cancel_invite"),
path("join/<str:token>/", v.accept_invite, name="accept_invite"),
path("org/people/reset/", v.trigger_password_reset, name="trigger_password_reset"),


# Locations
path("org/locations/", v.locations_index, name="locations_index"),
path("org/locations/new/", v.location_create, name="location_create"),
path("org/locations/<int:pk>/edit/", v.location_edit, name="location_edit"),
path("org/locations/<int:pk>/delete/", v.location_delete, name="location_delete"),
path("org/locations/<int:pk>/default/", v.location_set_default, name="location_set_default"),
]
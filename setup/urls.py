"""
URL configuration for setup project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.urls import path

from geo.autocomplete import GeoAutocomplete
from geo.api import geocode
from geo.models import City, Country, County, State, StreetName
from geo.openapi import openapi_schema, swagger_ui
from geo.views import geocode_page, tokenizer_status

urlpatterns = [
    path('', geocode_page, name='geocode-page'),
    path('admin/', admin.site.urls),
    path('api/geocode/', geocode, name='geocode'),
    path('api/tokenizer-status/', tokenizer_status, name='tokenizer-status'),
    path('api/openapi.json', openapi_schema, name='openapi-schema'),
    path('swagger/', swagger_ui, name='swagger-ui'),
    path('autocomplete/state/', staff_member_required(GeoAutocomplete.as_view(model=State)), name='state_autocomplete'),
    path('autocomplete/county/', staff_member_required(GeoAutocomplete.as_view(model=County)), name='county_autocomplete'),
    path('autocomplete/country/', staff_member_required(GeoAutocomplete.as_view(model=Country)), name='country_autocomplete'),
    path('autocomplete/city/', staff_member_required(GeoAutocomplete.as_view(model=City)), name='city_autocomplete'),
    path('autocomplete/street/', staff_member_required(GeoAutocomplete.as_view(model=StreetName)), name='street_name_autocomplete'),
]

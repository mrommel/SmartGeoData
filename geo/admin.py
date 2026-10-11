from django.contrib import admin

from geo.admin_forms import CityAdmin, AlternativeCityNameAdmin, CountyAdmin, StateAdmin, CountryAdmin, \
	AlternativeCountryNameAdmin, StreetNameAdmin, AlternativeStreetNameAdmin
from geo.models import City, AlternativeCityName, County, State, Country, AlternativeCountryName, StreetName, \
	AlternativeStreetName

# geo data
admin.site.register(City, CityAdmin)
admin.site.register(AlternativeCityName, AlternativeCityNameAdmin)
admin.site.register(County, CountyAdmin)
admin.site.register(State, StateAdmin)
admin.site.register(Country, CountryAdmin)
admin.site.register(AlternativeCountryName, AlternativeCountryNameAdmin)
admin.site.register(StreetName, StreetNameAdmin)
admin.site.register(AlternativeStreetName, AlternativeStreetNameAdmin)

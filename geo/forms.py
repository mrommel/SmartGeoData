from django import forms


class CreateCityForm(forms.Form):
    city_name = forms.CharField(max_length=100)
    zip_code = forms.CharField(max_length=200, required=False)
    county_name = forms.CharField(max_length=300)  #
    state_name = forms.CharField(max_length=100)
    country_name = forms.CharField(max_length=100, required=False)
    geo_value = forms.CharField(max_length=100, required=False)


class CreateStreetForm(forms.Form):
    city_name = forms.CharField(max_length=100)
    street_name = forms.CharField(max_length=100)
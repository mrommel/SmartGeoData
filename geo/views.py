import re

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from geo.llm import AddressExtractionError, extract_address
from geo.models import City, Country, County, State, StreetCityMembership, StreetName
from geo.tokenizer import StreetTokenizer, CityTokenizer
from geo.utils import _clean_string


streetTokenizer = StreetTokenizer()
cityTokenizer = CityTokenizer()



def _has_zip(city, postal_code):
	postal_code = postal_code.replace(' ', '').casefold()
	for part in (city.zip_code or '').replace(' ', '').split(','):
		part = part.casefold()
		if part == postal_code:
			return True
		if city.country and city.country.zips_use_range and '-' in part:
			start, separator, end = part.partition('-')
			if separator and start.isdigit() and end.isdigit() and len(start) == len(end) == len(postal_code):
				if start <= postal_code <= end:
					return True
	return False


@require_GET
def geocode(request):
	"""Resolve a city or street address to a city's coordinates."""
	text = request.GET.get('text', '').strip()
	if not text or len(text) > 255:
		return JsonResponse({'error': 'text must contain between 1 and 255 characters'}, status=400)

	try:
		parts = extract_address(text)
	except AddressExtractionError:
		return JsonResponse({'error': 'Address extraction is unavailable'}, status=503)

	cityTokenizer.populate()
	streetTokenizer.populate()
	city_name = _clean_string(parts['city'])
	street_name = _clean_string(parts['street'])
	city_ids = {entry[0] for entry in cityTokenizer.city_dict.get(city_name, [])} if city_name else set()
	street_id = None
	if street_name:
		# embed() resolves canonical and alternative street names to the same ID.
		embedded = streetTokenizer.embed(street_name)
		match = re.fullmatch(r'STREET\((\d+)\)', embedded)
		if match:
			street_id = int(match.group(1))
	if (city_name and not city_ids) or (street_name and street_id is None) or not (city_ids or street_id):
		return JsonResponse({'results': []})

	if street_id is not None:
		memberships = StreetCityMembership.objects.filter(street_name_id=street_id)
		if city_name:
			memberships = memberships.filter(city_id__in=city_ids)
		cities = City.objects.filter(pk__in=memberships.values('city_id'))
	else:
		cities = City.objects.filter(pk__in=city_ids)
	cities = cities.filter(lat__isnull=False, lng__isnull=False).select_related(
		'country', 'state', 'county')

	country_name = _clean_string(parts['country'])
	state_name = _clean_string(parts['state'])
	county_name = _clean_string(parts['county'])
	country_id = cityTokenizer.country_dict.get(country_name) if country_name else None
	if country_name and country_id is None:
		country_id = Country.objects.filter(iso2__iexact=country_name).values_list('pk', flat=True).first()
		if country_id is None:
			country_id = Country.objects.filter(iso3__iexact=country_name).values_list('pk', flat=True).first()
	if country_name:
		cities = cities.filter(country_id=country_id) if country_id else cities.none()
	if state_name:
		states = State.objects.all()
		state_ids = [state.pk for state in states if state_name in {
			_clean_string(name) for name in [state.name, state.iso2 or '',
			                                 *(state.alternative_names or '').split(',')]}]
		cities = cities.filter(state_id__in=state_ids)
	if county_name:
		county_ids = [county.pk for county in County.objects.all() if county_name in {
			_clean_string(name) for name in [county.name, *(county.alternative_names or '').split(',')]}]
		cities = cities.filter(county_id__in=county_ids)
	matched = [city for city in cities if not parts['postal_code'] or _has_zip(city, parts['postal_code'])]
	matched.sort(key=lambda city: (city.name.casefold(), city.pk))
	street = None
	if street_id is not None and matched:
		# Use the canonical street name in the response, never the LLM's spelling.
		street = StreetName.objects.get(pk=street_id).name
	return JsonResponse({'results': [
		{
			**({'street': street} if street else {}),
			'city': city.name,
			'county': city.county.name if city.county else None,
			'state': city.state.name if city.state else None,
			'country': city.country.name if city.country else None,
			'zip_code': city.zip_code,
			'lat': city.lat,
			'lng': city.lng,
		} for city in matched[:10]
	]})

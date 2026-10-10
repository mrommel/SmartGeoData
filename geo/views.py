import re

from django.db.models import Exists, OuterRef, Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from geo.models import (AlternativeCityName, AlternativeStreetName, City, Country,
						County, State, StreetCityMembership, StreetName)
from geo.utils import _clean_string


def _contains(text, name):
	name = _clean_string(name)
	return bool(name) and f' {name} ' in f' {text} '


def _code_qualifier(text, code):
	return bool(code) and _clean_string(code) in {_clean_string(part) for part in text.split(',')}


def _has_zip(city, postal_code):
	for part in (city.zip_code or '').replace(' ', '').split(','):
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

	postal_match = re.search(r'(?<!\w)\d{4,6}(?!\w)', text)
	postal_code = postal_match.group() if postal_match else None
	search_text = _clean_string(text.replace(postal_code, ' ', 1) if postal_code else text)
	words = search_text.split()
	# Match whole city names within free-form text, including multi-word cities.
	terms = {' '.join(words[i:j]) for i in range(len(words))
	         for j in range(i + 1, min(i + 6, len(words) + 1))}
	if not terms:
		return JsonResponse({'results': []})

	name_filter = Q()
	alias_filter = Q()
	for term in terms:
		name_filter |= Q(name__iexact=term)
		alias_filter |= Q(name__iexact=term)
	alias_match = Exists(AlternativeCityName.objects.filter(city_id=OuterRef('pk')).filter(alias_filter))
	cities = City.objects.filter(name_filter | Q(alias_match)).select_related(
		'country', 'state', 'county').prefetch_related('alternativecityname_set')
	city_matches = []
	for city in cities:
		names = [city.name] + [alias.name for alias in city.alternativecityname_set.all()]
		city_name = max((name for name in names if _contains(search_text, name)),
		                key=lambda name: len(_clean_string(name)), default=None)
		if city_name:
			city_matches.append((city, city_name, None))

	street_filter = Q()
	for term in terms:
		street_filter |= Q(name__iexact=term)
	street_alias_match = Exists(AlternativeStreetName.objects.filter(
		street_id=OuterRef('pk')).filter(street_filter))
	streets = StreetName.objects.filter(street_filter | Q(street_alias_match)).prefetch_related(
		'alternativestreetname_set')
	street_names = {}
	for street in streets:
		names = [street.name] + [alias.name for alias in street.alternativestreetname_set.all()]
		match = max((name for name in names if _contains(search_text, name)),
		            key=lambda name: len(_clean_string(name)), default=None)
		if match:
			street_names[street.pk] = (street.name, match)

	# An exact city-only query retains the original city response even if a street
	# elsewhere happens to share its name.
	use_streets = bool(street_names) and not any(
		_clean_string(city_name) == search_text for _, city_name, _ in city_matches)
	if use_streets:
		memberships = StreetCityMembership.objects.filter(
			street_name_id__in=street_names, city__lat__isnull=False, city__lng__isnull=False
		).select_related('city__country', 'city__state', 'city__county').prefetch_related(
			'city__alternativecityname_set')
		candidates = []
		for membership in memberships:
			city = membership.city
			street, street_match = street_names[membership.street_name_id]
			rest = re.sub(r'(?<!\w)' + re.escape(_clean_string(street_match)) + r'(?!\w)',
			              ' ', search_text, count=1).strip()
			city_names = [city.name] + [alias.name for alias in city.alternativecityname_set.all()]
			city_match = max((name for name in city_names if _contains(rest, name)),
			                 key=lambda name: len(_clean_string(name)), default=None)
			# If a city was explicitly named, the street must belong to that city.
			if city_matches and not city_match and any(
				_contains(rest, name) for _, name, _ in city_matches):
				continue
			candidates.append((city, city_match, (street, street_match)))
	else:
		candidates = city_matches

	# Qualifiers in the remaining text disambiguate cities sharing the same name.
	countries = states = counties = None
	matched = []
	for city, city_name, street_info in candidates:
		if city.lat is None or city.lng is None:
			continue
		if postal_code and not _has_zip(city, postal_code):
			continue
		remainder = search_text
		original_remainder = text
		for name in ([street_info[1]] if street_info else []) + ([city_name] if city_name else []):
			remainder = re.sub(r'(?<!\w)' + re.escape(_clean_string(name)) + r'(?!\w)',
			                   ' ', remainder, count=1).strip()
			original_remainder = re.sub(re.escape(name), ' ', original_remainder,
			                            count=1, flags=re.IGNORECASE)
		if not remainder:
			matched.append((city, city_name, street_info))
			continue
		if countries is None:
			countries = list(Country.objects.all().prefetch_related('alternativecountryname_set'))
			states = list(State.objects.all())
			counties = list(County.objects.all())
		matched_countries = {
			country.pk for country in countries
			if any(_contains(remainder, name) for name in
			       [country.name, *[alias.name for alias in country.alternativecountryname_set.all()]])
			or _code_qualifier(original_remainder, country.iso2)
			or _code_qualifier(original_remainder, country.iso3)
		}
		if matched_countries and city.country_id not in matched_countries:
			continue
		matched_states = {
			state.pk for state in states
			if any(_contains(remainder, name) for name in
			       [state.name, *(state.alternative_names or '').split(',')])
			or _code_qualifier(original_remainder, state.iso2)
		}
		matched_counties = {
			county.pk for county in counties
			if any(_contains(remainder, name) for name in
			       [county.name, *(county.alternative_names or '').split(',')])
		}
		if matched_states and city.state_id not in matched_states:
			continue
		if matched_counties and city.county_id not in matched_counties:
			continue
		matched.append((city, city_name, street_info))

	if not matched:
		return JsonResponse({'results': []})
	# Prefer the longest street and city match over shorter names within the text.
	best_length = max((len(_clean_string(street[1])) if street else 0,
	                   len(_clean_string(city_name)) if city_name else 0)
	                  for _, city_name, street in matched)
	matched = [item for item in matched if (
		len(_clean_string(item[2][1])) if item[2] else 0,
		len(_clean_string(item[1])) if item[1] else 0) == best_length]
	matched.sort(key=lambda item: (item[0].name.casefold(), item[0].pk))
	return JsonResponse({'results': [
		{
			**({'street': street[0]} if street else {}),
			'city': city.name,
			'county': city.county.name if city.county else None,
			'state': city.state.name if city.state else None,
			'country': city.country.name if city.country else None,
			'zip_code': city.zip_code,
			'lat': city.lat,
			'lng': city.lng,
		} for city, _, street in matched[:10]
	]})

import logging
import re
import string
from typing import Optional, Tuple

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from geo import green, red
from geo.forms import CreateCityForm, CreateStreetForm
from geo.llm import AddressExtractionError, extract_address
from geo.models import City, Country, County, State, StreetCityMembership, StreetName, AlternativeStreetName
from geo.tasks import get_tokenizers
from geo.tokenizer import AddressPatternTokenizer, AddressObject
from geo.utils import _clean_string, has_numbers

logger = logging.getLogger(__name__)


class NoValidCityFoundException(Exception):
	def __init__(self, message):
		super().__init__(message)


class StreetAlreadyExistsException(Exception):
	def __init__(self, message):
		super().__init__(message)


class AlternativeStreetAlreadyExistsException(Exception):
	def __init__(self, message):
		super().__init__(message)


class StreetNameIsEmptyException(Exception):
	def __init__(self, message):
		super().__init__(message)


def _has_zip(city, postal_code):
	postal_code = postal_code.replace(' ', '').casefold()
	for part in (city.zip_code or '').replace(' ', '').split(','):
		part = part.casefold()
		if part == postal_code:
			return True
		if (city.country and (city.country.iso2 or '').casefold() == 'nl'
		        and re.fullmatch(r'[1-9]\d{3}(?!sa|sd|ss)[a-z]{2}', postal_code)
	        and part == postal_code[:4]):
			return True
		if city.country and city.country.zips_use_range and '-' in part:
			start, separator, end = part.partition('-')
			if separator and start.isdigit() and end.isdigit() and len(start) == len(end) == len(postal_code):
				if start <= postal_code <= end:
					return True
	return False


def find_alternative(obj, name: str):
	if obj != County and obj != State and obj != Country and obj != City:
		raise Exception(f'Can only find alternative name for [County, State, Country] but is {obj}')

	if obj.objects.filter(name=name).first() is None:
		for county in obj.objects.all():
			if obj == County or obj == State:
				alternative_names = county.alternative_names
			elif obj == Country:
				alternative_names = ','.join(county.alternative_names())
			elif obj == City:
				alternative_names = ','.join(county.alternative_city_names())
			else:
				raise Exception(f'Cannot find alternative names for {obj}')

			if alternative_names is None or alternative_names == '':
				continue

			for alternative_name in alternative_names.lower().split(','):
				if name.lower() == alternative_name.strip():
					return county.name

	# found no match
	return name


def prepare_street_name(street_name: str) -> str:
	street_name_tokens = street_name.split(' ')
	filtered_street_name_tokens = []
	number_pattern = r'\d{1,5}(?:st|nd|rd|th)'

	for idx, street_name_token in enumerate(street_name_tokens):
		is_last = idx == len(street_name_tokens) - 1

		if has_numbers(street_name_token) and not re.match(number_pattern, street_name_token, flags=re.IGNORECASE):
			continue

		if street_name_token.lower() == 'bis':
			continue

		if street_name_token == '-':
			continue

		if street_name_token.lower() == 'unit':
			continue

		# print(street_name_token)

		if street_name_token.lower() == 'bd.' or street_name_token.lower() == 'bd':
			street_name_token = 'Boulevard'

		if street_name_token.lower() == 'imp.':
			street_name_token = 'Impasse'

		if street_name_token.lower() == 'chem.':
			street_name_token = 'Chemin'

		if street_name_token.lower() == 'av.':
			street_name_token = 'Avenue'

		if street_name_token.lower() == 'pl.':
			street_name_token = 'Place'

		if street_name_token.lower() == 'all.':
			street_name_token = 'Allée'

		if street_name_token.lower() == 'rte':
			street_name_token = 'Route'

		if street_name_token.lower() == 'Rdpt':
			street_name_token = 'Rond-Point'

		if street_name_token.lower() == 'cr':
			street_name_token = 'Cours'

		if street_name_token.lower() == 'str.':
			street_name_token = 'Straße'

		if street_name_token.lower() == 'chau.':
			street_name_token = 'Chaussée'

		if street_name_token.lower() == 'C.so':
			street_name_token = 'Corso'

		if is_last and street_name_token.lower() == 'rd':
			street_name_token = 'Road'

		if is_last and street_name_token.lower() == 'st':
			street_name_token = 'Street'

		if is_last and street_name_token.lower() == 'hwy':
			street_name_token = 'Highway'

		if is_last and street_name_token.lower() == 'ave':
			street_name_token = 'Avenue'

		filtered_street_name_tokens.append(street_name_token)

	street_name_without_numbers = ' '.join(filtered_street_name_tokens)
	street_name_without_numbers = street_name_without_numbers.strip()
	street_name_without_numbers = street_name_without_numbers.strip(',')
	return street_name_without_numbers.strip()


def find_alternative_street_names(street_name: str) -> list[str]:
	alternative_street_names: set[str] = set[str]()

	if not street_name.isascii():
		mapped_street_name = ''
		mapped = {
			'ä': 'a', 'â': 'a', 'à': 'a', 'Ä': 'A', 'Â': 'A', 'À': 'A', 'á': 'a', 'Á': 'A', 'ª': 'a', 'Å': 'A',
			'å': 'a', 'ă': 'a', 'Ă': 'A',
			'ö': 'o', 'Ö': 'O', 'ò': 'o', 'ô': 'o', 'ó': 'o', 'Ó': 'O', 'ø': 'o', 'Ø': 'O', 'õ': 'o', 'Õ': 'O',
			'Ò': 'O',
			'ü': 'u', 'ù': 'u', 'Ù': 'U', 'Ü': 'U', 'û': 'u', 'ú': 'u', 'Ú': 'U',
			'é': 'e', 'è': 'e', 'É': 'E', 'È': 'E', 'ë': 'e', 'ê': 'e', 'Ê': 'E', 'ě': 'e', 'Ě': 'E',
			'ß': 'ss',
			'ç': 'c', 'Ç': 'C', 'č': 'c', 'Č': 'C', 'ć': 'c', 'Ć': 'C',
			'Î': 'I', 'î': 'i', 'ï': 'i', 'Ï': 'I', 'í': 'i', 'Í': 'I', 'ì': 'i', 'Ì': 'I',
			'Œ': 'OE', 'œ': 'oe',
			'Æ': 'AE', 'æ': 'ae',
			'ñ': 'n', 'Ñ': 'N', 'ń': 'n', 'Ń': 'N',
			'ý': 'y', 'Ý': 'Y',
			'Š': 'S', 'š': 's', 'Ś': 'S', 'ś': 's',
			'ț': 't', 'Ț': 'T', 'ţ': 't', 'Ţ': 'T',
			'Ž': 'Z', 'ž': 'z',
			'ł': 'l', 'Ł': 'L',
			'þ': 'th', 'Þ': 'Th',
			'ð': 'd', 'Ð': 'D',
			'’': '\'', '´': '\'',
			'(': ' ', ')': ' ', '\u200e': ' ', '\u200f': ' '
		}
		for char in street_name:
			if char in [' ', '-', '.', ',', '\'', '·', '/', 'º', '&', '°']:
				mapped_street_name += char
				continue

			if char in string.ascii_letters:
				mapped_street_name += char
			else:
				mapped_street_name += mapped[char]

		alternative_street_names.add(mapped_street_name)

	if street_name.lower().endswith('strasse'):
		mapped_street_name = street_name[:len(street_name) - 4]
		alternative_street_names.add(mapped_street_name)

	if street_name.lower().endswith('straße'):
		mapped_street_name = street_name[:len(street_name) - 3]
		alternative_street_names.add(mapped_street_name)

	if 'Corso ' in street_name:
		mapped_street_name = street_name.replace('Corso ', 'C.so ')
		alternative_street_names.add(mapped_street_name)

	if street_name.lower().endswith(' road'):
		mapped_street_name = street_name.lower().replace(' road', ' rd')
		alternative_street_names.add(mapped_street_name)

	if street_name.lower().endswith(' highway'):
		mapped_street_name = street_name.lower().replace(' highway', ' hwy')
		alternative_street_names.add(mapped_street_name)

	if street_name.lower().endswith(' street'):
		mapped_street_name = street_name.lower().replace(' street', ' st')
		alternative_street_names.add(mapped_street_name)

	if street_name.lower().endswith(' avenue'):
		mapped_street_name = street_name.lower().replace(' avenue', ' ave')
		alternative_street_names.add(mapped_street_name)

	return list(alternative_street_names)


def add_street(city_name: str, street_name: str) -> Tuple[str, str]:
	tokenizers = get_tokenizers()
	if tokenizers is None:
		logger.warning('Invalid create_city request: "%r" - tokenizers not available', city_name)
		raise Exception('Invalid create_city request: "%r" - tokenizers not available', city_name)

	cityTokenizer, streetTokenizer = tokenizers

	cityTokenizer.populate()
	streetTokenizer.populate()

	# tokenize cities
	cleaned_city_name = _clean_string(city_name)
	cleaned_street_name = _clean_string(street_name)
	city_words = cityTokenizer.embed(f'{cleaned_street_name} {cleaned_city_name}')
	city_words = streetTokenizer.embed(city_words)

	addressPatternTokenizer = AddressPatternTokenizer(
		streetTokenizer=streetTokenizer,
		cityTokenizer=cityTokenizer
	)

	print(f'DEBUG: {city_words}')
	address_match: Optional[AddressObject] = addressPatternTokenizer.match(city_words)

	# print(f'DEBUG: {address_match}')
	# debug
	# return JsonResponse({'state': 'error', 'message': 'noop'}, status=400)

	if address_match is None:
		error_text = f"No valid City found in: '{city_words}'"
		raise NoValidCityFoundException(error_text)

	matched_city: Optional[City] = City.objects.get(id=address_match.city_id)
	matched_city_name: str = matched_city.name

	street_name_without_numbers: str = prepare_street_name(street_name)
	street_name_obj = StreetName.objects.filter(name=street_name_without_numbers).first()

	if address_match.street is not None:
		# link city to existing street if not already linked
		if not StreetCityMembership.objects.filter(city=matched_city, street_name=street_name_obj).exists():
			membership = StreetCityMembership(city=matched_city, street_name=street_name_obj)
			membership.save()
			print(f'Added membership between: {street_name_without_numbers} and {matched_city_name}')

		error_text = f"Street already exists: '{address_match.street}' ({address_match.street_id})"
		raise StreetAlreadyExistsException(error_text)

	if street_name_obj is not None:
		if not StreetCityMembership.objects.filter(city=matched_city, street_name=street_name_obj).exists():
			membership = StreetCityMembership(city=matched_city, street_name=street_name_obj)
			membership.save()
			print(f'Added membership between: {street_name_without_numbers} and {matched_city_name}')

		error_text = f'Street already exists: "{street_name_without_numbers}'
		raise StreetAlreadyExistsException(error_text)

	alt_street_name_obj = AlternativeStreetName.objects.filter(name=street_name_without_numbers).first()
	if alt_street_name_obj is not None:
		error_text = f'Alt Street already exists: "{street_name_without_numbers}'
		raise AlternativeStreetAlreadyExistsException(error_text)

	if street_name_without_numbers == '':
		error_text = f'Street name is empty: "{street_name_without_numbers}"'
		raise StreetNameIsEmptyException(error_text)

	new_street = StreetName(name=street_name_without_numbers)
	new_street.save()

	alternative_street_names: list[str] = find_alternative_street_names(street_name_without_numbers)

	for alternative_street_name in alternative_street_names:
		alt_street_name = AlternativeStreetName(name=alternative_street_name, street=new_street)
		alt_street_name.save()
		print(f'Created Alternative StreetName: {alternative_street_name}')

	membership = StreetCityMembership(city=matched_city, street_name=new_street)
	membership.save()

	# when a new street is created, we need to reset the tokenizer
	streetTokenizer.reset()

	return matched_city_name, street_name_without_numbers


@csrf_exempt
def create_street(request):
	# print(f'create_city: {request.method}')
	if request.method == "POST":
		# print(f'post {request.POST}')

		# create a form instance and populate it with data from the request:
		form = CreateStreetForm(request.POST)
		# check whether it's valid:
		if form.is_valid():
			print(form.cleaned_data)
			city_name = form.cleaned_data['city_name']
			street_name = form.cleaned_data['street_name']

			try:
				matched_city_name, street_name = add_street(city_name, street_name)
			except NoValidCityFoundException as e:
				print(red(str(e)))
				return JsonResponse({'state': 'error', 'message': str(e)}, status=400)
			except StreetAlreadyExistsException as e:
				print(red(str(e)))
				return JsonResponse({'state': 'error', 'message': str(e)}, status=409)
			except AlternativeStreetAlreadyExistsException as e:
				print(red(str(e)))
				return JsonResponse({'state': 'error', 'message': str(e)}, status=409)
			except StreetNameIsEmptyException as e:
				print(red(str(e)))
				return JsonResponse({'state': 'error', 'message': str(e)}, status=400)
			except Exception as e:
				print(e)
				print(red(f'Error adding street: {e}'))
				return JsonResponse({'state': 'error', 'message': str(e)}, status=400)

			print(green(f'Street with name "{street_name}" for "{matched_city_name}" created'))
			return JsonResponse({'state': 'success'}, status=200)
		else:
			print(red(f'CreateStreetForm not valid: {request.POST}'))
			return JsonResponse({'state': 'error', 'message': 'form not valid'}, status=400)
	else:
		return JsonResponse({'state': 'error', 'message': f'Method: {request.method} not allowed'}, status=400)


@csrf_exempt
def create_city(request):
	# print(f'create_city: {request.method}')
	if request.method == "POST":
		# print(f'post {request.POST}')

		# create a form instance and populate it with data from the request:
		form = CreateCityForm(request.POST)

		# check whether it's valid:
		if form.is_valid():
			print(form.cleaned_data)
			city_name = form.cleaned_data['city_name']

			# check italian city name
			take_first_half = True
			half_len = int(len(city_name) / 2)
			for idx in range(0, half_len):
				take_first_half &= city_name[idx] == city_name[half_len + idx]

			if take_first_half:
				city_name = city_name[:half_len]
				print(f'Take only first half: {city_name}')

			existing_city = City.objects.filter(name=city_name).first()
			if existing_city is not None:
				print(red(f'City with name "{city_name}" already exists'))
				return JsonResponse({'state': 'error', 'message': f'City with name "{city_name}" already exists'}, status=409)

			zip_code = form.cleaned_data['zip_code']
			county_name = form.cleaned_data['county_name']
			state_name = form.cleaned_data['state_name']
			country_name = form.cleaned_data['country_name']
			geo_value = form.cleaned_data['geo_value']

			if '}' in county_name:
				county_name = county_name.split('}')[-1]

			if ',' in county_name:
				county_name = county_name.split(',')[0]

			# some state fixes
			if state_name == 'England' or state_name == 'Scotland' or state_name == 'Wales':
				country_name = 'United Kingdom'

			if state_name == 'England':
				county_name = find_alternative(County, county_name)
				county = County.objects.get(name=county_name)
				state_name = county.state.name

			# try to get the state, if not try alternate names
			state_name = find_alternative(State, state_name)

			# some country fixes
			if country_name == 'Frankreich':
				country_name = 'France'

			if country_name == 'Schweiz Schweiz':
				country_name = 'Suisse'

			if country_name == 'Vereinigte Staaten':
				country_name = 'United States'

			if country_name == 'Kanada\xa0Kanada':
				country_name = 'Canada'

			if county_name == 'Italien':
				county_name = 'Italy'

			if county_name == 'Europäische Gebietskörperschaft Elsass':
				county_name = 'Bas-Rhin'

			if country_name != '':
				country_name = find_alternative(Country, country_name)

			if country_name == '':
				state = State.objects.get(name=state_name)
				country_name = state.country.name

			# some county fixes
			if '(Präfektur)' in county_name:
				county_name = county_name.replace('(Präfektur)', '').strip()

			if 'Département' in county_name:
				county_name = county_name.replace('Département', '').strip()

			county_name = county_name.replace('  ', ' ')

			# try to get the county, if not try alternate names
			department_matches = re.findall(r'\([A-Z0-9]+\)', county_name)
			# print(department_matches)
			if len(department_matches) > 0:
				for department_match in department_matches:
					county_name = county_name.replace(department_match, '').strip()
					print(f'Cleaned county name: {county_name}')

			if ',' in county_name:
				county_name = county_name.split(',')[0]

			county_name = find_alternative(County, county_name)

			# special case - same county_name
			if county_name == 'Baden':
				if country_name == 'Austria':
					county_name = 'Baden (Niederösterreich)'
				else:
					raise Exception(f'Unknown county name: {county_name} / {country_name}')

			# debug
			print(f'country_name={country_name}, state_name={state_name}, county_name={county_name}')
			country = Country.objects.get(name=country_name)
			state = State.objects.get(name=state_name)

			if county_name != 'Unabhängige Stadt':
				county = County.objects.get(name=county_name)
			else:
				county = None

			if zip_code is not None:
				zip_code = zip_code.split('[')[0]

			city = City(name=city_name, zip_code=zip_code, county=county, state=state, country=country)

			# handle "50.936071°N 1.195118°W"
			from lat_lon_parser import parse
			if geo_value is not None and geo_value != '':
				geo_value = geo_value.strip()

				if geo_value.startswith('Koordinaten:'):
					geo_value = geo_value.replace('Koordinaten:', '')
				else:
					geo_value = geo_value.split('Koordinaten:')[0].strip()

				geo_value = geo_value.split('O')[0].strip() + 'O'
				geo_value = geo_value.split('W')[0].strip() + 'W'
				geo_value_parts = geo_value.split(' ')

				# latitude
				lat_value = geo_value_parts[0]
				lat_value = lat_value.replace(r'\xa0', '')
				# clean-up
				# lat_value = lat_value.replace('°W', '')
				# lat_value = lat_value.replace('°N', '')
				# lat_value = float(lat_part)
				city.lat = parse(lat_value)

				# longitude
				lng_value = geo_value_parts[1]
				lng_value = lng_value.replace(r'\xa0', '')
				# lng_value = lng_value.replace('°N', '')
				# lng_value = lng_value.replace('°W', '')
				# lng_value = float(lng_value)
				city.lng = parse(lng_value)

			city.save()

			tokenizers = get_tokenizers()
			if tokenizers is None:
				logger.warning('Invalid create_city request: "%r" - tokenizers not available', city_name)
				return JsonResponse({'error': 'Tokenizer population is not complete'}, status=503)

			cityTokenizer, streetTokenizer = tokenizers

			cityTokenizer.reset()

			print(green(f'City with name "{city_name}" created'))

			return JsonResponse({'state': 'success'}, status=200)
		else:
			print(red(f'CityFrom not valid: {request.POST}'))
			return JsonResponse({'state': 'error', 'message': 'form not valid'}, status=400)
	else:
		return JsonResponse({'state': 'error', 'message': f'Method: {request.method} not allowed'}, status=400)


@require_GET
def geocode(request):
	"""Resolve a city or street address to a city's coordinates."""
	text = request.GET.get('text', '').strip()
	if not text or len(text) > 255:
		logger.warning('Invalid geocode request: "%r" - text must contain between 1 and 255 characters', text)
		return JsonResponse({'error': 'text must contain between 1 and 255 characters'}, status=400)

	tokenizers = get_tokenizers()
	if tokenizers is None:
		logger.warning('Invalid geocode request: "%r" - tokenizers not available', text)
		return JsonResponse({'error': 'Tokenizer population is not complete'}, status=503)
	cityTokenizer, streetTokenizer = tokenizers

	addressPatternTokenizer = AddressPatternTokenizer(
		streetTokenizer=streetTokenizer,
		cityTokenizer=cityTokenizer
	)

	embedded_text = addressPatternTokenizer.embed(text)
	print(f'Embedded text: {embedded_text}')

	address_match: Optional[AddressObject] = addressPatternTokenizer.match(embedded_text)
	print(f'Address match: {address_match}')

	if address_match is not None:
		address_city = City.objects.select_related('country', 'county', 'state').filter(
			pk=address_match.city_id).first()
		if (address_city is None or address_city.lat is None or address_city.lng is None
		        or (address_match.zip_code and not _has_zip(address_city, address_match.zip_code))
		        or any(int(country_id) != address_city.country_id for country_id in
		               re.findall(r'COUNTRY\((\d+)\)', embedded_text))
		        or (address_match.street_id and not StreetCityMembership.objects.filter(
				city_id=address_match.city_id, street_name_id=address_match.street_id).exists())):
			address_match = None

	if address_match is not None:
		logger.info('Matched address: %r', address_match)
		address_street = StreetName.objects.get(id=address_match.street_id) if address_match.street_id else None

		return JsonResponse({'results': [
			{
				**({'street': address_street.name} if address_street else {}),
				**({'street_number': address_match.streetNumber} if address_street and address_match.streetNumber else {}),
				'city': address_city.name,
				'county': address_city.county.name if address_city.county else None,
				'state': address_city.state.name if address_city.state else None,
				'country': address_city.country.name if address_city.country else None,
				'zip_code': address_city.zip_code,
				'lat': address_city.lat,
				'lng': address_city.lng,
			}
		]})
	else:
		try:
			parts = extract_address(text)
		except AddressExtractionError as exc:
			cause = exc.__cause__ or exc
			logger.warning('Address extraction failed (%s): %s', type(cause).__name__, cause)
			return JsonResponse({'error': 'Address extraction is unavailable'}, status=503)

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
				**({'street_number': parts['house_number']} if street and parts['house_number'] else {}),
				'city': city.name,
				'county': city.county.name if city.county else None,
				'state': city.state.name if city.state else None,
				'country': city.country.name if city.country else None,
				'zip_code': city.zip_code,
				'lat': city.lat,
				'lng': city.lng,
			} for city in matched[:10]
		]})

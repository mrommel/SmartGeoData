import collections
import random
import re
from typing import List, Optional

from strsimpy.weighted_levenshtein import WeightedLevenshtein

from geo import red, blue, green
from geo.constants import AddressRegex
from geo.models import StreetName, AlternativeStreetName, City, AlternativeCityName, Country, AlternativeCountryName, \
	State
from geo.utils import _clean_string, is_integer


uk_zip_country_ids = [25, 27, 47, 53]  # IR, UK, CN, Guernsey


class AmbiguousCity:
	def __init__(self, id: int, name: str, country_id: int, zip_code: str):
		self.id = id
		self.name = name
		self.country_id = country_id
		self.zip_code = zip_code  # fixme: list of zips => zip_codes
		self.matched_zip = None

	def zip_list(self) -> List[str]:
		result_list = []

		if self.zip_code is None:
			return []

		parts: List[str] = self.zip_code.lower().split(',')

		for part in parts:
			if '-' in part:
				r_list = part.split('-')
				start_str = r_list[0]
				end_str = r_list[1]
				zip_len = len(start_str)

				if start_str.isdigit() and end_str.isdigit():
					start = int(start_str)
					end = int(r_list[1])
					for plz in range(start, end + 1):
						result_list.append(str(plz).zfill(zip_len))
				else:
					result_list.append(part)
			else:
				result_list.append(part)

		return result_list

	def __eq__(self, other):
		if isinstance(other, AmbiguousCity):
			return self.id == other.id

		if isinstance(other, int):
			return self.id == other

		raise Exception(f'Cannot compare AmbiguousCity to {type(other)}')

	def __str__(self):
		return f'City: {self.name} ({self.id}, zips:{self.zip_code})'

	def __repr__(self):
		return f'City: {self.name} ({self.id}, zips:{self.zip_code})'



class StreetTokenizer:
	def __init__(self):
		self.street_dict = dict()
		self.street_regex = dict()
		self.street_number_regex = dict()

		self.keywords = [
			' rd ', 'strasse ', 'straße ', 'str ', ' ave ', ' avenue ', ' rue ', ' rua ', ' st ', ' street ',
			' hwy ', ' highway ', ' straat ', ' road '
		]

		self._populated = False

	def reset(self):
		print('StreetTokenizer.reset()')
		self.street_dict = dict()
		self.street_regex = dict()
		self.street_number_regex = dict()

		self._populated = False

	def populate(self):
		if self._populated:
			return

		streetNameQs = StreetName.objects.all().values('id', 'name')
		for customerName in streetNameQs:
			name = _clean_string(customerName['name'])
			id = customerName['id']
			if name in self.street_dict:
				raise Exception('Duplicate street name: "%s" (%s)' % (name, id))

			if len(name) < 3:
				raise Exception('Street name too short: "%s" (%s)' % (name, id))

			self.street_dict[name] = id

		alternateStreetNameQs = AlternativeStreetName.objects.all().values('street__id', 'name')
		for alternateStreetName in alternateStreetNameQs:
			name = _clean_string(alternateStreetName['name'])
			id = alternateStreetName['street__id']
			if name in self.street_dict:
				raise Exception('Duplicate alternate street name: %s (%s)' % (name, id))

			self.street_dict[name] = id

		# order by length of street name
		self.street_dict = collections.OrderedDict(sorted(self.street_dict.items(), key=lambda x: len(x[0]), reverse=True))
		# print(self.street_dict)

		self.load_snapshot(self.street_dict)
		print(f'### populated street dict with {len(self.street_regex.keys()):,} streets')

	def load_snapshot(self, street_dict):
		"""Restore a completed background population in the serving process."""
		self.street_dict = collections.OrderedDict(
			sorted(street_dict.items(), key=lambda item: len(item[0]), reverse=True))
		self.street_regex = dict()
		self.street_number_regex = dict()
		for key, value in self.street_dict.items():
			key = key.replace(' ', r'\s')
			pattern = re.compile(fr'(?<!\S){key}(?!\S)')
			self.street_regex[pattern] = value

		self.street_number_regex[re.compile(r'(stasso(?P<nr>[0-9]{1,3}[a-z]?))')] = f'strasse \g<nr>'  # stasso16
		self.street_number_regex[re.compile(r'(stasse(?P<nr>[0-9]{1,3}))')] = f'strasse \g<nr>'
		self.street_number_regex[re.compile(r'(staße(?P<nr>[0-9]{1,3}))')] = f'straße \g<nr>'
		self.street_number_regex[re.compile(r'(strasse(?P<nr>[0-9]{1,3}))')] = f'strasse \g<nr>'
		self.street_number_regex[re.compile(r'(straße(?P<nr>[0-9]{1,3}))')] = f'straße \g<nr>'
		self.street_number_regex[re.compile(r'(str(?P<nr>[0-9]{1,3}))')] = f'str \g<nr>'
		self.street_number_regex[re.compile(r'(weg(?P<nr>[0-9]{1,3}))')] = f'weg \g<nr>'  # kirchweg2c
		self.street_number_regex[re.compile(r'(nr°(?P<nr>[0-9]{1,3}))')] = f'\g<nr>'  # nr°123
		self.street_number_regex[re.compile(r'(n°(?P<nr>[0-9]{1,3}))')] = f'\g<nr>'  # N°5

		self._populated = True

	def embed(self, text: str, warn: bool = False) -> str:
		# fix common typos
		text = text.replace('strare', 'straße')
		text = text.replace('strabe', 'straße')
		text = text.replace('strabo', 'straße')
		text = text.replace('strafe', 'straße')
		text = text.replace('strake', 'straße')
		text = text.replace('strade', 'straße')
		text = text.replace('strahe', 'straße')
		text = text.replace('strate', 'straße')
		text = text.replace('strae ', 'straße ')  # fix for city: straelen
		text = text.replace('strafie', 'straße')
		text = text.replace('stratte', 'straße')
		text = text.replace('strabge', 'straße')
		text = text.replace('stra8e', 'straße')
		text = text.replace(' n° ', ' ')

		# split street number from street names
		for regex, key in self.street_number_regex.items():
			text = regex.sub(key, text)

		for regex, key in self.street_regex.items():
			# print(f'### regex: "{regex}" - {key}')
			text = regex.sub(f'STREET({key})', text, 1)  # only first occurrence

		if warn and 'STREET(' not in text:
			for keyword in self.keywords:
				if keyword in text:
					warn_keyword = red(keyword)
					print(f'Warning: Found unmatched Street "{warn_keyword}" in "{text}"')

		return text


def zip_insertion_cost(char):
	return 0.8


def zip_deletion_cost(char):
	return 0.8


def zip_substitution_cost(char_a, char_b):
	cost_list = [
		# special character - numbers
		('§', '5', 0.1),
		('$', '3', 0.2),
		('$', '5', 0.2),
		('$', '8', 0.2),
		('$', '4', 0.4),
		# letter - numbers
		('s', '5', 0.1),
		('s', '8', 0.1),
		('S', '5', 0.1),
		('S', '8', 0.1),
		('r', '1', 0.2),
		('g', '8', 0.5),
		# number - number
		('9', '0', 0.5),
		('9', '8', 0.5),
		('9', '5', 0.4),
		('5', '9', 0.4),
		('2', '3', 0.3),
		('3', '5', 0.3),
		('5', '3', 0.3),
		('6', '5', 0.5),
		('6', '4', 0.5),
		('1', '4', 0.3),
		('5', '7', 0.5),
		('1', '7', 0.3),
		('6', '8', 0.5),
		('6', '0', 0.5)
	]

	for char_one, char_two, value in cost_list:
		if (char_one == char_a and char_two == char_b) or (char_one == char_b and char_two == char_a):
			return value

	return 1.0


class ZipChecker:
	def __init__(self):
		self.weighted_levenshtein = WeightedLevenshtein(
			substitution_cost_fn=zip_substitution_cost,
			insertion_cost_fn=zip_insertion_cost,
			deletion_cost_fn=zip_deletion_cost
		)

	def isnumeric(self, zip_code: str) -> bool:
		return len(re.findall("[A-Za-z]", zip_code)) == 0

	def match(self, zip1: str, zip2) -> float:
		prepared_zip1 = self.prepare_zip(zip1)
		prepared_zip2 = self.prepare_zip(zip2)

		dist = self.weighted_levenshtein.distance(prepared_zip1, prepared_zip2)
		max_len = (len(zip1) + len(zip2)) / 2.0

		if max_len == 0:
			return 1.0

		res = 1.0 - (dist / max_len)
		# print(f' => "{zip1}"x"{zip2}" => {dist} => {res}')
		return res

	def prepare_zip(self, zip: str) -> str:
		# cut nederland zips, when combined
		# https://stackoverflow.com/questions/17898523/regular-expression-for-dutch-zip-postal-code
		if re.match(r'^[1-9][0-9]{3} ?(?!sa|sd|ss)[a-z]{2}$', zip, flags=re.IGNORECASE):
			return zip[0:4]

		if re.match(r'^[1-9][0-9]{3}-(?!sa|sd|ss)[a-z]{2}$', zip, flags=re.IGNORECASE):
			return zip[0:4]

		if re.match(r'^[1-9][0-9]{3}(?!sa|sd|ss)[a-z]{2}$', zip, flags=re.IGNORECASE):
			return zip[0:4]

		if re.match(f'^[1-9][0-9]{4}[a-z]$', zip, flags=re.IGNORECASE):  # handling of wrong match
			return zip[0:4]

		# -49565
		if re.match(r'^-[0-9]{5}$', zip, flags=re.IGNORECASE):
			return zip[1:6]

		if zip.startswith('DE-') or zip.startswith('de-'):
			return zip[3:8]

		if zip.startswith('D-') or zip.startswith('d-'):
			return zip[2:7]

		if zip.startswith('A-') or zip.startswith('a-'):
			return zip[2:7]

		if zip.startswith('AT-') or zip.startswith('at-'):
			return zip[3:8]

		if zip.startswith('AUT-') or zip.startswith('aut-'):
			return zip[4:9]

		if zip.startswith('0-'):
			return zip[2:7]

		if zip.startswith('3-'):
			return zip[2:7]

		if re.match(r'^d[0-9]{5}$', zip, flags=re.IGNORECASE):  # D54295
			return zip[1:6]

		if zip.startswith('CH-') or zip.startswith('ch-'):
			return zip[3:7]

		if zip.startswith('NL-') or zip.startswith('nl-'):
			return zip[3:7]

		if zip.startswith('NO-') or zip.startswith('no-'):
			return zip[3:7]

		if zip.startswith('b-') or zip.startswith('B-'):
			return zip[2:7]

		if zip.startswith('i-') or zip.startswith('I-'):
			return zip[2:6]

		if zip.startswith('l-') or zip.startswith('L-'):
			return zip[2:5]

		return zip


class UKZipChecker:
	def __init__(self):
		pass

	def match(self, zip_test: str, zip_city: str) -> float:
		if '-' in zip_city:
			print(f'Warning: UKZipChecker does not support zip with "-": {zip_city}')
			return 0.0

		for zip_city_item in zip_city.lower().split(','):
			if zip_city_item.strip() == '':
				continue

			if zip_test.startswith(zip_city_item):
				return 1.0

		return 0.0


def _input_insertion_cost(char):
	return 0.8


def _input_deletion_cost(char):
	return 0.8


def _input_substitution_cost(char_a, char_b):
	# s (big s) <-> 589
	if (char_a in ['5', '8', '9'] and char_b == 's') or (char_a == 's' and char_b in ['5', '8', '9']):
		return 0.3

	# ß
	if (char_a in ['r', 's', 'h', 'g'] and char_b == 'ß') or (char_a == 'ß' and char_b in ['r', 's', 'h', 'g']):
		return 0.4

	# ü
	if (char_a in ['i', 'u'] and char_b == 'ü') or (char_a == 'ü' and char_b in ['i', 'u']):
		return 0.4

	# ä
	if (char_a in ['a', 'd'] and char_b == 'ä') or (char_a == 'ä' and char_b in ['a', 'd']):
		return 0.1

	# ö
	if (char_a in ['o', 'd', 'é', '6'] and char_b == 'ö') or (char_a == 'ö' and char_b in ['o', 'd', 'é', '6']):
		return 0.1

	# 1 <-> i
	if (char_a == '1' and char_b == 'i') or (char_a == 'i' and char_b == '1'):
		return 0.1

	# 0 (zero) <-> o (oh)
	if (char_a == '0' and char_b == 'o') or (char_a == 'o' and char_b == '0'):
		return 0.3

	# c <-> g
	if (char_a == 'c' and char_b == 'g') or (char_a == 'g' and char_b == 'c'):
		return 0.5

	# v <-> y
	if (char_a == 'v' and char_b == 'y') or (char_a == 'y' and char_b == 'v'):
		return 0.5

	# i <-> t
	if (char_a == 'i' and char_b == 't') or (char_a == 't' and char_b == 'i'):
		return 0.2

	# i,l,|,! <-> i,l,|,!
	if char_a in ['i', 'l', '|', '!'] and char_b in ['i', 'l', '|', '!']:
		return 0.1

	# 2 <-> z
	if (char_a == '2' and char_b == 'z') or (char_a == 'z' and char_b == '2'):
		return 0.2

	return 1.0


class SimilarityChecker:
	def __init__(self):
		self.weighted_levenshtein = WeightedLevenshtein(
			substitution_cost_fn=_input_substitution_cost,
			insertion_cost_fn=_input_insertion_cost,
			deletion_cost_fn=_input_deletion_cost
		)

	def match(self, input0: str, input1: str) -> float:
		max_len = (len(input0) + len(input1)) / 2.0

		dist = self.weighted_levenshtein.distance(input0, input1)
		return 1.0 - (dist / max_len)



class CityTokenizer:
	def __init__(self):
		self.city_dict = dict()
		self.ibd_dict = dict()
		self.country_dict = dict()
		self.state_dict = dict()

		# maps of alternate names mapping back the original names
		self.alternate_city_dict = dict()
		self.alternate_state_dict = dict()
		self.alternate_country_dict = dict()

		self.similarityChecker = SimilarityChecker()
		self.zipChecker = ZipChecker()
		self.ukzipChecker = UKZipChecker()

		self.country_us_id = None
		self.country_cn_id = None
		self.country_aus_id = None

		self.populated = False

	def _clean(self):
		alternatives_dict = dict()
		to_be_deleted = list()

		for alt_city in AlternativeCityName.objects.all():
			if alt_city.name in alternatives_dict and alternatives_dict[alt_city.name] == alt_city.city.id:
				print(f'Found duplicate entry: {alt_city.name}')
				to_be_deleted.append(alt_city.id)
			else:
				alternatives_dict[alt_city.name] = alt_city.city.id

		num_deleted = 0
		for identifier in to_be_deleted:
			alt_city = AlternativeCityName.objects.filter(id=identifier).first()
			alt_city.delete()
			num_deleted += 1

		print(f'deleted {num_deleted} alt cities')

	def reset(self):
		print('CityTokenizer.reset()')
		self.city_dict = dict()
		self.ibd_dict = dict()
		self.country_dict = dict()
		self.state_dict = dict()

		# maps of alternate names mapping back the original names
		self.alternate_city_dict = dict()
		self.alternate_state_dict = dict()
		self.alternate_country_dict = dict()

		self.populated = False

	def tokenize(self, text: str, warnings: bool = True):  # ->: country_id, city_id
		if not self.populated:
			self.populate()

		ambiguous_cities = []

		for city_name, cities_list in self.city_dict.items():
			for (city_id, city_country_id, city_zip_code, city_ambiguous, city_need_zip) in cities_list:
				city_lower = city_name.lower()

				# special rule for cities with spaces
				if ' ' in city_lower and city_lower in text:
					if city_need_zip:
						if city_zip_code is not None:
							ambiguous_city = AmbiguousCity(city_id, city_name, city_country_id, city_zip_code)
							found_zip = False
							for plz in ambiguous_city.zip_list():
								if plz in text:
									found_zip = True

							if not found_zip:
								continue

					if city_ambiguous:
						if city_id not in ambiguous_cities:
							ambiguous_cities.append(AmbiguousCity(city_id, city_name, city_country_id, city_zip_code))
					else:
						return city_country_id, city_id

				# try to get exact match
				if city_lower in re.split(r';|:|,|"|\.|\?|‘|“|\'|\(|\)|_|\s', text):
					if city_need_zip:
						# print(f'check {city_name} in "{text}"')
						if city_zip_code is not None:
							ambiguous_city = AmbiguousCity(city_id, city_name, city_country_id, city_zip_code)
							found_zip = False
							for plz in ambiguous_city.zip_list():
								if plz in text:
									found_zip = True

							if not found_zip:
								continue

					if city_ambiguous:
						if city_id not in ambiguous_cities:
							ambiguous_cities.append(AmbiguousCity(city_id, city_name, city_country_id, city_zip_code))
					else:
						return city_country_id, city_id

		if len(ambiguous_cities) == 1:
			ambiguous_city = ambiguous_cities[0]
			return ambiguous_city.country_id, ambiguous_city.id

		if len(ambiguous_cities) > 1:
			# check zip/plz
			for ambiguous_city in ambiguous_cities:
				if ambiguous_city.zip_code is not None:
					for plz in ambiguous_city.zip_list():
						if plz in text:
							return ambiguous_city.country_id, ambiguous_city.id

			if warnings:
				print(f'Cannot find ambiguous city ({ambiguous_cities}) by zip in "{text}" => choosing random')
			ambiguous_city = random.choice(ambiguous_cities)
			return ambiguous_city.country_id, ambiguous_city.id

		return None, None

	def _embed_zipuk_list(self, text: str, zip_list: List[str]) -> str:
		zip_uk_pattern = '\s(?P<zip>[a-z]{1,2}\d[a-z\d]?\s\d[a-z0-9]{2})\s'
		# https://github.com/mnestorov/regex-patterns?tab=readme-ov-file#ireland
		zip_ir_pattern = '\s(?P<zip>(D6W|[A-Z]{1}[0-9]{1,2}|[A-Z]{2}[0-9]{1,2}|[A-Z]{1}[0-9]{1}[A-Z]{1}|[A-Z]{2}[0-9]{1}[A-Z]{1}))\s'
		zip_can_pattern = '\s(?P<zip>[abceghj-nprstvxy]\d[abceghj-nprstv-z][ -]?\d[abceghj-nprstv-z]\d)\s'

		zip_uk_regex = re.compile(zip_uk_pattern, re.IGNORECASE)
		zip_ir_regex = re.compile(zip_ir_pattern, re.IGNORECASE)
		zip_can_regex = re.compile(zip_can_pattern, re.IGNORECASE)

		for regex in [zip_uk_regex, zip_can_regex, zip_ir_regex]:
			for match in regex.finditer(text):
				match_dict = match.groupdict()
				zip_code = match_dict['zip']
				found_match = False
				for zip_item in zip_list:
					if self.ukzipChecker.match(zip_code, zip_item) > 0.9:
						text = text.replace(f' {zip_code} ', f' ZIPUK({zip_code}) ')
						found_match = True

		return text

	def _embed_zip_czech_list(self, text: str, zip_list: List[str]) -> str:
		zip_czech_pattern_end = '\s(?P<zip>\d{3}\s\d{2})\s'
		zip_czech_regex = re.compile(zip_czech_pattern_end, re.IGNORECASE)
		for match in zip_czech_regex.finditer(text):
			match_dict = match.groupdict()
			zip_code = match_dict['zip']
			matched_zip_code = zip_code.replace(' ', '')
			if matched_zip_code not in zip_list:
				print(f'DEBUG: czech zip code "{matched_zip_code}" not in {zip_list}')
			# continue
			text = text.replace(f' {zip_code} ', f' ZIP({matched_zip_code}) ')

		zip_polish_pattern_end = '\s(?P<zip>\d{2}\-\d{3})\s'
		zip_polish_regex = re.compile(zip_polish_pattern_end, re.IGNORECASE)
		for match in zip_polish_regex.finditer(text):
			match_dict = match.groupdict()
			zip_code = match_dict['zip']
			matched_zip_code = zip_code.replace('-', '')
			if matched_zip_code not in zip_list:
				print(f'DEBUG: polish zip code "{matched_zip_code}" not in {zip_list}')
			# continue
			text = text.replace(f' {zip_code} ', f' ZIP({matched_zip_code}) ')

		return text

	def _embed_zip_portugal_list(self, text: str, zip_list: List[str]) -> str:
		# print(f'DEBUG: _embed_zip_portugal_list {zip_list} for "{text}"')
		zip_portugal_pattern = '\s(?P<zip>\d{4}-\d{3})\s'
		zip_portugal_regex = re.compile(zip_portugal_pattern, re.IGNORECASE)
		for match in zip_portugal_regex.finditer(text):
			match_dict = match.groupdict()
			zip_code = match_dict['zip']

			for zip_item in zip_list:
				if zip_code.startswith(zip_item):
					text = text.replace(f' {zip_code} ', f' ZIP({zip_item}) ')
			# print(f'DEBUG: matched: "{zip_code}" -> {zip_item}')

		return text

	def _embed_other_zip_list(self, text: str, zip_list: List[str]) -> str:
		# print(f'DEBUG: _embed_other_zip_list {zip_list} for "{text}"')
		for zip_code in zip_list:
			if zip_code in text:
				text = text.replace(f' {zip_code} ', f' ZIP({zip_code}) ')

		return text

	def _embed_zip_list(self, text: str, zip_list: List[str]) -> str:
		tokens = []
		# print(f'DEBUG: _embed_zip_list {zip_list} for "{text}"')

		for token in text.split(' '):
			best_zip = None
			best_value = 0.0

			for zip_code in zip_list:
				if 'bis' in zip_code:
					continue

				if zip_code.strip() == '':
					raise Exception(f'Empty zip code in "{zip_list}" for "{text}"')
					continue

				if not zip_code.isnumeric():
					# print(f'Invalid zip code: "{zip_code}" in "{text}"')
					continue

				tmp_value = self.zipChecker.match(zip_code, token)

				if tmp_value > best_value:
					best_zip = zip_code
					best_value = tmp_value

			if best_value >= 0.9:
				tokens.append(f'ZIP({best_zip})')
			else:
				tokens.append(token)

		return ' '.join(tokens)

	def embed(self, text: str, city_name_length: int = -1) -> str:
		ambiguous_cities = []
		city_zip_code = None

		text = ' ' + text + ' '

		found = False
		for city_name, cities_list in self.city_dict.items():
			if city_name_length != -1 and len(city_name) != city_name_length:
				continue

			for (city_id, city_country_id, city_zip_codes, city_ambiguous, city_need_zip) in cities_list:
				city_lower = city_name.lower()
				city_lower_spaces = ' ' + city_lower + ' '

				# special rule for cities with spaces
				if ' ' in city_lower and city_lower_spaces in text:
					if city_need_zip or city_ambiguous:
						if city_zip_codes is not None:
							ambiguous_city = AmbiguousCity(city_id, city_name, city_country_id, city_zip_codes)
							found_zip = False
							for plz in ambiguous_city.zip_list():
								if plz in text:  # and plz.isnumeric():
									city_zip_code = plz
									found_zip = True

							if not found_zip:
								continue

					if city_ambiguous:
						if city_id not in ambiguous_cities:
							a_city = AmbiguousCity(city_id, city_name, city_country_id, city_zip_codes)
							a_city.matched_zip = city_zip_code
							ambiguous_cities.append(a_city)
					else:
						text = text.replace(city_lower_spaces, f' CITY({city_id}) ')
						# print(f'DEBUG: found city: {city_id} in "{text}"')
						if city_zip_codes is not None:
							# print(f'DEBUG: try to find {city_zip_codes} in "{text}"')
							tmp_ambiguous_city = AmbiguousCity(city_id, city_name, city_country_id, city_zip_codes)
							# print(f'DEBUG: unpacked {city_zip_codes} into "{tmp_ambiguous_city.zip_list()}"')
							if city_country_id in uk_zip_country_ids:
								text = self._embed_zipuk_list(text, tmp_ambiguous_city.zip_list())
							elif city_country_id in [34, 35]:  # poland, czechia
								text = self._embed_zip_czech_list(text, tmp_ambiguous_city.zip_list())
							elif city_country_id in [50]:  # andorra
								text = self._embed_other_zip_list(text, tmp_ambiguous_city.zip_list())
							elif city_country_id in [28]:  # portugal
								text = self._embed_zip_portugal_list(text, tmp_ambiguous_city.zip_list())
							else:
								text = self._embed_zip_list(text, tmp_ambiguous_city.zip_list())
						found = True

				# try to get exact match
				if city_lower in re.split(r';|:|,|"|\.|\?|‘|“|\'|\(|\)|_|\s', text):
					if city_need_zip or city_ambiguous:
						# print(f'check {city_name} in "{text}"')
						if city_zip_codes is not None:
							ambiguous_city = AmbiguousCity(city_id, city_name, city_country_id, city_zip_codes)
							found_zip = False
							for plz in ambiguous_city.zip_list():
								if plz in text:
									city_zip_code = plz
									found_zip = True

							if not found_zip and not city_ambiguous:
								continue

					if city_ambiguous:
						if city_id not in ambiguous_cities:
							a_city = AmbiguousCity(city_id, city_name, city_country_id, city_zip_codes)
							a_city.matched_zip = city_zip_code
							ambiguous_cities.append(a_city)
					else:
						text = text.replace(' ' + city_name + ' ', f' CITY({city_id}) ')
						# print('DEBUG: found city: %s in "%s"' % (city_id, text))
						if city_zip_codes is not None and city_zip_codes.strip() != '':
							tmp_ambiguous_city = AmbiguousCity(city_id, city_name, city_country_id, city_zip_codes)
							if city_country_id in uk_zip_country_ids:
								# print('DEBUG: _embed_zipuk_list')
								text = self._embed_zipuk_list(text, tmp_ambiguous_city.zip_list())
							elif city_country_id in [28]:  # portugal
								# print('DEBUG: _embed_zip_portugal_list')
								text = self._embed_zip_portugal_list(text, tmp_ambiguous_city.zip_list())
							elif city_country_id in [34, 35]:  # poland, czechia
								# print('DEBUG: _embed_zip_czech_list')
								text = self._embed_zip_czech_list(text, tmp_ambiguous_city.zip_list())
							elif self.zipChecker.isnumeric(city_zip_codes):
								# print('DEBUG: _embed_zip_list')
								text = self._embed_zip_list(text, tmp_ambiguous_city.zip_list())
							elif city_country_id in [50]:  # andorra - adxxx
								pass  # todo: implement andorra zip parsing
							elif city_country_id in [60]:  # malta - 3 letters
								pass  # todo: implement malta zip parsing
							else:
								raise Exception(
									f'Unsupported zip code format: {city_name} ({city_id}): {city_zip_codes}')
						else:
							print(f'Warning: Zip of {city_name} ({city_id}) is empty in {text}')

		if len(ambiguous_cities) == 1:
			ambiguous_city = ambiguous_cities[0]
			text = text.replace(' ' + ambiguous_city.name + ' ', f' CITY({ambiguous_city.id}) ')
			if ambiguous_city.matched_zip is not None:
				text = self._embed_zip_list(text, [ambiguous_city.matched_zip])
		elif len(ambiguous_cities) > 1:
			found = False
			# check zip/plz
			for ambiguous_city in ambiguous_cities:
				if ambiguous_city.zip_code is not None:
					if ambiguous_city.matched_zip is not None and ambiguous_city.country_id in uk_zip_country_ids:
						zip_uk_pattern = '\s(?P<zip>[a-z]{1,2}\d[a-z\d]{0,1}\s\d[a-z]{2})\s'
						zip_uk_regex = re.compile(zip_uk_pattern, re.IGNORECASE)
						for match in zip_uk_regex.finditer(text):
							match_dict = match.groupdict()
							zip_code = match_dict['zip']

							if self.ukzipChecker.match(zip_code, ambiguous_city.matched_zip) > 0.9:
								text = text.replace(' ' + ambiguous_city.name + ' ', f' CITY({ambiguous_city.id}) ')
								text = self._embed_zipuk_list(text, [zip_code])

								found = True

					for plz in ambiguous_city.zip_list():
						if plz in text and plz.isnumeric():
							text = text.replace(' ' + ambiguous_city.name + ' ', f' CITY({ambiguous_city.id}) ')

							# normal zip
							if ambiguous_city.matched_zip is not None and ambiguous_city.matched_zip.isnumeric():
								if self.zipChecker.match(ambiguous_city.matched_zip, plz) > 0.9:
									text = self._embed_zip_list(text, [ambiguous_city.matched_zip])
									found = True

							# uk zip
							if ambiguous_city.matched_zip is not None and ambiguous_city.country_id in uk_zip_country_ids:
								if self.zipChecker.match(ambiguous_city.matched_zip, plz) > 0.9:
									text = self._embed_zipuk_list(text, [ambiguous_city.matched_zip])
									found = True

			if not found:
				ambiguous_city = random.choice(ambiguous_cities)
				text = text.replace(' ' + ambiguous_city.name + ' ', f' CITY({ambiguous_city.id}) ')

				if ambiguous_city.country_id in uk_zip_country_ids and ambiguous_city.matched_zip is not None:
					text = self._embed_zip_list(text, [ambiguous_city.matched_zip])
				elif ambiguous_city.matched_zip is not None:
					text = self._embed_zip_list(text, [ambiguous_city.matched_zip])

		# check country
		for country_name, country_id in self.country_dict.items():
			if city_name_length != -1 and len(country_name) != city_name_length:
				continue

			if country_name in text.split(' '):
				text = text.replace(country_name, f'COUNTRY({country_id})')

			if ' ' in country_name and country_name in text:  # special rule for countries with spaces
				text = text.replace(country_name, f'COUNTRY({country_id})')

		# handle special case for nederlands 'ZIP(3962) ec CITY(1690)'
		zip = 'ZIP\((?P<zip>[0-9]+)\)'
		zip_nl = '(?P<zip_nl>[a-z]{2})'
		city = 'CITY\((?P<city>[0-9]+)\)'
		nl_pattern = fr'{zip}\s{zip_nl}\s{city}'
		nl_regex = re.compile(nl_pattern)
		for match in nl_regex.finditer(text):
			match_dict = match.groupdict()
			# print(match_dict)
			zip_code = match_dict['zip']
			zip_nl_code = match_dict['zip_nl']
			city_id = match_dict['city']
			text = text.replace(f'ZIP({zip_code}) {zip_nl_code} CITY({city_id})', f'ZIP({zip_code}) CITY({city_id})')

		# handle UK zip
		# https://stackoverflow.com/questions/164979/regex-for-matching-uk-postcodes?page=1&tab=scoredesc#tab-top
		# ^[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}$
		if 'ZIP(' not in text:
			zip_uk_pattern_end = '\s(?P<zip>[a-z]{1,2}\d[a-z\d]{0,1}\s\d[a-z]{2})\s'
			zip_uk_regex = re.compile(zip_uk_pattern_end, re.IGNORECASE)
			for match in zip_uk_regex.finditer(text):
				match_dict = match.groupdict()
				zip_code = match_dict['zip']
				text = text.replace(f'{zip_code}', f'ZIPUK({zip_code})')

		# fallback - no city but a valid zip
		if 'CITY(' not in text:
			zip45_pattern_end = '[\s-](?P<zip>[0-9]{4,5})$'
			zip45_regex_end = re.compile(zip45_pattern_end, re.IGNORECASE)
			for match in zip45_regex_end.finditer(text):
				match_dict = match.groupdict()
				zip_code = match_dict['zip']
				text = text.replace(f'{zip_code}', f'ZIP({zip_code})')

			zip45_pattern_mid = '[\s-](?P<zip>[0-9]{4,5})\s'
			zip45_regex_mid = re.compile(zip45_pattern_mid, re.IGNORECASE)
			for match in zip45_regex_mid.finditer(text):
				match_dict = match.groupdict()
				zip_code = match_dict['zip']
				text = text.replace(f'{zip_code}', f'ZIP({zip_code})')

		return text.strip()

	def tokenize_ibd(self, text: str):
		if not self.populated:
			self.populate()

		# find IBD by name
		for ibd_name, (city_country_id, city_id) in self.ibd_dict.items():
			if ibd_name in text:
				return city_country_id, city_id

		return None, None

	def tokenize_ibd_with_name(self, text: str):
		if not self.populated:
			self.populate()

		# find IBD by name
		for ibd_name, (city_country_id, city_id) in self.ibd_dict.items():
			if ibd_name in text:
				return city_country_id, city_id, ibd_name

		return None, None, None

	def tokenize_country(self, text: str):
		if not self.populated:
			self.populate()

		for country_name, country_id in self.country_dict.items():
			if country_name in text.split(' '):
				return country_id, None

			if ' ' in country_name and country_name in text:  # special rule for countries with spaces
				return country_id, None

		return None, None

	def tokenize_state(self, text: str):
		if not self.populated:
			self.populate()

		for state_name, country_id in self.state_dict.items():
			if state_name in text.split(' '):
				return country_id, None

			if ' ' in state_name and state_name in text:  # special rule for states with spaces
				return country_id, None

		return None, None

	def tokenize_city_name(self, token: str):
		"""
			method returns real city name for given alternative name
			parts are not supported
		"""
		if not self.populated:
			self.populate()

		for alt_city_name, city_name in self.alternate_city_dict.items():
			if alt_city_name == token:
				return city_name

		return None

	def tokenize_city_name_with_context(self, token: str, text: str, warnings: bool = True):
		"""
			method returns real city name for given alternative name
			parts are not supported
		"""
		if not self.populated:
			self.populate()

		word_array = []
		token_array = text.lower().split(' ')

		last_word = None
		index_of_tag_in_array = -1
		idx = 0
		for tag in token_array:
			if tag == token:
				index_of_tag_in_array = idx

			if last_word != tag:
				word_array.append(tag.lower())
				idx += 1
			last_word = tag.lower()

		# print(f'full word_array={word_array} => index: {index_of_tag_in_array}')

		sliced_word_array = []
		if index_of_tag_in_array == 0:
			sliced_word_array.append('#')
			sliced_word_array.append('#')
		elif index_of_tag_in_array == 1:
			sliced_word_array.append('#')

		for idx, word in enumerate(word_array):
			if idx + 2 >= index_of_tag_in_array >= idx - 2:
				sliced_word_array.append(word)

		if index_of_tag_in_array == len(word_array) - 1:
			sliced_word_array.append('#')
			sliced_word_array.append('#')
		elif index_of_tag_in_array == len(word_array) - 2:
			sliced_word_array.append('#')

		# print(f'sliced word_array={sliced_word_array}')
		slice_words_lower = " ".join(sliced_word_array)
		_, city_id = self.tokenize(slice_words_lower, warnings=warnings)

		if city_id is not None:
			city = City.objects.filter(id=city_id).first()  # fixme: use new dict

			if city is None:
				raise Exception(f'Cannot find city for {city_id}')

			tmp_city_name = city.name
			tmp_city_name_parts = tmp_city_name.split(' ')
			for tmp_city_name_part in tmp_city_name_parts:
				if self.similarityChecker.match(tmp_city_name_part, token) > 0.9:
					return tmp_city_name

		return None

	def tokenize_state_name(self, text: str):
		"""
			method returns real state name for given alternative name
			parts are not supported
		"""
		if not self.populated:
			self.populate()

		for alt_state_name, state_name in self.alternate_state_dict.items():
			if alt_state_name == text:
				return state_name

		return None

	def tokenize_country_name(self, text: str):
		"""
			method returns real country name for given alternative name
			parts are not supported
		"""
		if not self.populated:
			self.populate()

		for alt_country_name, country_name in self.alternate_country_dict.items():
			if alt_country_name == text:
				return country_name

		return None

	def populate(self):
		if self.populated:
			return

		num_cities = 0
		num_ambiguous_cities = 0

		# populate countries
		num_countries = 0
		countryQs = Country.objects.all().values('id', 'name')
		for country in countryQs:
			country_id = country['id']
			country_name = _clean_string(country['name'])

			self.country_dict[country_name.lower()] = country_id
			self.alternate_country_dict[country_name.lower()] = country_name.lower()
			num_countries += 1

			altCountryQs = AlternativeCountryName.objects.filter(country__id=country_id).values_list('name', flat=True)
			for alternative_name in altCountryQs:
				self.country_dict[alternative_name.lower()] = country_id
				self.alternate_country_dict[alternative_name.lower()] = country_name.lower()
				num_countries += 1

			if country_name == 'united states':
				self.country_us_id = country_id
			elif country_name == 'canada':
				self.country_cn_id = country_id
			elif country_name == 'australia':
				self.country_aus_id = country_id

		if self.country_us_id is None:
			print(red('WARNING: us country id not initialized'))
		if self.country_cn_id is None:
			print(red('WARNING: canada country id not initialized'))
		if self.country_aus_id is None:
			print(red('WARNING: australia country id not initialized'))

		citiesQs = City.objects.all()
		for city in citiesQs:
			city_name = _clean_string(city.name)
			if city_name in self.city_dict:
				raise Exception(
					f'City names must be unique! Found already a city with name: {city.name} => {self.city_dict[city_name]}')

			zip_code = city.zip_code.lower() if city.zip_code is not None else None
			self.city_dict[city_name] = [
				(city.id, city.country.id, zip_code, False, False)]  # ambiguous=False, need_zip=False
			self.alternate_city_dict[city_name] = city_name
			num_cities += 1

			has_state_alternative = False
			for alternative_city in city.alternative_city_names():
				if alternative_city.name not in self.city_dict:
					self.city_dict[alternative_city.name.lower()] = []

				self.city_dict[alternative_city.name.lower()].append(
					(city.id, city.country.id, city.zip_code, alternative_city.ambiguous, alternative_city.need_zip))

				# check us and can cities for alternative names with state
				if city.country.id in [self.country_cn_id, self.country_us_id, self.country_aus_id]:
					if city.state is None:
						print(f'WARNING: {city.name} has no state')
					elif city.state.iso2 is None:
						print(f'WARNING: {city.state.name} has no iso2')
					else:
						state_iso = ' ' + city.state.iso2.lower()
						if alternative_city.name.lower().endswith(state_iso):
							has_state_alternative = True

				# only add if alternate city name does not need zip
				if not alternative_city.need_zip:
					self.alternate_city_dict[alternative_city.name.lower()] = city.name.lower()
				num_ambiguous_cities += 1

			if city.country.id in [self.country_cn_id, self.country_us_id, self.country_aus_id]:
				if not has_state_alternative:
					state_iso2 = city.state.iso2 if city.state is not None else '-'
					print(
						f'WARNING: {city.name} ({city.id}) is {city.country.name} but has no state ({state_iso2}) alternative')

		ambiguous_cities_count = dict()
		non_ambiguous_cities_count = dict()
		for city_name, cities_list in self.city_dict.items():
			for (city_id, city_country_id, city_zip_code, city_ambiguous, city_need_zip) in cities_list:
				if city_ambiguous:
					if city_name not in ambiguous_cities_count:
						ambiguous_cities_count[city_name.lower()] = 1
					else:
						ambiguous_cities_count[city_name.lower()] += 1
				else:
					if city_name not in non_ambiguous_cities_count:
						non_ambiguous_cities_count[city_name.lower()] = 1
					else:
						non_ambiguous_cities_count[city_name.lower()] += 1

		for key, value in ambiguous_cities_count.items():
			if value < 2:
				raise Exception(f'Ambiguous City not needed: "{key}"')

		for key, value in non_ambiguous_cities_count.items():
			if value > 1:
				raise Exception(f'Non-Ambiguous City needs to be ambiguous: "{key}"')

		# sort by key length (start with longest)
		sorted_keys = sorted(self.city_dict.keys(), key=len, reverse=True)
		self.city_dict = dict(zip(sorted_keys, [self.city_dict[key] for key in sorted_keys]))

		# populate IBD by name
		# num_ibds = 0
		# ibdQs = IBD.objects.all().values('name', 'city__country__id', 'city__id')
		# for ibd_item in ibdQs:
		# 	ibd_name = _clean_string(ibd_item['name'])
		# 	city_country_id = ibd_item['city__country__id']
		# 	city_id = ibd_item['city__id']
		#
		# 	self.ibd_dict[ibd_name] = (city_country_id, city_id)
		# 	num_ibds += 1
		#
		# ibdQs = AlternativeIBDName.objects.all().values('name', 'ibd__city__country__id', 'ibd__city__id')
		# for alternative_ibd in ibdQs:
		# 	ibd_name = _clean_string(alternative_ibd['name'])
		# 	city_country_id = alternative_ibd['ibd__city__country__id']
		# 	city_id = alternative_ibd['ibd__city__id']
		#
		# 	self.ibd_dict[ibd_name] = (city_country_id, city_id)
		# 	num_ibds += 1

		# sort by key length (start with longest)
		sorted_keys = sorted(self.country_dict.keys(), key=len, reverse=True)
		self.country_dict = dict(zip(sorted_keys, [self.country_dict[key] for key in sorted_keys]))

		# populate states
		num_states = 0
		stateQs = State.objects.all().values('country__id', 'name', 'alternative_names')
		for state in stateQs:
			country_id = state['country__id']
			state_name = state['name']
			state_alternative_names = state['alternative_names']

			self.state_dict[state_name.lower()] = country_id
			self.alternate_state_dict[state_name.lower()] = state_name.lower()
			num_states += 1

			if state_alternative_names is not None:
				for alternative_name in state_alternative_names.split(','):
					self.state_dict[alternative_name.lower()] = country_id
					self.alternate_state_dict[alternative_name.lower()] = state_name.lower()
					num_states += 1

		# sort by key length (start with longest)
		sorted_keys = sorted(self.state_dict.keys(), key=len, reverse=True)
		self.state_dict = dict(zip(sorted_keys, [self.state_dict[key] for key in sorted_keys]))

		self.populated = True
		print(f'### populated city dict with {num_cities:,} cities and {num_ambiguous_cities:,} alternative city names')
		# print(f'### populated ibd dict with {num_ibds:,}')
		print(f'### populated country dict with {num_countries:,}')
		print(f'### populated state dict with {num_states:,}')

	def city_by_id(self, city_id: int) -> Optional[str]:
		if not is_integer(city_id):
			print(f'Warning: {city_id} is not an integer')
			return None

		if not self.populated:
			self.populate()

		# print(f'Check for {city_id}')
		for key, city_record_list in self.city_dict.items():
			for (city_record_id, _, _, _, _) in city_record_list:
				# print(f'* Checking {value} == {city_id}')
				if city_record_id == city_id:
					return key

		return None

	def city_id_by_zid(self, zip_code: str) -> Optional[str]:
		if not is_integer(zip_code):
			print(f'Warning: zip {zip_code} is not an integer')
			return None

		if not self.populated:
			self.populate()

		city_id_set = set()

		for city_name, cities_list in self.city_dict.items():
			for (city_id, city_country_id, city_zip_codes, city_ambiguous, city_need_zip) in cities_list:
				if city_need_zip or city_ambiguous:
					if city_zip_codes is not None:
						ambiguous_city = AmbiguousCity(city_id, city_name, city_country_id, city_zip_codes)

						for plz in ambiguous_city.zip_list():
							if self.zipChecker.match(zip_code, plz) >= 0.9:
								city_id_set.add(city_id)

		if len(city_id_set) == 1:
			return city_id_set.pop()
		elif len(city_id_set) > 1:
			print(f'Warning: multiple cities found for zip {green(zip_code)}: {blue(str(list(city_id_set)))}')
			for city in City.objects.filter(id__in=list(city_id_set)):
				for city_zip_code in city.zip_list():
					if zip_code == city_zip_code:
						print(f'Selected exact matching City: {blue(city.id)} with zip {green(city_zip_code)}')
						return city.id

			random_city_id = city_id_set.pop()
			print(f'Selected random City: {blue(random_city_id)}')
			return random_city_id

		return None


class AddressObject:
	def __init__(self):
		self.street = None  # name str
		self.street_id = None
		self.streetNumber = None
		self.zip_code = None
		self.city = None  # name str
		self.city_id = None
		self.country = None

	def __eq__(self, other: 'AddressObject'):
		if not isinstance(other, AddressObject):
			return False

		if self.street != other.street:
			return False

		if self.streetNumber != other.streetNumber:
			return False

		if self.zip_code != other.zip_code:
			return False

		if self.city != other.city:
			return False

		if self.country != other.country:
			return False

		return True

	def __str__(self):
		street_str = '-'
		if self.street is not None:
			if self.streetNumber is None:
				street_str = self.street
			else:
				if self.city is None:
					street_str = f'{self.street} {self.streetNumber}'
				else:
					city_obj = City.objects.get(id=self.city_id)
					if city_obj.country.id in [22, 27]:  # F, GB
						street_str = f'{self.streetNumber} {self.street}'
					else:
						street_str = f'{self.street} {self.streetNumber}'

		return f'street: {street_str}, zip: {self.zip_code}, city: {self.city}, country: {self.country}'

	def __repr__(self):
		return f'street: {self.street} {self.streetNumber}, zip: {self.zip_code}, city: {self.city}, country: {self.country}'


class CombinedStreetCityTokenizer:
	def __init__(self, streetTokenizer: StreetTokenizer, cityTokenizer: CityTokenizer):
		self.combined_dict = dict()
		self.combined_regex = dict()

		self.streetTokenizer = streetTokenizer
		self.cityTokenizer = cityTokenizer

		self.max_length = -1

		self._populated = False

	def populate(self):
		if self._populated:
			return

		for key, value in self.streetTokenizer.street_dict.items():
			if key in self.cityTokenizer.city_dict:
				self.combined_dict[key] = (value, self.cityTokenizer.city_dict[key])

		self.combined_dict = collections.OrderedDict(sorted(self.combined_dict.items(), key=lambda x: len(x[0]), reverse=True))

		for key, value in self.combined_dict.items():
			key = key.replace(' ', r'\s')
			pattern = re.compile(fr'(?<!\S){key}(?!\S).*(?<!\S){key}(?!\S)')
			self.combined_regex[pattern] = value

		# print(f'### Found {len(self.combined_dict.keys()):,} combined street/city names')

		if len(self.combined_regex.values()) > 0:
			max_combined_length = max(len(x) for x in self.combined_regex.values())
		else:
			max_combined_length = 0

		if len(self.streetTokenizer.street_dict.keys()) > 0:
			max_street_length = max(len(x) for x in self.streetTokenizer.street_dict.keys())
			max_city_length = max(len(x) for x in self.cityTokenizer.city_dict.keys())
			self.max_length = max([max_combined_length, max_street_length, max_city_length])
			# print(f'### Max pattern length: {self.max_length}')
			# traceback.print_stack(limit=5)

			self._populated = True

	def embed(self, text: str) -> str:
		for length in reversed(range(self.max_length + 1)):
			# 1st: check combined
			for regex, key in self.combined_regex.items():
				if len(key) != length:
					continue

				for match in regex.finditer(text):
					match_dict = match.groupdict()
					print(f'Todo: ### Match found by CombinedStreetCityTokenizer: {match_dict} in "{text}"')
					# print(f'### regex: "{regex}" - {key}')
					# text = regex.sub(f'STREET({key})', text, 1)  # only first occurrence

			# 2nd: check street
			for streetName, regex_item in zip(self.streetTokenizer.street_dict.keys(), self.streetTokenizer.street_regex.items()):
			# for regex, key in self.streetTokenizer.street_regex.items():
				regex, streetId = regex_item
				if len(streetName) != length:
					continue

				# print(f'### regex: "{regex}" - {key}')
				text = regex.sub(f'STREET({streetId})', text, 1)  # only first occurrence

			# 3rd: check city
			text = self.cityTokenizer.embed(text, length)

		return text


class AddressPatternTokenizer:
	def __init__(self, streetTokenizer: StreetTokenizer, cityTokenizer: CityTokenizer):
		street = AddressRegex.street
		street_number = AddressRegex.street_number
		zip = AddressRegex.zip
		uk_zip = AddressRegex.uk_zip
		city = AddressRegex.city

		# street pattern
		# '55 rue victor hugo'
		# 'allee', 'strake' etc

		# sorted by prio
		self.pattern_list = [
			# prio 5 - fallbacks
			fr'{street}\s{street_number}\s{zip}\s{city}',  # no name, but street number
			fr'{street_number}\s{street}\s{zip}\s{city}',  # no name, but french street number
			fr'{street}\s{street_number}\s{city}\s{zip}',  # no name, but street number
			fr'{street_number}\s{street}\s{city}\s{zip}',  # no name, but french street number
			fr'{street_number}\s{street}\s{city}\s{uk_zip}',  # fallback - only street and uk city
			fr'{street_number}\s{street}\s{uk_zip}\s{city}',  # fallback - only street and uk city
			fr'{street}\s{street_number}\s{uk_zip}\s{city}',  # fallback - only street and uk city

			# no number but zip
			fr'{street}\s{zip}\s{city}',  # no name, no street number
			fr'{street}\s{uk_zip}\s{city}',  # fallback - only street and uk city
			fr'{street}\s{city}\s{uk_zip}',  # fallback - only street and uk city

			# no zip
			fr'{street}\s{street_number}\s{city}',   # fallback - only street and city

			fr'{street_number}\s{street}\s{city}',  # fallback - only street and city

			# last fallback
			fr'{street}\s{city}',  # fallback - only street and city
			fr'{zip}\s{city}',  # fallback - only zip and city
			fr'{city}\s{zip}',  # fallback - only zip and city
			fr'{city}\s{uk_zip}',
			fr'{uk_zip}\s{city}',
		]
		# self.pattern_dict = sorted(self.patterns, key=lambda x: len(x), reverse=True)
		self.regex_list = list(map(re.compile, self.pattern_list))

		self.skip_tokens = [
			'ort', 'plz', 'name', 'vorname', 'geburtsdatum', 'land', 'firmenname', 'hausummer',
			'rechnungsadresse:', 'lieferadresse:', 'nr', 'firma', 'name/firma', 'vorname:',
			'lleferadresse', 'leferadresse', 'lieferadresse', 'kunden-daten', 'absender',
			'unverbindliche', 'mitarbeiter', 'abholdatum', 'liefer-', 'versandadresse', 'kundencaten',
			'mharbelterin', 'mitarbelters', 'adresse', 'livraison', 'delours', 'mitarbeiters',
			'nutzer', 'vor-', 'nachname', 'ceschaftsalhaer', 'kundendaten', 'leasingrate', 'inkl',
			'-rechnungsadresse', 'leasingnehmer', 'untemehmensname', 'hausnummer', 'firmencode',
			'facturation', 'adrosse', 'diagnostictool', 'leasingnutzer', 'arbeitgeber', 'sachbearbeiter',
			'geschiftsfdhrerinnen', 'livralson', 'lueferanschrift', 'kostenstelle', 'selbstabholer',
			'auftrag', 'erstellungsdatum', 'jobrad-angebotscode', 'licferadresse', 'bestelldbersicht',
			'rundum-schutz', 'erstinspektion', 'emall-adresse', 'leasingobjekt', 'postleitzahl',
			'postcode', 'herzlichen', 'dank', 'artikel-nr', 'aussteller', 'empfanger', 'buchung',
			'kundenservice', 'lieferadresso', 'leistung', 'lieferdatum', 'wertgarantie', 'lieferdatum',
			'vorabdberweisung', 'rechniingsdatum', 'bearbeiter', 'emait', 'licteradresse', 'anschrift',
			'leasingnutzer', 'ueferscheln',
			#
			'-', '~', '°', '—', '»'
		]

		self.ukzipChecker = UKZipChecker()

		self.streetTokenizer = streetTokenizer
		self.cityTokenizer = cityTokenizer

		# find duplicate tokens in street and city
		self.combinedStreetCityTokenizer = CombinedStreetCityTokenizer(streetTokenizer, cityTokenizer)
		self.combinedStreetCityTokenizer.populate()

	def _name_by_id(self, name_id: int) -> str:
		for key, value in self.nameTokenizer.name_dict.items():
			if value == name_id:
				return key

		raise Exception(f'Cannot find name_id {name_id}')

	def _street_by_id(self, street_id: int) -> str:
		for key, value in self.streetTokenizer.street_dict.items():
			if value == street_id:
				return key

		raise Exception(f'Cannot find street_id {street_id}')

	def embed(self, text: str) -> str:
		self.combinedStreetCityTokenizer.populate()  # if no already

		tmp_text = _clean_string(text)

		if len(tmp_text) == 0:
			return ''

		tmp_tokens = []
		for token in tmp_text.split(' '):
			if token in self.skip_tokens:
				continue

			tmp_tokens.append(token)

		if len(tmp_tokens) == 0:
			return ''

		customer_words = ' '.join(tmp_tokens)

		# check combined street/city names
		customer_words = self.combinedStreetCityTokenizer.embed(customer_words)

		# post-processing - remove ZIP(ZIP(53501))
		zip_pattern = r'ZIP\(ZIP\((?P<zip>[0-9]+)\)\)'
		zip_regex = re.compile(zip_pattern, re.IGNORECASE)

		while 'ZIP(ZIP(' in customer_words:
			for match in zip_regex.finditer(customer_words):
				match_dict = match.groupdict()
				zip_code = match_dict['zip']
				customer_words = zip_regex.sub(f'ZIP({zip_code})', customer_words, 1)

		if ' d-ZIP(' in customer_words:
			print(f'Warning: Found d-ZIP in "{customer_words}" - replacing with ZIP')
			customer_words = customer_words.replace(' d-ZIP(', ' ZIP(')

		return customer_words

	def match(self, text, verbose: bool=False) -> Optional[AddressObject]:
		text = (' ' + text + ' ').replace(' n ', ' ').strip()  # get rid of single 'n' words
		text = (' ' + text).replace(' nr°', ' ').strip()  # nr°
		text = (' ' + text + ' ').replace(' snc ', ' ').strip()  # snc

		# fix double spaces bug - https://stackoverflow.com/questions/2077897/substitute-multiple-whitespace-with-single-whitespace-in-python
		text = ' '.join(text.split())

		for regex_index, regex in enumerate(self.regex_list):
			for match in regex.finditer(text):
				match_dict = match.groupdict()

				# print(f'DEBUG: found match: {regex_index} - {regex.pattern}')

				if verbose:
					print(f'match_dict: {match_dict}', flush=True)

				obj = AddressObject()
				if 'name' in match_dict:
					name_id = int(match_dict['name'])
					obj.name = self._name_by_id(name_id).title()
					obj.name_id = name_id
				obj.surname = match_dict['surname'] if 'surname' in match_dict else None

				# handle street
				if 'street' in match_dict:
					street_id = int(match_dict['street'])
					obj.street = self._street_by_id(street_id).title()
					obj.street_id = street_id
				obj.streetNumber = match_dict['street_number'] if 'street_number' in match_dict else None

				# print(f'DEBUG: zip={match_dict.get("zip", None)}, zipuk={match_dict.get("zipuk", None)}')
				obj.zip_code = match_dict['zip'] if 'zip' in match_dict else None

				# uk zip
				if obj.zip_code is None and 'zipuk' in match_dict:
					zipuk = match_dict['zipuk']

					# need to verify uk zip here (and not when the embedding is done)
					if 'city' in match_dict:
						city_id = int(match_dict['city'])
						city_uk = City.objects.get(id=city_id)

						if city_uk.zip_code is None or city_uk.zip_code.strip() == '':
							print(f'Warning: UK city {city_uk.name} has no zip code')
							return None

						city_match = self.ukzipChecker.match(zipuk, city_uk.zip_code) > 0.9

						if city_match and city_uk.country.id not in uk_zip_country_ids:
							raise Exception(f'Warning: UK zip {zipuk} in non-UK city {city_uk.name} ({city_uk.country.name}) in "{text}"')
							return None
						elif city_match:
							# print(f'Debug: Found uk zip match: {zipuk} in {city_uk.zip_code}')
							obj.zip_code = zipuk.upper()
						else:
							value = self.ukzipChecker.match(zipuk, city_uk.zip_code)
							print(f'self.ukzipChecker.match({zipuk}, {city_uk.zip_code}) => {value}')
							# raise Exception(f'Warning: uk zip NOT matched: {zipuk} in {city_uk.zip_code} for {city_uk.name} in "{text}"')
							return None
					else:
						print(f'Warning: UK zip {zipuk} found, but no city in "{text}"')

				# handle city
				if 'city' in match_dict:
					try:
						city_id = int(match_dict['city'])
						city_name = City.objects.get(id=city_id).name
						obj.city = city_name
						obj.city_id = city_id
					except City.DoesNotExist:
						print(f'Warning: City id {city_id} not found')
						return None
				elif 'zip' in match_dict:
					zip_code = match_dict['zip']
					city_id = self.cityTokenizer.city_id_by_zid(zip_code)
					if city_id is not None:
						city_name = self.cityTokenizer.city_by_id(city_id)
						unmapped_city_name = self.cityTokenizer.tokenize_city_name(city_name)  # map alternative name back to original
						obj.city = city_name if unmapped_city_name is None else unmapped_city_name
						obj.city_id = city_id

				# obj.country = city.country.name

				# handle ibd
				if 'ibd' in match_dict:
					ibd_id = int(match_dict['ibd'])
					# print(f'Found IBD: {ibd_id}')
					ibd = self._ibd_by_id(ibd_id)
					obj.ibd = ibd.name
					obj.ibd_id = ibd_id

					if obj.city is None and ibd.city is not None:
						obj.city = ibd.city.name

					if obj.street is None and ibd.street is not None:
						obj.street = ibd.street.name
						obj.street_id = ibd.street.id

					if obj.streetNumber is None and ibd.street_number is not None:
						obj.streetNumber = ibd.street_number

					if obj.zip_code is None and ibd.zip_code is not None:
						print(f'DEBUG: take over zip from ibd: {ibd.zip_code}')
						obj.zip_code = ibd.zip_code

				if verbose:
					print(f'Matched pattern {regex_index}', flush=True)

				return obj

		return None
import json
from io import BytesIO
from unittest.mock import patch

from django.test import TestCase, SimpleTestCase, override_settings
from django.urls import reverse

from geo.llm import AddressExtractionError, extract_address
from geo.models import (AlternativeCityName, AlternativeCountryName, AlternativeStreetName,
						City, Country, State, StreetName)


class GeocodeTests(TestCase):
	def setUp(self):
		patcher = patch('geo.views.extract_address', side_effect=self.extract_fixture)
		patcher.start()
		self.addCleanup(patcher.stop)

	@staticmethod
	def extract_fixture(text):
		# Simulate structured omlx output; the view must resolve names using tokenizers.
		parts = {key: '' for key in ('street', 'house_number', 'city', 'county',
		                            'state', 'country', 'postal_code')}
		for name in ('Unter den Linden', 'Linden Avenue', 'Market Street', 'No Coordinates'):
			if name in text:
				parts['street'] = name
				break
		for name in ('Berlin', 'Berlyn', 'Munich', 'Paris', 'Unknown', 'No Such City'):
			if name in text:
				parts['city'] = name
				break
		for name in ('Deutschland', 'Germany', 'France', 'DE'):
			if name in text.split(', ') or text.endswith(name):
				parts['country'] = name
		for name in ('Texas',):
			if name in text:
				parts['state'] = name
		for zip_code in ('10115', '80331', '99999'):
			if zip_code in text:
				parts['postal_code'] = zip_code
		return parts

	@classmethod
	def setUpTestData(cls):
		cls.germany = Country.objects.create(name='Germany', iso2='DE', zips_use_range=True)
		AlternativeCountryName.objects.create(country=cls.germany, name='Deutschland')
		cls.france = Country.objects.create(name='France')
		cls.berlin_state = State.objects.create(name='Berlin', country=cls.germany)
		cls.texas = State.objects.create(name='Texas', country=cls.germany)
		cls.berlin = City.objects.create(name='Berlin', country=cls.germany,
		                                 state=cls.berlin_state, zip_code='10115,10117', lat=52.52, lng=13.405)
		AlternativeCityName.objects.create(city=cls.berlin, name='Berlyn')
		cls.munich = City.objects.create(name='Munich', country=cls.germany,
		                                 zip_code='80000-80999', lat=48.137, lng=11.575)
		City.objects.create(name='Paris', country=cls.france, lat=48.8566, lng=2.3522)
		cls.unknown = City.objects.create(name='Unknown', country=cls.germany)
		cls.linden = StreetName.objects.create(name='Unter den Linden')
		cls.linden.cities.add(cls.berlin)
		AlternativeStreetName.objects.create(street=cls.linden, name='Linden Avenue')
		cls.shared = StreetName.objects.create(name='Market Street')
		cls.shared.cities.add(cls.berlin, cls.munich)
		StreetName.objects.create(name='No Coordinates').cities.add(cls.unknown)

	def lookup(self, text):
		return self.client.get(reverse('geocode'), {'text': text})

	def test_city_name_and_coordinates(self):
		response = self.lookup('Berlin')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()['results'], [{
			'city': 'Berlin', 'county': None, 'state': 'Berlin', 'country': 'Germany',
			'zip_code': '10115,10117', 'lat': 52.52, 'lng': 13.405,
		}])

	def test_alias_and_country(self):
		self.assertEqual(self.lookup('Berlyn, Deutschland').json()['results'][0]['city'], 'Berlin')
		self.assertEqual(self.lookup('Berlin, DE').json()['results'][0]['city'], 'Berlin')
		self.assertEqual(self.lookup('Berlin, France').json()['results'], [])
		self.assertEqual(self.lookup('Berlin, Texas').json()['results'], [])

	def test_postal_code(self):
		self.assertEqual(self.lookup('10115 Berlin, Germany').json()['results'][0]['city'], 'Berlin')
		self.assertEqual(self.lookup('80331 Munich').json()['results'][0]['city'], 'Munich')
		self.assertEqual(self.lookup('99999 Berlin').json()['results'], [])

	def test_no_match_or_coordinates(self):
		self.assertEqual(self.lookup('Unknown').json()['results'], [])
		self.assertEqual(self.lookup('No Such City').json()['results'], [])
		self.assertEqual(self.lookup('No Coordinates, Unknown').json()['results'], [])

	def test_street_and_alias_with_city(self):
		result = self.lookup('Unter den Linden 12, 10115 Berlin, Germany').json()['results']
		self.assertEqual(len(result), 1)
		self.assertEqual(result[0]['street'], 'Unter den Linden')
		self.assertEqual(result[0]['city'], 'Berlin')
		self.assertEqual((result[0]['lat'], result[0]['lng']), (52.52, 13.405))
		self.assertEqual(self.lookup('Linden Avenue, Berlyn').json()['results'][0]['street'],
		                 'Unter den Linden')

	def test_street_only_and_shared_street(self):
		self.assertEqual(self.lookup('Unter den Linden').json()['results'][0]['city'], 'Berlin')
		self.assertEqual({item['city'] for item in self.lookup('Market Street').json()['results']},
		                 {'Berlin', 'Munich'})
		self.assertEqual([item['city'] for item in self.lookup('Market Street, Munich').json()['results']],
		                 ['Munich'])

	def test_street_must_belong_to_requested_city_and_zip(self):
		self.assertEqual(self.lookup('Unter den Linden, Munich').json()['results'], [])
		self.assertEqual(self.lookup('Unter den Linden, Paris').json()['results'], [])
		self.assertEqual(self.lookup('Unter den Linden, Unknown').json()['results'], [])
		self.assertEqual(self.lookup('Unter den Linden, 99999 Berlin').json()['results'], [])
		self.assertEqual(self.lookup('Unter den Linden, Berlin, France').json()['results'], [])

	def test_invalid_input_and_method(self):
		self.assertEqual(self.client.get(reverse('geocode')).status_code, 400)
		self.assertEqual(self.lookup(' ' * 4).status_code, 400)
		self.assertEqual(self.lookup('x' * 256).status_code, 400)
		self.assertEqual(self.client.post(reverse('geocode'), {'text': 'Berlin'}).status_code, 405)

	def test_omlx_unavailable(self):
		with patch('geo.views.extract_address', side_effect=AddressExtractionError()):
			response = self.lookup('Berlin')
		self.assertEqual(response.status_code, 503)


@override_settings(OMLX_MODEL='test-model', OMLX_API_KEY='test-key',
				   OMLX_BASE_URL='http://localhost:8000/v1', OMLX_TIMEOUT=2)
class ExtractionTests(SimpleTestCase):
	def test_extract_address(self):
		response = {'choices': [{'message': {'content': json.dumps({'city': 'Berlin', 'street': 'Market Street'})}}]}
		with patch('geo.llm.urllib.request.urlopen', return_value=BytesIO(json.dumps(response).encode())) as send:
			parts = extract_address('Market Street, Berlin')
		self.assertEqual(parts['city'], 'Berlin')
		self.assertEqual(parts['postal_code'], '')
		request = send.call_args.args[0]
		self.assertEqual(request.full_url, 'http://localhost:8000/v1/chat/completions')
		self.assertEqual(request.get_header('Authorization'), 'Bearer test-key')
		self.assertEqual(json.loads(request.data)['model'], 'test-model')
		self.assertEqual(send.call_args.kwargs['timeout'], 2)

	def test_invalid_response(self):
		response = {'choices': [{'message': {'content': '{invalid'}}]}
		with patch('geo.llm.urllib.request.urlopen', return_value=BytesIO(json.dumps(response).encode())):
			with self.assertRaises(AddressExtractionError):
				extract_address('Berlin')



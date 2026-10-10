from django.test import TestCase
from django.urls import reverse

from geo.models import (AlternativeCityName, AlternativeCountryName, AlternativeStreetName,
						City, Country, State, StreetName)


class GeocodeTests(TestCase):
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

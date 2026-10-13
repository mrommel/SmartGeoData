"""Opt-in live omlx tests; run with RUN_OMLX_E2E=1 and OMLX_MODEL set."""
import os
from unittest import skipUnless

from django.conf import settings
from django.test import TestCase, override_settings, tag
from django.urls import reverse

from geo.models import City, Country, State, StreetName
from geo.tasks import _loaded
from geo.tests.test_geocode import finish_population


@tag('e2e')
@skipUnless(os.environ.get('RUN_OMLX_E2E') == '1', 'Set RUN_OMLX_E2E=1 to run against a live omlx server')
@override_settings(OMLX_TIMEOUT=120)
class LiveOmlxGeocodeTests(TestCase):
	"""Exercise HTTP -> real omlx -> tokenizers -> temporary database -> HTTP."""

	@classmethod
	def setUpTestData(cls):
		germany = Country.objects.create(name='Germany', iso2='DE')
		france = Country.objects.create(name='France', iso2='FR')
		usa = Country.objects.create(name='United States', iso2='US')
		berlin_state = State.objects.create(name='Berlin', country=germany)
		new_york_state = State.objects.create(name='New York', iso2='NY', country=usa)
		berlin = City.objects.create(name='Berlin', country=germany, state=berlin_state,
		                             zip_code='10117', lat=52.5200, lng=13.4050)
		paris = City.objects.create(name='Paris', country=france,
		                            zip_code='75007', lat=48.8566, lng=2.3522)
		new_york = City.objects.create(name='New York', country=usa, state=new_york_state,
		                               zip_code='10118', lat=40.7128, lng=-74.0060)
		for street_name, city in (('Unter den Linden', berlin),
		                          ('Avenue Anatole France', paris), ('5th Avenue', new_york)):
			StreetName.objects.create(name=street_name).cities.add(city)
		finish_population()

	def setUp(self):
		_loaded.clear()
		self.assertTrue(settings.OMLX_MODEL, 'Set OMLX_MODEL to a model served by omlx')

	def test_real_world_addresses(self):
		addresses = (
			('Unter den Linden 77, 10117 Berlin, Germany',
			 'Unter den Linden', 'Berlin', 'Germany', '10117', 52.5200, 13.4050),
			('Eiffel Tower, 5 Avenue Anatole France, 75007 Paris, France',
			 'Avenue Anatole France', 'Paris', 'France', '75007', 48.8566, 2.3522),
			('Empire State Building, 350 5th Avenue, New York, NY 10118, United States',
			 '5th Avenue', 'New York', 'United States', '10118', 40.7128, -74.0060),
		)
		for text, street, city, country, zip_code, lat, lng in addresses:
			with self.subTest(address=text):
				response = self.client.get(reverse('geocode'), {'text': text})
				self.assertEqual(response.status_code, 200, response.content)
				self.assertEqual(response.json()['results'], [{
					'street': street, 'city': city, 'county': None,
					'state': 'Berlin' if city == 'Berlin' else 'New York' if city == 'New York' else None,
					'country': country, 'zip_code': zip_code, 'lat': lat, 'lng': lng,
				}])


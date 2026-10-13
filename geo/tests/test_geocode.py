import json
import urllib.error
from io import BytesIO, StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, SimpleTestCase, override_settings
from django.urls import reverse
from django_tasks_db.models import DBTaskResult

from geo.llm import AddressExtractionError, extract_address
from geo.models import (AlternativeCityName, AlternativeCountryName, AlternativeStreetName,
						City, Country, State, StreetName)
from geo.tasks import POPULATION_TASKS, _loaded, start_population


def finish_population():
	"""Execute queued task bodies against the test database, storing worker results."""
	start_population()
	for population_task in POPULATION_TASKS.values():
		job = DBTaskResult.objects.filter(task_path=population_task.module_path).latest('enqueued_at')
		job.set_successful(population_task.call())


class GeocodePageTests(SimpleTestCase):
	def test_single_address_page(self):
		response = self.client.get(reverse('geocode-page'))
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'geo/geocode.html')
		self.assertContains(response, 'name="text"')
		self.assertContains(response, 'maxlength="255"')
		self.assertContains(response, reverse('geocode'))
		self.assertContains(response, f'href="{reverse("swagger-ui")}"')
		self.assertContains(response, f'href="{reverse("mcp-integration")}"')
		self.assertEqual(self.client.post(reverse('geocode-page')).status_code, 405)

	def test_mcp_integration_page(self):
		response = self.client.get(reverse('mcp-integration'))
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'geo/mcp_integration.html')
		self.assertContains(response, 'How to integrate geocoding MCP')
		self.assertContains(response, 'http://127.0.0.1:9113/mcp')
		self.assertContains(response, 'geocode_address(text)')
		self.assertContains(response, f'href="{reverse("geocode-page")}"')
		self.assertEqual(self.client.post(reverse('mcp-integration')).status_code, 405)


class GeocodeTests(TestCase):
	@staticmethod
	def extract_fixture(text):
		# Simulate structured omlx output; the view must resolve names using tokenizers.
		parts = {key: '' for key in ('street', 'house_number', 'city', 'county',
		                            'state', 'country', 'postal_code')}
		for name in ('Unter den Linden', 'Linden Avenue', 'Market Street', 'No Coordinates', 'Voorstraat', 'Uhlstr'):
			if name in text:
				parts['street'] = name
				break
		for name in ('Berlin', 'Berlyn', 'Munich', 'Paris', 'Unknown', 'No Such City', 'Woudenberg'):
			if name in text:
				parts['city'] = name
				break
		for name in ('Deutschland', 'Germany', 'France', 'Netherlands', 'DE'):
			if name in text.split(', ') or text.endswith(name):
				parts['country'] = name
		for name in ('Texas',):
			if name in text:
				parts['state'] = name
		for zip_code in ('10115', '80331', '99999', '3931HC', '50321', '68782'):
			if zip_code in text:
				parts['postal_code'] = zip_code
		return parts

	@classmethod
	def setUpTestData(cls):
		cls.germany = Country.objects.create(name='Germany', iso2='DE', zips_use_range=True)
		AlternativeCountryName.objects.create(country=cls.germany, name='Deutschland')
		cls.france = Country.objects.create(name='France')
		cls.netherlands = Country.objects.create(name='Netherlands', iso2='NL')
		cls.berlin_state = State.objects.create(name='Berlin', country=cls.germany)
		cls.texas = State.objects.create(name='Texas', country=cls.germany)
		cls.berlin = City.objects.create(name='Berlin', country=cls.germany,
		                                 state=cls.berlin_state, zip_code='10115,10117', lat=52.52, lng=13.405)
		AlternativeCityName.objects.create(city=cls.berlin, name='Berlyn')
		cls.munich = City.objects.create(name='Munich', country=cls.germany,
		                                 zip_code='80000-80999', lat=48.137, lng=11.575)
		cls.bruehl = City.objects.create(name='Brühl (Rheinland)', country=cls.germany,
		                                  zip_code='50321', lat=50.829, lng=6.904)
		cls.bruehl_baden = City.objects.create(name='Brühl (Baden)', country=cls.germany,
		                                        zip_code='68782', lat=49.396, lng=8.534)
		for city in (cls.bruehl, cls.bruehl_baden):
			AlternativeCityName.objects.create(city=city, name='Brühl', ambiguous=True)
		cls.woudenberg = City.objects.create(name='Woudenberg', country=cls.netherlands,
		                                     zip_code='3711,3931', lat=52.0821751, lng=5.4265952)
		City.objects.create(name='Paris', country=cls.france, lat=48.8566, lng=2.3522)
		cls.unknown = City.objects.create(name='Unknown', country=cls.germany)
		cls.linden = StreetName.objects.create(name='Unter den Linden')
		cls.linden.cities.add(cls.berlin)
		AlternativeStreetName.objects.create(street=cls.linden, name='Linden Avenue')
		cls.shared = StreetName.objects.create(name='Market Street')
		cls.shared.cities.add(cls.berlin, cls.munich)
		StreetName.objects.create(name='No Coordinates').cities.add(cls.unknown)
		StreetName.objects.create(name='Voorstraat').cities.add(cls.woudenberg)
		uhlstrasse = StreetName.objects.create(name='Uhlstraße')
		uhlstrasse.cities.add(cls.bruehl)
		AlternativeStreetName.objects.create(street=uhlstrasse, name='Uhlstr')
		StreetName.objects.create(name='Brühl').cities.add(cls.berlin, cls.bruehl)
		finish_population()

	def setUp(self):
		_loaded.clear()
		patcher = patch('geo.api.extract_address', side_effect=self.extract_fixture)
		patcher.start()
		self.addCleanup(patcher.stop)

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

	def test_dutch_postal_code_prefix(self):
		results = self.lookup('Voorstraat 53, 3931HC Woudenberg').json()['results']
		self.assertEqual(len(results), 1)
		self.assertEqual(results[0]['street'], 'Voorstraat')
		self.assertEqual(results[0]['street_number'], '53')
		self.assertEqual(results[0]['city'], 'Woudenberg')

	def test_zip_resolves_street_city_name_collision(self):
		with patch('geo.api.extract_address', side_effect=AssertionError('unexpected LLM fallback')):
			results = self.lookup('Uhlstr. 85-87, 50321 Brühl').json()['results']
		self.assertEqual(len(results), 1)
		self.assertEqual(results[0]['street'], 'Uhlstraße')
		self.assertEqual(results[0]['street_number'], '85-87')
		self.assertEqual(results[0]['city'], 'Brühl (Rheinland)')
		self.assertEqual(results[0]['zip_code'], '50321')

	def test_colliding_name_can_still_be_a_street(self):
		with patch('geo.api.extract_address', side_effect=AssertionError('unexpected LLM fallback')):
			results = self.lookup('Brühl 12, 10115 Berlin').json()['results']
			both = self.lookup('Brühl 12, 50321 Brühl').json()['results']
		self.assertEqual(results[0]['street'], 'Brühl')
		self.assertEqual(results[0]['street_number'], '12')
		self.assertEqual(results[0]['city'], 'Berlin')
		self.assertEqual(both[0]['street'], 'Brühl')
		self.assertEqual(both[0]['street_number'], '12')
		self.assertEqual(both[0]['city'], 'Brühl (Rheinland)')

	def test_direct_match_requires_matching_street_and_zip(self):
		self.assertEqual(self.lookup('Uhlstr. 85-87, 68782 Brühl').json()['results'], [])
		self.assertEqual(self.lookup('Uhlstr. 85-87, 50321 Berlin').json()['results'], [])

	def test_no_match_or_coordinates(self):
		self.assertEqual(self.lookup('Unknown').json()['results'], [])
		self.assertEqual(self.lookup('No Such City').json()['results'], [])
		self.assertEqual(self.lookup('No Coordinates, Unknown').json()['results'], [])

	def test_street_and_alias_with_city(self):
		result = self.lookup('Unter den Linden 12, 10115 Berlin, Germany').json()['results']
		self.assertEqual(len(result), 1)
		self.assertEqual(result[0]['street'], 'Unter den Linden')
		self.assertEqual(result[0]['street_number'], '12')
		self.assertEqual(result[0]['city'], 'Berlin')
		self.assertEqual((result[0]['lat'], result[0]['lng']), (52.52, 13.405))
		self.assertEqual(self.lookup('Linden Avenue, Berlyn').json()['results'][0]['street'],
		                 'Unter den Linden')
		self.assertNotIn('street_number', self.lookup('Linden Avenue, Berlyn').json()['results'][0])

	def test_fallback_returns_extracted_street_number(self):
		parts = {key: '' for key in ('street', 'house_number', 'city', 'county',
		                            'state', 'country', 'postal_code')}
		parts.update(street='Market Street', house_number='85-87')
		with patch('geo.api.extract_address', return_value=parts):
			results = self.lookup('Market Street 85-87').json()['results']
		self.assertEqual({item['city'] for item in results}, {'Berlin', 'Munich'})
		self.assertTrue(all(item['street_number'] == '85-87' for item in results))
		parts.update(street='', city='Berlin')
		with patch('geo.api.extract_address', return_value=parts):
			city_only = self.lookup('Berlin').json()['results'][0]
		self.assertNotIn('street_number', city_only)

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
		with patch('geo.api.extract_address', side_effect=AddressExtractionError()):
			response = self.lookup('Berlin')
		self.assertEqual(response.status_code, 503)


class TokenizerStatusTests(TestCase):
	def setUp(self):
		_loaded.clear()

	def status(self):
		return self.client.get(reverse('tokenizer-status'))

	def test_health_readiness(self):
		response = self.client.get(reverse('health'))
		self.assertEqual(response.status_code, 503)
		self.assertEqual(response.json(), {
			'status': 'unavailable', 'tokenizers': {'city': 'pending', 'street': 'pending'},
		})
		finish_population()
		response = self.client.get(reverse('health'))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json(), {
			'status': 'ready', 'tokenizers': {'city': 'completed', 'street': 'completed'},
		})
		self.assertEqual(self.client.post(reverse('health')).status_code, 405)

	def test_health_database_unavailable(self):
		with patch('geo.views.population_status', side_effect=RuntimeError('database offline')):
			response = self.client.get(reverse('health'))
		self.assertEqual(response.status_code, 503)
		self.assertEqual(response.json(), {'status': 'unavailable'})

	def test_startup_does_not_requeue_existing_or_failed_tasks(self):
		start_population()
		start_population()
		self.assertEqual(DBTaskResult.objects.count(), 2)
		city_task = DBTaskResult.objects.get(task_path=POPULATION_TASKS['city'].module_path)
		city_task.set_failed(ValueError('bad city'))
		start_population()
		self.assertEqual(DBTaskResult.objects.count(), 2)
		self.assertEqual(self.status().json()['status'], 'failed')

	def test_startup_only_queues_missing_task(self):
		POPULATION_TASKS['city'].enqueue()
		start_population()
		self.assertEqual(DBTaskResult.objects.count(), 2)
		self.assertEqual(DBTaskResult.objects.filter(task_path=POPULATION_TASKS['city'].module_path).count(), 1)
		self.assertEqual(DBTaskResult.objects.filter(task_path=POPULATION_TASKS['street'].module_path).count(), 1)

	def test_refresh_command_queues_new_pair(self):
		start_population()
		call_command('refresh_tokenizers', stdout=StringIO())
		self.assertEqual(DBTaskResult.objects.count(), 4)
		self.assertEqual(self.status().json()['status'], 'pending')

	def test_pending_running_completed_and_failed(self):
		self.assertEqual(self.status().json(), {
			'status': 'pending', 'tokenizers': {'city': 'pending', 'street': 'pending'},
		})
		self.assertEqual(self.client.get(reverse('geocode'), {'text': 'Berlin'}).status_code, 503)
		start_population()
		jobs = {name: DBTaskResult.objects.get(task_path=population_task.module_path)
		        for name, population_task in POPULATION_TASKS.items()}
		self.assertEqual(self.status().json()['status'], 'pending')
		jobs['city'].status = 'RUNNING'
		jobs['city'].save(update_fields=['status'])
		self.assertEqual(self.status().json(), {
			'status': 'running', 'tokenizers': {'city': 'running', 'street': 'pending'},
		})
		jobs['city'].set_successful({'city_dict': {}, 'country_dict': {}})
		self.assertEqual(self.status().json()['status'], 'pending')
		jobs['street'].set_failed(ValueError('bad street'))
		self.assertEqual(self.status().json(), {
			'status': 'failed', 'tokenizers': {'city': 'completed', 'street': 'failed'},
		})
		self.assertEqual(self.client.post(reverse('tokenizer-status')).status_code, 405)

	def test_successful_snapshots_and_new_startup(self):
		Country.objects.create(name='Germany')
		finish_population()
		self.assertEqual(self.status().json()['status'], 'completed')
		with patch('geo.tokenizer.CityTokenizer.populate', side_effect=AssertionError('synchronous populate')):
			with patch('geo.tokenizer.StreetTokenizer.populate', side_effect=AssertionError('synchronous populate')):
				from geo.tasks import get_tokenizers
				city, street = get_tokenizers()
				self.assertTrue(city.populated)
				self.assertTrue(street._populated)
				self.assertIn('germany', city.country_dict)
		start_population(force=True)
		self.assertEqual(self.status().json()['status'], 'pending')
		self.assertIsNone(get_tokenizers())


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

	def test_temporary_omlx_error_retries_once(self):
		response = {'choices': [{'message': {'content': '{"city": "Berlin"}'}}]}
		with patch('geo.llm.time.sleep') as sleep:
			with patch('geo.llm.urllib.request.urlopen', side_effect=[
				urllib.error.HTTPError('http://localhost:8000/v1/chat/completions', 503,
				                       'unavailable', {}, None),
				BytesIO(json.dumps(response).encode()),
			]) as send:
				self.assertEqual(extract_address('Berlin')['city'], 'Berlin')
		self.assertEqual(send.call_count, 2)
		sleep.assert_called_once()

	def test_unavailable_omlx_retries_only_once(self):
		with patch('geo.llm.time.sleep'):
			with patch('geo.llm.urllib.request.urlopen', side_effect=urllib.error.URLError('offline')) as send:
				with self.assertRaises(AddressExtractionError):
					extract_address('Berlin')
		self.assertEqual(send.call_count, 2)

	def test_permanent_omlx_error_is_not_retried(self):
		with patch('geo.llm.urllib.request.urlopen', side_effect=urllib.error.HTTPError(
			'http://localhost:8000/v1/chat/completions', 401, 'unauthorized', {}, None)) as send:
			with self.assertRaises(AddressExtractionError):
				extract_address('Berlin')
		self.assertEqual(send.call_count, 1)

	def test_invalid_response(self):
		response = {'choices': [{'message': {'content': '{invalid'}}]}
		with patch('geo.llm.urllib.request.urlopen', return_value=BytesIO(json.dumps(response).encode())) as send:
			with self.assertRaises(AddressExtractionError):
				extract_address('Berlin')
		self.assertEqual(send.call_count, 1)




import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from geo.admin_forms import CityForm, CountyForm, AlternativeCityNameForm
from geo.models import City, Country, County, State, StreetName


class AdminAutocompleteTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.staff = get_user_model().objects.create_superuser('staff', 'staff@example.com', 'test-password')
		cls.regular = get_user_model().objects.create_user('regular', 'regular@example.com', 'test-password')
		cls.country = Country.objects.create(name='Germany')
		cls.state = State.objects.create(name='Berlin', country=cls.country)
		cls.county = County.objects.create(name='Mitte', state=cls.state)
		City.objects.create(name='Berlin', country=cls.country, state=cls.state, county=cls.county)
		StreetName.objects.create(name='Unter den Linden')

	def test_admin_forms_render_select2_widgets(self):
		for form, fields in ((CityForm(), ('country', 'state', 'county')),
		                     (CountyForm(), ('state',)),
		                     (AlternativeCityNameForm(), ('city',))):
			for field in fields:
				with self.subTest(field=field):
					self.assertIn('data-autocomplete-light-url=', form[field].as_widget())

	def test_registered_admin_add_pages_render(self):
		self.client.force_login(self.staff)
		for model in ('city', 'county', 'alternativecityname'):
			with self.subTest(model=model):
				response = self.client.get(reverse(f'admin:geo_{model}_add'))
				self.assertEqual(response.status_code, 200)

	def test_autocomplete_requires_staff(self):
		url = reverse('city_autocomplete')
		self.assertEqual(self.client.get(url).status_code, 302)
		self.client.force_login(self.regular)
		self.assertEqual(self.client.get(url).status_code, 302)

	def test_autocomplete_search_and_forward(self):
		self.client.force_login(self.staff)
		for name, query in (('country_autocomplete', 'Germany'),
		                    ('state_autocomplete', 'Berlin'),
		                    ('county_autocomplete', 'Mitte'),
		                    ('city_autocomplete', 'Berlin'),
		                    ('street_name_autocomplete', 'Unter')):
			with self.subTest(name=name):
				response = self.client.get(reverse(name), {'q': query})
				self.assertEqual(response.status_code, 200)
				self.assertEqual(len(response.json()['results']), 1)
		response = self.client.get(reverse('county_autocomplete'),
		                           {'q': 'Mitte', 'forward': json.dumps({'state': self.state.pk})})
		self.assertEqual(len(response.json()['results']), 1)
		response = self.client.get(reverse('county_autocomplete'),
		                           {'q': 'Mitte', 'forward': json.dumps({'state': 999999})})
		self.assertEqual(response.json()['results'], [])


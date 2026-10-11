from django.test import SimpleTestCase
from django.urls import reverse


class OpenAPITests(SimpleTestCase):
	def test_schema_describes_public_api(self):
		response = self.client.get(reverse('openapi-schema'))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response['Content-Type'], 'application/json')
		spec = response.json()
		self.assertEqual(spec['openapi'], '3.0.3')
		self.assertEqual(set(spec['paths']), {reverse('geocode'), reverse('tokenizer-status')})
		geocode = spec['paths'][reverse('geocode')]['get']
		self.assertEqual(geocode['parameters'][0]['name'], 'text')
		self.assertTrue(geocode['parameters'][0]['required'])
		self.assertEqual(geocode['parameters'][0]['schema']['maxLength'], 255)
		self.assertEqual(set(geocode['responses']), {'200', '400', '503'})
		self.assertEqual(spec['components']['schemas']['GeocodeResult']['properties']['lat']['type'], 'number')
		self.assertEqual(set(spec['components']['schemas']['TokenizerStatus']['properties']['tokenizers']['required']),
		                 {'city', 'street'})
		self.assertEqual(self.client.post(reverse('openapi-schema')).status_code, 405)

	def test_swagger_ui_uses_local_schema(self):
		response = self.client.get(reverse('swagger-ui'))
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'geo/swagger.html')
		self.assertContains(response, 'swagger-ui-bundle.js')
		self.assertContains(response, reverse('openapi-schema'))
		self.assertEqual(self.client.post(reverse('swagger-ui')).status_code, 405)

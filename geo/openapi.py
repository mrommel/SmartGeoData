from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET


@require_GET
def openapi_schema(request):
	"""Describe the public geocoding API without changing its runtime behavior."""
	states = ['pending', 'running', 'completed', 'failed']
	spec = {
		'openapi': '3.0.3',
		'info': {
			'title': 'SmartGeoData API',
			'version': '1.0.0',
			'description': 'Resolve city and street addresses to city coordinates and check tokenizer readiness.',
		},
		'paths': {
			reverse('geocode'): {
				'get': {
					'summary': 'Geocode one address',
					'description': 'Returns at most 10 matching cities; coordinates are city-level, not house-level.',
					'parameters': [{
						'name': 'text', 'in': 'query', 'required': True,
						'description': 'City or street address (whitespace-only input is invalid).',
						'schema': {'type': 'string', 'minLength': 1, 'maxLength': 255},
						'example': 'Unter den Linden 12, 10115 Berlin, Germany',
					}],
					'responses': {
						'200': {
							'description': 'Matching cities, or an empty list if none match.',
							'content': {'application/json': {'schema': {'type': 'object',
								'required': ['results'], 'properties': {'results': {'type': 'array',
								'maxItems': 10, 'items': {'$ref': '#/components/schemas/GeocodeResult'}}}}}},
						},
						'400': {'description': 'Missing, blank, or overlong text.',
						        'content': {'application/json': {'schema': {'$ref': '#/components/schemas/Error'}}}},
						'503': {'description': 'Tokenizer population is incomplete or address extraction is unavailable.',
						        'content': {'application/json': {'schema': {'$ref': '#/components/schemas/Error'}}}},
					},
				},
			},
			reverse('tokenizer-status'): {
				'get': {
					'summary': 'Check tokenizer population status',
					'responses': {'200': {
						'description': 'Overall status and city/street tokenizer states.',
						'content': {'application/json': {'schema': {'$ref': '#/components/schemas/TokenizerStatus'}}},
					}},
				},
			},
			reverse('health'): {
				'get': {
					'summary': 'Check geocoding readiness',
					'description': 'Ready when city and street tokenizers have finished; does not probe the external omlx model.',
					'responses': {
						'200': {'description': 'Tokenizers are ready.',
						        'content': {'application/json': {'schema': {'$ref': '#/components/schemas/Health'}}}},
						'503': {'description': 'Tokenizers are not ready or the database is unavailable.',
						        'content': {'application/json': {'schema': {'$ref': '#/components/schemas/Health'}}}},
					},
				},
			},
		},
		'components': {'schemas': {
			'GeocodeResult': {
				'type': 'object',
				'required': ['city', 'county', 'state', 'country', 'zip_code', 'lat', 'lng'],
				'properties': {
					'street': {'type': 'string', 'description': 'Included only for street matches.'},
					'street_number': {'type': 'string', 'description': 'House number or range, when present with a street match.'},
					'city': {'type': 'string'},
					'county': {'type': 'string', 'nullable': True},
					'state': {'type': 'string', 'nullable': True},
					'country': {'type': 'string', 'nullable': True},
					'zip_code': {'type': 'string', 'nullable': True},
					'lat': {'type': 'number', 'format': 'double'},
					'lng': {'type': 'number', 'format': 'double'},
				},
			},
			'Error': {'type': 'object', 'required': ['error'], 'properties': {'error': {'type': 'string'}}},
			'TokenizerStatus': {
				'type': 'object', 'required': ['status', 'tokenizers'],
				'properties': {
					'status': {'type': 'string', 'enum': states},
					'tokenizers': {'$ref': '#/components/schemas/TokenizerStates'},
				},
			},
			'Health': {
				'type': 'object', 'required': ['status'],
				'properties': {
					'status': {'type': 'string', 'enum': ['ready', 'unavailable']},
					'tokenizers': {'$ref': '#/components/schemas/TokenizerStates'},
				},
			},
			'TokenizerStates': {
				'type': 'object', 'required': ['city', 'street'], 'properties': {
					'city': {'type': 'string', 'enum': states},
					'street': {'type': 'string', 'enum': states},
				},
			},
		}},
	}
	return JsonResponse(spec)


@require_GET
def swagger_ui(request):
	return render(request, 'geo/swagger.html')

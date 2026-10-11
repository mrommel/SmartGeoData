"""Extract address fields with an omlx OpenAI-compatible chat endpoint."""
import json
import urllib.error
import urllib.request

from django.conf import settings


class AddressExtractionError(Exception):
	pass


FIELDS = ('street', 'house_number', 'city', 'county', 'state', 'country', 'postal_code')


def extract_address(text):
	model = settings.OMLX_MODEL
	if not model:
		raise AddressExtractionError('OMLX_MODEL is not configured')
	url = settings.OMLX_BASE_URL.rstrip('/') + '/chat/completions'
	payload = {
		'model': model,
		'temperature': 0,
		'messages': [
			{'role': 'system', 'content': (
				'Extract only address components explicitly present in the user text. '
				'Return ONLY a JSON object with string or null fields: street, house_number, '
				'city, county, state, country, postal_code. Do not guess missing fields. '
				'Keep names and postal codes as written in the input.')},
			{'role': 'user', 'content': text},
		],
	}
	headers = {'Content-Type': 'application/json'}
	if settings.OMLX_API_KEY:
		headers['Authorization'] = f'Bearer {settings.OMLX_API_KEY}'
	request = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
	                                 headers=headers, method='POST')
	try:
		with urllib.request.urlopen(request, timeout=settings.OMLX_TIMEOUT) as response:
			data = json.load(response)
		content = data['choices'][0]['message']['content']
		if not isinstance(content, str):
			raise ValueError('Missing response content')
		# Some models wrap even requested JSON in a Markdown code fence.
		content = content.strip()
		if content.startswith('```') and content.endswith('```'):
			content = content.split('\n', 1)[-1].rsplit('```', 1)[0].strip()
		parts = json.loads(content)
		if not isinstance(parts, dict) or any(
			key in parts and parts[key] is not None and not isinstance(parts[key], str)
			for key in FIELDS
		):
			raise ValueError('Invalid address fields')
		return {key: (parts.get(key) or '').strip() for key in FIELDS}
	except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, IndexError, TypeError) as exc:
		raise AddressExtractionError('omlx address extraction failed') from exc

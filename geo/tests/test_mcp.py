import asyncio
import json
from email.message import Message
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from django.test import SimpleTestCase
from mcp.server.fastmcp.exceptions import ToolError
from starlette.testclient import TestClient

from geo.mcp_server import geocode_address, geocoding_health, main, mcp


class MCPTests(SimpleTestCase):
	def test_http_liveness_and_transport(self):
		with TestClient(mcp.streamable_http_app()) as client:
			response = client.get('/health')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json(), {'status': 'ok'})
		with patch('geo.mcp_server.mcp.run') as run:
			main(['--transport', 'streamable-http'])
			run.assert_called_once_with(transport='streamable-http')
		with patch('geo.mcp_server.mcp.run') as run:
			main([])
			run.assert_called_once_with(transport='stdio')

	def test_registered_geocode_tool(self):
		tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
		self.assertEqual(set(tools), {'geocode_address', 'geocoding_health'})
		self.assertEqual(tools['geocode_address'].inputSchema['required'], ['text'])
		address = 'Unter den Linden 12, Berlin & Germany'
		result = {'results': [{'city': 'Berlin', 'lat': 52.52, 'lng': 13.405}]}
		with patch('geo.mcp_server.urlopen', return_value=BytesIO(json.dumps(result).encode())) as send:
			content = asyncio.run(mcp.call_tool('geocode_address', {'text': address}))
		self.assertEqual(json.loads(content[0].text), result)
		self.assertEqual(send.call_args.args[0],
		                 'http://127.0.0.1:9112/api/geocode/?text=Unter+den+Linden+12%2C+Berlin+%26+Germany')
		self.assertEqual(send.call_args.kwargs['timeout'], 30)

	def test_health_reports_not_ready_without_raising(self):
		payload = {'status': 'unavailable', 'tokenizers': {'city': 'pending', 'street': 'running'}}
		error = HTTPError('http://localhost:9112/api/health/', 503, 'not ready', Message(),
		                  BytesIO(json.dumps(payload).encode()))
		with patch.dict('os.environ', {'SMARTGEODATA_API_URL': 'http://localhost:9112/'}):
			with patch('geo.mcp_server.urlopen', side_effect=error) as send:
				self.assertEqual(geocoding_health(), payload)
		self.assertEqual(send.call_args.args[0], 'http://localhost:9112/api/health/')

	def test_health_ready(self):
		payload = {'status': 'ready', 'tokenizers': {'city': 'completed', 'street': 'completed'}}
		with patch('geo.mcp_server.urlopen', return_value=BytesIO(json.dumps(payload).encode())):
			self.assertEqual(geocoding_health(), payload)

	def test_invalid_address_does_not_call_api(self):
		with patch('geo.mcp_server.urlopen') as send:
			for text in ('', '   ', 'x' * 256):
				with self.assertRaises(ToolError):
					geocode_address(text)
			send.assert_not_called()

	def test_service_errors_are_tool_errors(self):
		with patch('geo.mcp_server.urlopen', side_effect=URLError('offline')):
			with self.assertRaisesRegex(ToolError, 'Cannot reach'):
				geocode_address('Berlin')
		error = HTTPError('http://localhost/api/geocode/', 503, 'not ready', Message(),
		                  BytesIO(b'{"error":"Tokenizer unavailable"}'))
		with patch('geo.mcp_server.urlopen', side_effect=error):
			with self.assertRaisesRegex(ToolError, 'HTTP 503: Tokenizer unavailable'):
				geocode_address('Berlin')


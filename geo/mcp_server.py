"""MCP tools for a running SmartGeoData web server (no Django startup required)."""
import argparse
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from starlette.responses import JSONResponse


mcp = FastMCP('SmartGeoData', host=os.environ.get('SMARTGEODATA_MCP_HOST', '127.0.0.1'),
	          port=int(os.environ.get('SMARTGEODATA_MCP_PORT', '9113')), stateless_http=True, json_response=True)


@mcp.custom_route('/health', methods=['GET'])
async def mcp_health(request):
	"""Report that the MCP HTTP process is running; Django readiness is a separate check."""
	return JSONResponse({'status': 'ok'})


def _get_json(path, *, params=None, allow_unavailable=False):
	base_url = os.environ.get('SMARTGEODATA_API_URL', 'http://127.0.0.1:9112').rstrip('/')
	url = base_url + path
	if params:
		url += '?' + urlencode(params)
	try:
		with urlopen(url, timeout=30) as response:
			data = json.load(response)
	except HTTPError as exc:
		if allow_unavailable and exc.code == 503:
			try:
				data = json.load(exc)
			except (ValueError, UnicodeError) as error:
				raise ToolError('Geocoding service returned invalid health data') from error
		else:
			try:
				message = json.load(exc).get('error', '')
			except (ValueError, UnicodeError, AttributeError):
				message = ''
			raise ToolError(f'Geocoding service returned HTTP {exc.code}: {message}'.rstrip(': ')) from exc
	except (URLError, TimeoutError) as exc:
		raise ToolError(f'Cannot reach the geocoding service: {exc}') from exc
	except (ValueError, UnicodeError) as exc:
		raise ToolError('Geocoding service returned invalid JSON') from exc
	if not isinstance(data, dict):
		raise ToolError('Geocoding service returned an invalid response')
	return data


@mcp.tool()
def geocode_address(text: str) -> dict:
	"""Find up to 10 matching cities for an address; coordinates are city-level, not house-level."""
	if not isinstance(text, str) or not text.strip() or len(text) > 255:
		raise ToolError('Address text must be between 1 and 255 characters and not blank')
	return _get_json('/api/geocode/', params={'text': text})


@mcp.tool()
def geocoding_health() -> dict:
	"""Check whether the geocoding tokenizers are ready (or report their current states)."""
	return _get_json('/api/health/', allow_unavailable=True)


def main(argv=None):
	parser = argparse.ArgumentParser(description='Serve SmartGeoData tools over MCP')
	parser.add_argument('--transport', choices=('stdio', 'streamable-http'), default='stdio')
	args = parser.parse_args(argv)
	mcp.run(transport=args.transport)


if __name__ == '__main__':
	main()

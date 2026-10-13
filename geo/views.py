from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from geo.tasks import population_status


@require_GET
def geocode_page(request):
	"""Display the single-address geocoding form."""
	return render(request, 'geo/geocode.html')


@require_GET
def mcp_integration_page(request):
	"""Explain how to connect an MCP client to SmartGeoData."""
	return render(request, 'geo/mcp_integration.html')


@require_GET
def tokenizer_status(request):
	return JsonResponse(population_status())


@require_GET
def health(request):
	"""Report whether the geocoding tokenizers are ready to serve requests."""
	try:
		population = population_status()
	except Exception:
		return JsonResponse({'status': 'unavailable'}, status=503)
	ready = population['status'] == 'completed'
	return JsonResponse({
		'status': 'ready' if ready else 'unavailable',
		'tokenizers': population['tokenizers'],
	}, status=200 if ready else 503)


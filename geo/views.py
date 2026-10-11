from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from geo.tasks import population_status


@require_GET
def geocode_page(request):
	"""Display the single-address geocoding form."""
	return render(request, 'geo/geocode.html')


@require_GET
def tokenizer_status(request):
	return JsonResponse(population_status())


from dal import autocomplete

from geo.models import Country, County, State


class GeoAutocomplete(autocomplete.Select2QuerySetView):
	"""Search a configured geo model, narrowing choices by forwarded form fields."""

	def get_queryset(self):
		queryset = super().get_queryset().order_by('name', 'pk')
		country = self.forwarded.get('country')
		state = self.forwarded.get('state')
		county = self.forwarded.get('county')
		if self.model is County:
			if state and str(state).isdigit():
				queryset = queryset.filter(state_id=state)
			elif country and str(country).isdigit():
				queryset = queryset.filter(state__country_id=country)
		elif self.model is State:
			if county and str(county).isdigit():
				queryset = queryset.filter(county__pk=county)
			elif country and str(country).isdigit():
				queryset = queryset.filter(country_id=country)
		elif self.model is Country and state and str(state).isdigit():
			queryset = queryset.filter(state__pk=state)
		return queryset

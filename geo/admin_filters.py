from django.contrib import admin
from django.db.models import Q, Count
from django.utils.translation import gettext_lazy as _

from geo.models import City, State



class IgnoreFilter(admin.SimpleListFilter):
	# Human-readable title which will be displayed in the
	# right admin sidebar just above the filter options.
	title = _('Ignore')

	# Parameter for the filter that will be used in the URL query.
	parameter_name = 'ignore'

	def lookups(self, request, model_admin):
		return (
			('ignore', _('Ignore')),
			('use', _('Use')),
		)

	def queryset(self, request, queryset):
		if self.value() == 'ignore':
			return queryset.filter(ignore=True)
		elif self.value() == 'use':
			return queryset.filter(ignore=False)

		return queryset


class StateCountryFilter(admin.SimpleListFilter):
	# Human-readable title which will be displayed in the
	# right admin sidebar just above the filter options.
	title = _('Country')

	# Parameter for the filter that will be used in the URL query.
	parameter_name = 'country'

	def lookups(self, request, model_admin):
		country_dict = dict()
		flag_dict = dict()
		not_set = 0

		stateQs = State.objects.all() \
			.values('country__name', 'country__emoji')

		for state in stateQs:
			country_name = state['country__name']
			country_emoji = state['country__emoji']
			if country_name is not None:
				country_dict[country_name] = country_dict.get(country_name, 0) + 1
				flag_dict[country_name] = country_emoji
			else:
				not_set += 1

		val = list()
		for key, value in country_dict.items():
			val.append((key, f'{flag_dict[key]} {key} ({value:,})'))

		val.append(('empty', f'<EMPTY> ({not_set:,})'))

		return val

	def queryset(self, request, queryset):
		if self.value() == 'empty':
			return queryset.filter(country=None)

		if self.value() is not None:
			return queryset.filter(country__name=self.value())

		return queryset


class CityCountryFilter(admin.SimpleListFilter):
	title = _('Country')

	parameter_name = 'country'	# Parameter for the filter that will be used in the URL query.

	def lookups(self, request, model_admin):
		country_dict = dict()
		flag_dict = dict()
		not_set = 0

		cityQs = City.objects.all() \
			.values('country__name', 'country__emoji')

		for city in cityQs:
			country_name = city['country__name']
			country_emoji = city['country__emoji']
			if country_name is not None:
				country_dict[country_name] = country_dict.get(country_name, 0) + 1
				flag_dict[country_name] = country_emoji
			else:
				not_set += 1

		val = list()
		for key, value in country_dict.items():
			val.append((key, f'{flag_dict[key]} {key} ({value:,})'))

		val.append(('empty', f'<EMPTY> ({not_set:,})'))

		return val

	def queryset(self, request, queryset):
		if self.value() == 'empty':
			return queryset.filter(country=None)

		if self.value() is not None:
			return queryset.filter(country__name=self.value())

		return queryset


class CityZipFilter(admin.SimpleListFilter):
	title = _('Zip')

	parameter_name = 'zip'  # Parameter for the filter that will be used in the URL query.

	def lookups(self, request, model_admin):
		val = list()

		num_has_zip = City.objects.filter(Q(zip_code__isnull=False) & ~Q(zip_code='')).count()
		val.append(('has_zip', _(f'Has Zip ({num_has_zip:,})')))
		num_no_zip = City.objects.filter(Q(zip_code__isnull=True) | Q(zip_code='')).count()
		val.append(('no_zip', _(f'No Zip ({num_no_zip:,})')))

		return val

	def queryset(self, request, queryset):
		if self.value() == 'has_zip':
			return queryset.filter(Q(zip_code__isnull=False) & ~Q(zip_code=''))

		if self.value() == 'no_zip':
			return queryset.filter(Q(zip_code__isnull=True) | Q(zip_code=''))

		return queryset


class CityLocationFilter(admin.SimpleListFilter):
	title = _('Geo')

	parameter_name = 'geo'  # Parameter for the filter that will be used in the URL query.

	def lookups(self, request, model_admin):
		val = list()

		num_has_geo = City.objects.filter(Q(lat__isnull=False) & ~Q(lat=0.0)).count()
		val.append(('has_geo', _(f'Has Geo ({num_has_geo:,})')))
		num_no_geo = City.objects.filter(Q(lat__isnull=True) | Q(lat=0.0)).count()
		val.append(('no_geo', _(f'No Geo ({num_no_geo:,})')))

		return val

	def queryset(self, request, queryset):
		if self.value() == 'has_geo':
			return queryset.filter(Q(lat__isnull=False) & ~Q(lat=0.0))

		if self.value() == 'no_geo':
			return queryset.filter(Q(lat__isnull=True) | Q(lat=0.0))

		return queryset


class EnabledFilter(admin.SimpleListFilter):
	# Human-readable title which will be displayed in the
	# right admin sidebar just above the filter options.
	title = _('Enabled')

	# Parameter for the filter that will be used in the URL query.
	parameter_name = 'enabled'

	def lookups(self, request, model_admin):
		return (
			('enabled', _('Enabled')),
			('disabled', _('Disabled')),
		)

	def queryset(self, request, queryset):
		if self.value() == 'enabled':
			return queryset.filter(enabled=True)
		elif self.value() == 'disabled':
			return queryset.filter(enabled=False)

		return queryset


class AmbiguousFilter(admin.SimpleListFilter):
	# Human-readable title which will be displayed in the
	# right admin sidebar just above the filter options.
	title = _('Ambiguous')

	# Parameter for the filter that will be used in the URL query.
	parameter_name = 'ambiguous'

	def lookups(self, request, model_admin):
		return (
			('ambiguous', _('Ambiguous')),
			('non_ambiguous', _('Non Ambiguous')),
		)

	def queryset(self, request, queryset):
		if self.value() == 'ambiguous':
			return queryset.filter(ambiguous=True)
		elif self.value() == 'non_ambiguous':
			return queryset.filter(ambiguous=False)

		return queryset


class IBDImportStreetFilter(admin.SimpleListFilter):
	# Human-readable title which will be displayed in the
	# right admin sidebar just above the filter options.
	title = _('has_street')

	# Parameter for the filter that will be used in the URL query.
	parameter_name = 'has_street'

	def lookups(self, request, model_admin):
		qs = model_admin.get_queryset(request)
		numHasStreet = qs.filter(street__isnull=False).count()
		numNoStreet = qs.filter(street__isnull=True).count()

		return (
			('has_street', _('Has Street ({:,})'.format(numHasStreet))),
			('no_street', _('No Street ({:,})'.format(numNoStreet))),
		)

	def queryset(self, request, queryset):
		if self.value() == 'has_street':
			return queryset.filter(street__isnull=False)
		elif self.value() == 'no_street':
			return queryset.filter(street__isnull=True)

		return queryset


class IBDImportCityFilter(admin.SimpleListFilter):
	# Human-readable title which will be displayed in the
	# right admin sidebar just above the filter options.
	title = _('has_city')

	# Parameter for the filter that will be used in the URL query.
	parameter_name = 'has_city'

	def lookups(self, request, model_admin):
		qs = model_admin.get_queryset(request)
		numHasCity = qs.filter(city__isnull=False).count()
		numNoCity = qs.filter(city__isnull=True).count()

		return (
			('has_city', _('Has City ({:,})'.format(numHasCity))),
			('no_city', _('No City ({:,})'.format(numNoCity))),
		)

	def queryset(self, request, queryset):
		if self.value() == 'has_city':
			return queryset.filter(city__isnull=False)
		elif self.value() == 'no_city':
			return queryset.filter(city__isnull=True)

		return queryset

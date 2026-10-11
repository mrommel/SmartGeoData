from dal import autocomplete
from django import forms
from django.contrib import admin
from django.db.models import Subquery, OuterRef, Func, F
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django_admin_inline_paginator.admin import TabularInlinePaginated
from geo.admin_filters import EnabledFilter, AmbiguousFilter, \
	CityCountryFilter, CityZipFilter, \
	StateCountryFilter, CityLocationFilter
from geo.constants import AddressRegex

from geo.models import Country, State, County, City, \
	AlternativeCityName, \
	AlternativeCountryName, AlternativeStreetName, \
	StreetName, StreetCityMembership, _clean_string
# from geo.tokenizer import AddressPatternTokenizer, AddressObject, BikeModelTokenizer, BikeModelParser


class ListStyleAdminMixin(object):
	def row_css(self, obj, index):
		return ''


class StateInline(admin.TabularInline):
	model = State
	fk_name = "country"
	extra = 0
	# can_delete = False
	readonly_fields = ['admin_link', 'alternative_names', 'iso2', 'counties_list']
	fields = [
		'admin_link', 'alternative_names', 'iso2', 'counties_list'
	]

	def counties_list(self, obj):
		return ", ".join(obj.county_list())


class AlternativeCountryNameInline(admin.TabularInline):
	model = AlternativeCountryName

	extra = 1


class CountryAdmin(admin.ModelAdmin):
	model = Country

	search_fields = [
		'name',
	]
	list_display = [
		'admin_link',
		'iso3',
		'iso2',
		'currency',
		'zips_use_range'
	]
	fields = [
		'name',
		'emoji',
		'iso3',
		'iso2',
		'currency',
		'zips_use_range'
	]
	readonly_fields = [
		'admin_link'
	]
	inlines = [
		AlternativeCountryNameInline,
		StateInline,
	]


class AlternativeCountryNameAdmin(admin.ModelAdmin):
	model = AlternativeCountryName

	search_fields = [
		'name'
	]
	list_display = [
		'name',
	]


class StateAdmin(admin.ModelAdmin):
	model = State

	search_fields = [
		'name',
		'alternative_names'
	]
	list_display = [
		'name',
		'iso2',
		'country',
		'admin_county_list'
	]
	readonly_fields = [
		'admin_county_list'
	]
	list_filter = [
		StateCountryFilter,
	]

	def formfield_for_foreignkey(self, db_field, request, **kwargs):
		# print(db_field.name)
		if db_field.name == "country":
			kwargs["queryset"] = Country.objects.order_by('name')

		return super().formfield_for_foreignkey(db_field, request, **kwargs)


class CityInline(admin.TabularInline):
	model = City
	fk_name = 'county'
	extra = 0
	can_delete = False

	fields = [
		'admin_link',
		'name',
		'zip_code',
	]
	readonly_fields = [
		'admin_link',
		'name',
		'zip_code',
	]

	def has_add_permission(self, request, obj):
		return False


class CountyForm(forms.ModelForm):
	state = forms.ModelChoiceField(
		queryset=State.objects.all(),
		widget=autocomplete.ModelSelect2(
			url='state_autocomplete',
			forward=['county'],
			attrs={
				'class': 'form-control',
				"data-placeholder": _('Choose a State ...'),
				"data-width": None
			},
		),
		required=False
	)

	class Meta:
		model = County
		fields = "__all__"


class CountyAdmin(admin.ModelAdmin):
	model = County
	form = CountyForm

	search_fields = [
		'name',
		'alternative_names'
	]
	list_display = [
		'name',
		'state',
		'num_cities',
		# 'city_list'
	]
	readonly_fields = [
		'num_cities',
		# 'city_list'
	]
	inlines = [
		CityInline
	]

	def get_inlines(self, request, obj):
		"""Hook for specifying custom inlines."""
		if obj is None:
			return []

		return self.inlines

	def formfield_for_foreignkey(self, db_field, request, **kwargs):
		# print(db_field.name)
		if db_field.name == "state":
			kwargs["queryset"] = State.objects.order_by('name')

		return super().formfield_for_foreignkey(db_field, request, **kwargs)


# https://stackoverflow.com/questions/74736218/how-to-filter-dropdown-choices-based-on-the-value-of-another-dropdown-in-django
class CityForm(forms.ModelForm):
	county = forms.ModelChoiceField(
		queryset=County.objects.all(),
		widget=autocomplete.ModelSelect2(
			url='county_autocomplete',
			forward=['country', 'state'],
			attrs={
				'class': 'form-control',
				"data-placeholder": _('Choose a County ...'),
				"data-width": None
			},
		),
		required=False,
	)
	state = forms.ModelChoiceField(
		queryset=State.objects.all(),
		widget=autocomplete.ModelSelect2(
			url='state_autocomplete',
			forward=['county', 'country'],
			attrs={
				'class': 'form-control',
				"data-placeholder": _('Choose a State ...'),
				"data-width": None
			},
		),
		required=False
	)
	country = forms.ModelChoiceField(
		queryset=Country.objects.all(),
		widget=autocomplete.ModelSelect2(
			url='country_autocomplete',
			forward=['state'],
			attrs={
				'class': 'form-control',
				"data-placeholder": _('Choose a Country ...'),
				"data-width": None
			},
		),
	)

	class Meta:
		model = City
		fields = [
			'name',
			'zip_code',
			'county',
			'state',
			'country',
			'lat',
			'lng'
		]  # "__all__"


class AlternativeCityNameInline(admin.TabularInline):
	model = AlternativeCityName

	extra = 1


class AlternativeCityNameForm(forms.ModelForm):
	city = forms.ModelChoiceField(
		queryset=City.objects.all(),
		widget=autocomplete.ModelSelect2(
			url='city_autocomplete',
			attrs={
				'class': 'form-control',
				"data-placeholder": _('Choose a City ...'),
				"data-width": None
			},
		),
		required=False
	)

	class Meta:
		model = AlternativeCityName
		fields = '__all__'


class AlternativeCityNameAdmin(admin.ModelAdmin):
	model = AlternativeCityName
	form = AlternativeCityNameForm

	search_fields = [
		'name'
	]
	list_display = [
		'name',
		'city',
		'ambiguous',
		'need_zip',
	]
	list_filter = [
		AmbiguousFilter,
	]
	fields = [
		'name',
		'city',
		'city_link',
		'ambiguous',
		'need_zip',
	]
	readonly_fields = [
		'city_link',
	]

	def city_link(self, obj):
		if obj.city is None:
			return '-'

		return obj.city.admin_link()
	city_link.allow_tags = True


class AlternativeStreetNameInline(TabularInlinePaginated):
	model = AlternativeStreetName
	per_page = 10
	extra = 1
	# can_delete = False
	ordering = ('name',)


class CityInlineForm(forms.ModelForm):
	city = forms.ModelChoiceField(
		queryset=City.objects.all(),
		widget=autocomplete.ModelSelect2(
			url='city_autocomplete',
			attrs={
				'class': 'form-control',
				"data-placeholder": _('Choose a City ...'),
				"data-width": None
			},
		),
		required=False
	)

	class Meta:
		fields = "__all__"


class StreetNameInlineForm(forms.ModelForm):
	street = forms.ModelChoiceField(
		queryset=StreetName.objects.all(),
		widget=autocomplete.ModelSelect2(
			url='street_name_autocomplete',
			attrs={
				'class': 'form-control',
				"data-placeholder": _('Choose a Street ...'),
				"data-width": None
			},
		),
		required=True
	)

	class Meta:
		fields = ('street', )


class StreetCitiesInline(TabularInlinePaginated):
	model = StreetName.cities.through
	form = CityInlineForm
	extra = 1
	per_page = 10
	ordering = ('street_name',)


class CityStreetInline(TabularInlinePaginated):
	model = StreetName.cities.through
	extra = 0
	per_page = 10
	ordering = ('street_name', )

	readonly_fields = [
		'street_name',
	]

	can_delete = False

	def has_add_permission(self, request, obj):
		return False


class StreetNameAdmin(admin.ModelAdmin):
	model = StreetName
	list_display = [
		'name',
		'cities_list',
		'alternative_names_count'
	]
	readonly_fields = [
		'cities_list',
		'alternative_names_count',
	]
	search_fields = [
		'name',
	]
	exclude = [
		"cities"
	]
	inlines = [
		AlternativeStreetNameInline,
		StreetCitiesInline,
	]

	# def get_ordering(self, request):
	#	return [Lower('name')]  # sort case-insensitive

	def cities_list(self, obj):
		city_names = []

		for membership in StreetCityMembership.objects.filter(street_name=obj).order_by('city__name'):
			city_names.append(membership.city.admin_link())

		return mark_safe(', '.join(city_names))

	cities_list.allow_tags = True

	def alternative_names_count(self, obj):
		return len(obj.alternative_city_names())


class AlternativeStreetNameForm(forms.ModelForm):
	street = forms.ModelChoiceField(
		queryset=StreetName.objects.all(),
		widget=autocomplete.ModelSelect2(
			url='street_name_autocomplete',
			attrs={
				'class': 'form-control',
				"data-placeholder": _('Choose a Street ...'),
				"data-width": None
			},
		),
		required=True
	)

	class Meta:
		fields = ('street', 'name', )


class AlternativeStreetNameAdmin(admin.ModelAdmin):
	model = AlternativeStreetName
	form = AlternativeStreetNameForm

	fields = [
		'street', 'street_link', 'name',
	]
	readonly_fields = [
		'street_link',
	]

	search_fields = [
		'name',
	]

	def street_link(self, object):
		return object.street.admin_link()


class CityAdmin(admin.ModelAdmin):
	model = City
	form = CityForm

	search_fields = [
		'name', 'zip_code'
	]
	list_display = [
		'name',
		'tagging',
		'zip_code',
		'county',
		'state',
		'country_admin_link',
		'customer_invoices_count',
		'ibd_invoices_count',
		'street_count',
		'alternative_names_count'
	]
	readonly_fields = [
		'country_admin_link',
		'customer_invoices_count',
		'ibd_invoices_count',
		'alternative_names_count',
		'street_count',
		# 'lng',
		# 'lat',
		'tagging'
	]
	exclude = ['tagging', ]
	inlines = [
		AlternativeCityNameInline,
		CityStreetInline,
	]
	list_filter = [
		CityZipFilter,
		CityLocationFilter,
		CityCountryFilter,
	]
	change_list_template = "admin/change_list_quick.html"

	def customer_invoices_count(self, obj):
		return 0 # obj.customer_invoices_count

	def ibd_invoices_count(self, obj):
		"""
		Get the number of invoices, where the ibd city is this city

		@param obj: city to get the number of invoices from
		@return: number of invoices
		"""
		return 0 # obj.ibd_invoices_count

	def street_count(self, obj):
		return obj.street_count

	def alternative_names_count(self, obj):
		return len(obj.alternative_city_names())

	def alternative_names_count(self, obj):
		return len(obj.alternative_city_names())

	def get_queryset(self, request):
		queryset = super().get_queryset(request)
		queryset = queryset.annotate(
			street_count=Subquery(
				StreetCityMembership.objects.filter(city_id=OuterRef('pk'))
				.values("pk")
				.annotate(value=Func(F('pk'), function='Count'))
				.values("value")
			)
		)
		return queryset

	def get_inlines(self, request, obj):
		"""Hook for specifying custom inlines."""
		if obj is None:
			return [AlternativeCityNameInline, ]

		return self.inlines

	def formfield_for_foreignkey(self, db_field, request, **kwargs):
		# print(db_field.name)
		if db_field.name == "country":
			kwargs["queryset"] = Country.objects.order_by('name')

		if db_field.name == "state":
			kwargs["queryset"] = State.objects.order_by('name')

		if db_field.name == "county":
			kwargs["queryset"] = County.objects.order_by('name')

		return super().formfield_for_foreignkey(db_field, request, **kwargs)

	def tagging(self, city) -> str:
		if city is None:
			return '-'
		# get us and cn country ids
		country_cn_id = None
		country_us_id = None
		country_aus_id = None
		for country in Country.objects.filter(name__in=['United States', 'Canada', 'Australia']).values('id', 'name'):
			country_name = _clean_string(country['name'])
			if country_name == 'united states':
				country_us_id = country['id']
			elif country_name == 'canada':
				country_cn_id = country['id']
			elif country_name == 'australia':
				country_aus_id = country['id']

		has_alt_state_name = None  # city.ibd is not None
		has_state_alternative = False
		for alternative_city in city.alternative_city_names():
			# check us, can or aus cities for alternative names with state
			if city.country_id is not None and city.country_id in [country_cn_id, country_us_id, country_aus_id]:
				if city.state is None:
					print(f'WARNING: {city.name} has no state')
				elif city.state.iso2 is None:
					print(f'WARNING: {city.state.name} has no iso2')
				else:
					state_iso = ' ' + city.state.iso2.lower()
					if alternative_city.name.lower().endswith(state_iso):
						has_state_alternative = True

		if city.country_id is not None and city.country_id in [country_cn_id, country_us_id, country_aus_id]:
			has_alt_state_name = has_state_alternative

		# 🌐❌
		# 🏛️❌➖
		geo_emoji = '🌐' if city.lng is not None else '❌'

		if has_alt_state_name is None:
			state_emoji = '➖'
		elif has_alt_state_name:
			state_emoji = '🏛'
		else:
			state_emoji = '❌'

		return mark_safe(geo_emoji + '&nbsp;' + state_emoji)

	tagging.short_description = '🌐 🏛'
	tagging.allow_tags = True

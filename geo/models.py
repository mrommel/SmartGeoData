import warnings
from tkinter import Image
from typing import List

from django.db import models
from django.db.models import QuerySet, Exists, Q, OuterRef
from django.utils.safestring import mark_safe, SafeString
from django.utils.translation import gettext_lazy as _
from PIL import Image
from django.core.exceptions import ValidationError

from geo.utils import _clean_string

warnings.filterwarnings('ignore', category=UserWarning, message='TypedStorage is deprecated')
warnings.simplefilter('ignore', Image.DecompressionBombWarning)


class Currency(models.TextChoices):
	"""Currency choices stored on countries, with helpers for parsing and symbols."""

	# https://de.wikipedia.org/wiki/ISO_4217
	UNKNOWN = 'UN', _('Unknown')

	EURO = 'EU', _('Euro')
	FRANKEN = 'FR', _('Franken')
	DOLLAR = 'DO', _('Dollar')
	POUND = 'PO', _('Pound')
	LEI = 'LE', _('Lei')
	ZLOTY = 'ZL', _('Złoty')
	CZK = 'CZ', _('Czech koruna')
	DKK = 'DK', _('Danish krone')
	NOK = 'NK', _('Norwegian krone')
	SEK = 'SE', _('Swedish Krona')
	NZD = 'NZ', _('New Zealand Dollar')
	AUD = 'AU', _('Australian Dollar')
	CAD = 'CA', _('Canadian Dollar')
	ISK = 'IS', _('Icelandic Króna')
	SKK = 'SK', _('Slovak koruna')
	YEN = 'YN', _('Japanese Yen')
	HRK = 'HR', _('Croatian Kuna')
	AED = 'AE', _('UAE Dirham')
	FORINT = 'FO', _('Forint')
	BGN = 'BG', _('Bulgarian Lev')

	@classmethod
	def from_name(cls, name: str) -> 'Currency':
		if name in [
			'EU', 'EUR', '€', 'Euro', 'EURO', 'EUR (inkl. MwSt)', 'eur', 'EUROS', 'Eur', '{EUR}', '€uros',
			'Nederlandse Gulden (€)', 'EU!', 'EURO (€)', 'Euro (€)', '€ (Euro)', 'BTW or: €', 'euros',
			'Euro (€)', 'Euros', 'Do not know the currency, but it seems to be euros (€)', 'Some currency (€)',
			'<eur', 'E€', '{€}', 'EuR', 'eur (inkl. mwst)', 'euro', 'Nederland', 'EUR (inkl. MWST)', '€ (EUR)',
			'EUR (assuming from Germany)', 'EUR (assumed based on context, as it is a German company)',
			'Assumed EUR (Germany context)', 'EUR, as the invoice is from Germany',
			'not specified in the provided text, but assuming EUR as it is a German document',
			'EUR (assumed based on German context)', 'Not detected, assuming EUR (Germany context)',
			'EUR (assumed based on context, as it is a German invoice)',
			'Not specified in the provided invoice text. Assuming EUR as it is a common currency for European countries.',
			'EUR (assumed based on context as it is a German company)',
			'EUR (assumed based on the context of the invoice being from Germany)',
			'EUR (assumed based on the country of origin Germany)',
			'Assumed EUR (based on common international format for dates)',
			'EUR (assumed based on the context as it is a German document)',
			'EUR (assumed based on the country code +49)',
			'Not specified in the provided invoice text. Assuming EUR as it\'s a common currency for German companies.',
			'Not specified in the provided invoice, but assuming EUR as it is a common currency for Germany',
			'EUR (assumed due to the country code in phone number)',
			'EUR (assumed from context as it is a German company)', 'EUR (assumed due to the invoice being from Germany)',
			'Based on the context that the invoice is from Germany, it can be assumed that the currency is EUR.',
			'Assumed EUR (based on the context that it\'s an invoice from Germany)',
			'Not detected in the provided invoice text. Assuming EUR as it is a Dutch invoice.',
			'EUR (based on the context of the invoice being from France)',
			"EUR (assuming from context as it is a German company name 'Schwalbe' which is a well-known German bicycle tire manufacturer)",
			'EUR (assumed due to German context)',
			'Not specified in the provided invoice text. Assuming EUR as it is a Dutch invoice.',
			'EUR (assumed based on the context of a German e-bike center)',
			'Not specified in the provided text, but it can be assumed EUR as it is a German document',
			'Not specified in the provided text. Assuming EUR as it is a German document.',
			'EUR (assumed as per standard for German invoices)',
			'Assumed EUR (based on the context of the invoice being from Germany)',
			'EUR (assumed due to the context of the invoice being from Germany)',
			'Not specified in the provided text. Assuming EUR as it is a common currency for Germany.',
			'Not detected (Assuming EUR for German context)',
			'Not detected (Assumed EUR based on context)',
			'not specified in the provided text, but it can be assumed EUR as it\'s a German business transaction',
			'Not found in the provided text, assuming EUR as it\'s a German document',
			'Not detected (Assuming EUR as it\'s a European invoice number format)',
			'Not specified in the provided text. Assuming EUR as it\'s a German context.',
			'Assumed EUR (based on the context that the invoice is from Germany)',
			'Not specified in the provided invoice text, but it could be assumed as EUR based on the country code \'de\' (Germany).',
			'EUR (assuming from context, as the invoice is not from Germany)',
			'Not specified in the provided invoice, but assuming EUR for Germany context with a certainty score of 0.8',
			'Not detected. Since the invoice is from Austria, it\'s likely that the currency is EUR. Certainty: 0.9',
			'Assumed EUR (based on common international format and no currency specified)',
			'EUR (assumed due to the contact numbers being from Germany)'
		]:
			return Currency.EURO
		elif name in [
			'DO', '$', 'USD', 'US', 'US Dollar', 'USS', '$USD', "$US", 'usd', '$ (US Dollars)', 'Us Dollar', 'USD ($)',
			'United States Dollar', 'Dollar', 'Dollars', 'Dollar (USD)', 'Dollar USD', 'Dollar $', 'usd (USD)',
			'Dollar ($)', 'USD US', 'USD US Dollar', 'usd (us dollar)', 'usd (dollar)', 'usd dollars',
			'Assumed USD (based on the absence of a currency symbol and the context of an American-sounding business name)'
		]:
			return Currency.DOLLAR
		elif name in [
			'PO', '£', 'GBP', 'GBP (£)', 'GBP (£ British Pound)', 'STERLING', 'pound', 'Pounds', 'Pound',
            'Pound Sterling', '£ (British Pound)', '£ (GBP)', '£GBP', '£ (Pound Sterling)'
		]:
			return Currency.POUND
		elif name in [
			'FR', 'CHF', 'CHF (Swiss Francs)', 'Fr', 'Swiss Francs (CHF)', 'CHE', 'SFr.', 'Sfr', 'Franci (CHF)',
			'Sfr.', 'Fr.', 'CFR', 'Fr. (Swiss Franc)', 'SFR (Swiss Franc)', 'CHF (Swiss Franc)', 'franc (CHF)', 'sfr',
			'CHF (Swiss Franc) as it is mentioned throughout the invoice.'
		]:
			return Currency.FRANKEN
		elif name in [
			'LE', 'RON', 'LEI', 'Lei',
			'LEI (based on context, as it is mentioned as the currency for the price of the bike)'
		]:  # romanian currency: Romanian leu
			return Currency.LEI
		elif name in [
			'ZL', 'PLN', 'POLISH ZLOTY', 'PL', 'zł', 'Złoty', 'Polish Zloty (PLN)', 'pln',
		    'PLN (Polish Zloty)', 'Zloty', 'PLN (PLN)', 'ZT'
		]:
			return Currency.ZLOTY
		elif name in ['DK', 'DKK', 'Dkk', 'DKK (Danish Kroner)', 'dkk', 'Danish Krone', 'DKK (Demark)']:
			return Currency.DKK
		elif name in ['CZ', 'CZK', 'kr.', 'Czech Republic Koruna (CZK)', 'kr', 'Kč', 'czk']:
			return Currency.CZK
		elif name in ['NK', 'NOK', 'nok', 'NOK (Norwegian Krone)']:
			return Currency.NOK
		elif name in ['NZD', 'NZ$', 'NZ', 'New Zealand Dollar', 'nzd']:
			return Currency.NZD
		elif name in ['AUD', 'AU', 'AUSTRALIA', 'AUD (Australian Dollar)', 'aud', 'Australian Dollar', 'AUD$']:
			return Currency.AUD
		elif name in ['SEK', 'SEK (Swedish Krona)']:
			return Currency.SEK
		elif name in ['CAD']:
			return Currency.CAD
		elif name in ['ISK', 'ISK (ISK)', 'ISK (Icelandic Krona)']:
			return Currency.ISK
		elif name in ['CA']:
			return Currency.CAD
		elif name in ['NZ']:
			return Currency.NZD
		elif name in ['SE']:
			return Currency.SEK
		elif name in ['SKK', 'SK']:
			return Currency.SKK
		elif name in ['YEN', 'YN', '¥', 'JPY', '¥ (Japanese Yen)', 'Yen']:
			return Currency.YEN
		elif name in ['HRK']:
			return Currency.HRK
		elif name in [
			'HUF', 'HUF (Hungarian Unite)', 'hu', 'Forint', 'Ft', 'Forint (HUF)', 'HUF (Hungarian Forint)',
		    'forint', 'Hungarian Forint'
		]:
			return Currency.FORINT
		elif name in ['BGN', 'BG', 'Bulgarian Lev', 'Lev', 'bgn']:
			return Currency.BGN
		elif name in ['UN', 'Unknown']:
			return Currency.UNKNOWN

		raise ValueError(f'currency not handled: "{name}"')

	def sign(self) -> str:
		if self == Currency.EURO:
			return "€"
		elif self == Currency.DOLLAR:
			return "$"
		elif self == Currency.FRANKEN:
			return "CHF"
		elif self == Currency.POUND:
			return "£"
		elif self == Currency.LEI:
			return "Lei"
		elif self == Currency.ZLOTY:
			return "Złoty"
		elif self == Currency.DKK:
			return "DKK"
		elif self == Currency.NOK:
			return "NOK"
		elif self == Currency.CZK:
			return "Kč"
		elif self == Currency.YEN:
			return "¥"
		elif self == Currency.HRK:
			return "kn"
		elif self == Currency.AED:
			return "aed"
		elif self == Currency.FORINT:
			return "Ft"
		else:
			return "?"


class Country(models.Model):
	"""A country with ISO codes, currency, and postal-code range settings."""

	name = models.CharField(max_length=255)
	emoji = models.CharField(max_length=5, null=True, blank=True, default=None)
	iso3 = models.CharField(max_length=255, null=True, blank=True, default=None)
	iso2 = models.CharField(max_length=255, null=True, blank=True, default=None)
	currency = models.CharField(max_length=2, choices=Currency.choices, default=Currency.UNKNOWN, )
	zips_use_range = models.BooleanField(default=False)

	objects = models.Manager()

	def admin_link(self):
		return mark_safe(f'<a href="/admin/data/country/{self.pk}/change/">{self.emoji} {self.name}</a>')

	def alternative_names(self) -> QuerySet:
		return AlternativeCountryName.objects.filter(country=self).values_list('name', flat=True)

	def __str__(self):
		return self.name

	class Meta:
		"""Require each country name to be unique."""

		constraints = [
			models.UniqueConstraint(fields=['name'], name='unique_country_name')
		]


class AlternativeCountryName(models.Model):
	"""An additional searchable name for a country."""

	country = models.ForeignKey(Country, on_delete=models.CASCADE)
	name = models.CharField(max_length=255)

	objects = models.Manager()

	def save(self, *args, **kwargs):
		# remove spaces
		if self.name is not None:
			self.name = _clean_string(self.name)

		super(AlternativeCountryName, self).save(*args, **kwargs)

	def __str__(self):
		return self.name


class State(models.Model):
	"""A state or region belonging to a country."""

	name = models.CharField(max_length=255)
	alternative_names = models.CharField(max_length=1024, null=True, blank=True, default=None)
	country = models.ForeignKey(Country, on_delete=models.CASCADE, default=None)
	iso2 = models.CharField(max_length=3, null=True, blank=True, default=None)

	objects = models.Manager()

	def admin_link(self):
		return mark_safe(f'<a href="/admin/data/state/{self.pk}/change/">{self.name}</a>')

	def county_list(self) -> List[str]:
		return list(map(lambda county: county.name, County.objects.filter(state=self)))

	def admin_county_list(self) -> SafeString:
		return mark_safe(', '.join(list(map(lambda county: county.admin_link(), County.objects.filter(state=self)))))

	def __str__(self):
		return self.name

	class Meta:
		"""Require each state name to be unique."""

		constraints = [
			models.UniqueConstraint(fields=['name'], name='unique_state_name')
		]


class County(models.Model):
	"""A county belonging to a state and containing cities."""

	name = models.CharField(max_length=255)
	alternative_names = models.CharField(max_length=1024, null=True, blank=True, default=None)
	state = models.ForeignKey(State, on_delete=models.CASCADE, default=None)

	objects = models.Manager()

	def num_cities(self) -> int:
		return len(City.objects.filter(county=self))

	def admin_link(self):
		return mark_safe(f'<a href="/admin/data/county/{self.pk}/change/">{self.name}</a>')

	def city_list(self) -> List[str]:
		return list(map(lambda city: city.name, City.objects.filter(county=self)))

	def __str__(self):
		return self.name

	class Meta:
		"""Require each county name to be unique."""

		constraints = [
			models.UniqueConstraint(fields=['name'], name='unique_county_name')
		]


class City(models.Model):
	"""A city with optional location, administrative divisions, and postal codes."""

	name = models.CharField(max_length=255)
	zip_code = models.CharField(max_length=255, null=True, blank=True, default=None)

	county = models.ForeignKey(County, on_delete=models.CASCADE, null=True, blank=True, default=None)
	state = models.ForeignKey(State, on_delete=models.CASCADE, null=True, blank=True, default=None)
	country = models.ForeignKey(Country, on_delete=models.CASCADE, null=True, blank=True, default=None)

	lat = models.FloatField(null=True, blank=True, default=None)
	lng = models.FloatField(null=True, blank=True, default=None)

	objects = models.Manager()

	def save(self, *args, **kwargs):
		# remove spaces
		if self.zip_code is not None:
			self.zip_code = str(self.zip_code).replace(" ", "")
			self.zip_code = self.zip_code.replace("–", '-')

		if '’' in self.name:
			self.name = self.name.replace('’', '\'')

		try:
			super(City, self).save(*args, **kwargs)
		except Exception as e:
			raise Exception(f'Cannot save "{self}"', e)

	def admin_link(self):
		return mark_safe(f'<a href="/admin/data/city/{self.pk}/change/"><strong>🏘️ {self.name}</strong></a>')

	def country_admin_link(self):
		return self.country.admin_link()

	def zip_list(self) -> List[str]:
		result_list = []

		if self.zip_code is None:
			return []

		parts: List[str] = self.zip_code.split(',')

		for part in parts:
			if '-' in part and self.country.zips_use_range:
				try:
					r_list = part.split('-')
					zip_len = len(r_list[0])
					start = int(r_list[0])
					end = int(r_list[1])
					for plz in range(start, end + 1):
						result_list.append(str(plz).zfill(zip_len))
				except ValueError as e:
					raise Exception(f'Cannot parse {part} of {self.name}', e)
			else:
				result_list.append(part)

		return result_list

	def alternative_city_names(self):  # -> [AlternativeCityName]:
		return AlternativeCityName.objects.filter(city=self)

	@staticmethod
	def find_city(city_name: str, exact: bool = False):
		if exact:
			city_name = city_name.lower().replace('’', '\'').strip()
			alt_cityName = _clean_string(city_name)
			alt_city_filter = Exists(AlternativeCityName.objects.filter(city_id=OuterRef('id'), name__iexact=alt_cityName))
			return City.objects.all().filter(Q(name__iexact=city_name) | Q(alt_city_filter)).order_by('name')
		else:
			city_name = _clean_string(city_name)
			alt_city_filter = Exists(AlternativeCityName.objects.filter(city_id=OuterRef('id'), name__istartswith=city_name))
			return City.objects.all().filter(Q(name__istartswith=city_name) | Q(alt_city_filter)).order_by('name')

	def __str__(self):
		return self.name

	class Meta:
		"""Require each city name to be unique."""

		constraints = [
			models.UniqueConstraint(fields=['name'], name='unique_city_name')
		]


class AlternativeCityName(models.Model):
	"""An additional city name, optionally flagged as ambiguous or needing a ZIP."""

	city = models.ForeignKey(City, on_delete=models.CASCADE)
	name = models.CharField(max_length=255)
	ambiguous = models.BooleanField(default=False)
	need_zip = models.BooleanField(default=False)

	objects = models.Manager()

	def save(self, *args, **kwargs):
		# remove spaces
		if self.name is not None:
			self.name = _clean_string(self.name)

		super(AlternativeCityName, self).save(*args, **kwargs)

	def __str__(self):
		return self.name


class StreetName(models.Model):
	"""A street name shared by one or more cities."""

	name = models.CharField(max_length=255)
	cities = models.ManyToManyField(City, through="StreetCityMembership")

	objects = models.Manager()

	def save(self, *args, **kwargs):
		self.name = self.name.strip()

		if '’' in self.name:
			self.name = self.name.replace('’', '\'')

		try:
			super(StreetName, self).save(*args, **kwargs)
		except Exception as e:
			raise Exception(f'Cannot save "{self}"', e)

	def alternative_city_names(self):
		return AlternativeStreetName.objects.filter(street=self)

	def __str__(self):
		return self.name

	def admin_link(self):
		return mark_safe(f'<a href="/admin/data/streetname/{self.pk}/change/">{self.name}</a>')

	class Meta:
		"""Prevent duplicate street names."""

		unique_together = ['name', ]

	@staticmethod
	def find_street(street_name: str, exact: bool = False):
		if exact:
			street_name = street_name.lower().strip()
			alt_streetName = _clean_string(street_name)
			alt_street_filter = Exists(AlternativeStreetName.objects.filter(street_id=OuterRef('id'), name__iexact=alt_streetName))
			return StreetName.objects.all().filter(Q(name__iexact=street_name) | Q(alt_street_filter)).order_by('name')
		else:
			street_name = _clean_string(street_name)
			alt_street_filter = Exists(AlternativeStreetName.objects.filter(street_id=OuterRef('id'), name__istartswith=street_name))
			return StreetName.objects.all().filter(Q(name__istartswith=street_name) | Q(alt_street_filter)).order_by('name')


class StreetCityMembership(models.Model):
	"""Link a street name to a city where that street exists."""

	city = models.ForeignKey(City, on_delete=models.CASCADE)
	street_name = models.ForeignKey(StreetName, on_delete=models.CASCADE)

	objects = models.Manager()

	def __str__(self):
		return f'{self.city.name} - {self.street_name.name}'


class AlternativeStreetName(models.Model):
	"""An additional searchable name for a street."""

	street = models.ForeignKey(StreetName, on_delete=models.CASCADE)
	name = models.CharField(max_length=255)

	objects = models.Manager()

	def save(self, *args, **kwargs):
		# remove spaces
		if self.name is not None:
			self.name = _clean_string(self.name)

			if self.name.lower() != 'rt' and len(self.name) < 4:
				raise ValidationError(_("Alternative street Name is too short: %s" % self.name))

		super(AlternativeStreetName, self).save(*args, **kwargs)

	def clean(self):
		if self.name == _clean_string(self.street.name):
			raise ValidationError(_("Alternative street Name matches the original street name"))

	def __str__(self):
		return self.name

	class Meta:
		"""Prevent duplicate alternative street names."""

		unique_together = ['name', ]

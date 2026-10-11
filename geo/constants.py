from enum import Enum

import cv2


class AddressRegex:
	"""
	Regex patterns for the different fields in the address string.
	"""
	salutation = r'SALUTATION\((?P<salutation>[0-9]+)\)'
	name = r'NAME\((?P<name>[0-9]+)\)'
	surname = r'(?P<surname>\w+)'
	ibd = r'IBD\((?P<ibd>[0-9]+)\)'
	street = r'STREET\((?P<street>[0-9]+)\)'

	# multiple street number patterns
	# 1/2/3, 1a, 1/2a, 1/2, 1 2/3, 1-2a, 1-2, 1-2/3a - fallback 1234
	street_number = r'(?P<street_number>(\d+\/\d+/\d+|\d+[a-z]|\d+[\/-]\d*[a-z]|\d+\/\d+|\d+ \d+\/\d+|[-0-9]+))'

	zip = r'ZIP\((?P<zip>[0-9]+)\)'
	uk_zip = r'ZIPUK\((?P<zipuk>[0-9a-z ]+)\)'  # ZIPUK(b90 3dx)
	city = r'CITY\((?P<city>[0-9]+)\)'


class UtilRegex:
	"""
	Regex patterns for utility functions.
	"""
	duplicate_words = r'\b(?P<word>\w{4,20})\s+\1\b'
	duplicate_two_words = r'\b(?P<words>\w{2,20}\s\w{3,20})\s+\1\b'
	duplicate_three_words = r'\b(?P<words>\w{2,20}\s\w{2,20}\s\w{3,20})\s+\1\b'



class Images:
	"""
	Images used in the application.
	"""
	def __init__(self):
		self.geo_image = None
		self.state_image = None

		self._populated = False

	def load(self):
		if self._populated:
			return

		self.geo_image = cv2.imread('static/images/views/geo_white-32.png', cv2.IMREAD_UNCHANGED)
		self.state_image = cv2.imread('static/images/views/state_white-32.png', cv2.IMREAD_UNCHANGED)

		self._populated = True

import re


def _clean_string(input_string: str) -> str:
	input_string = input_string.lower()
	input_string = input_string.replace(',', ' ')
	input_string = input_string.replace('.', ' ')
	input_string = input_string.replace('’', ' ')
	input_string = input_string.replace('‘', ' ')
	input_string = input_string.replace(';', ' ')
	input_string = input_string.replace(':', ' ')
	input_string = input_string.replace('“', ' ')
	input_string = input_string.replace('”', ' ')
	input_string = input_string.replace('"', ' ')
	input_string = input_string.replace('(', ' ')
	input_string = input_string.replace(')', ' ')
	input_string = input_string.replace('[', ' ')
	input_string = input_string.replace(']', ' ')
	input_string = input_string.replace('{', ' ')
	input_string = input_string.replace('}', ' ')
	input_string = input_string.replace('_', ' ')
	input_string = input_string.replace('\'', ' ')
	input_string = input_string.replace('|', ' ')
	# input_string = input_string.replace('/', ' ')  # problematic for street numbers
	input_string = input_string.replace('!', ' ')
	input_string = input_string.replace('?', ' ')
	input_string = input_string.replace('*', ' ')
	input_string = input_string.replace('«', ' ')
	input_string = input_string.replace('∴', ' ')
	input_string = input_string.replace('  ', ' ')
	input_string = input_string.replace('  ', ' ')
	input_string = input_string.replace('  ', ' ')

	# find street number range with spaces
	input_string = re.sub(r' (\d+) - (\d+) ', r' \1-\2 ', ' ' + input_string + ' ')

	input_string = input_string.strip()

	return input_string


def is_integer(n):
	try:
		float(n)
	except ValueError:
		return False
	else:
		return float(n).is_integer()


def has_numbers(inputString):
	return any(char.isdigit() for char in inputString)

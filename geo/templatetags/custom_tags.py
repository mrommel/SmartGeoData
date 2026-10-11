from django import template
import random

register = template.Library()


@register.filter(name='multiply')
def multiply(value, factor):
	return value * factor


@register.simple_tag
def define(val=None):
	return val


@register.filter
def dict_item(dictionary, key):
	return dictionary[key] if key in dictionary else '-'


@register.filter
def to_list(dict_keys):
	return list(dict_keys)


@register.filter(name='zip')
def zip_lists(a, b):
	return zip(a, b)


@register.filter
def index(indexable, i):
	return indexable[i]


@register.simple_tag
def randint(a, b=None):
	if b is None:
		a, b = 0, a
	return random.randint(a, b)

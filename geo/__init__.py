from termcolor import colored


def red(text: str) -> str:
	return colored(text, 'red')


def red_int(number: int) -> str:
	text = f'{number:,}'
	return colored(text, 'red')


def green(text: str) -> str:
	return colored(text, 'green')


def green_int(number: int) -> str:
	text = f'{number:,}'
	return colored(text, 'green')


def yellow(text: str) -> str:
	return colored(text, 'yellow')


def blue(text: str) -> str:
	return colored(text, 'blue')


def magenta(text: str) -> str:
	return colored(text, 'magenta')

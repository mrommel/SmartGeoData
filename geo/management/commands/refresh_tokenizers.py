from django.core.management.base import BaseCommand

from geo.tasks import start_population


class Command(BaseCommand):
	help = 'Queue fresh city and street tokenizer snapshots.'

	def handle(self, *args, **options):
		start_population(force=True)
		self.stdout.write('Queued city and street tokenizer refresh tasks.')

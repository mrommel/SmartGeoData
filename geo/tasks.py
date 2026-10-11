"""Background tokenizer snapshots shared between the task worker and web processes."""
from threading import Lock

from django.db import connection, transaction
from django_tasks import task, TaskResultStatus
from django_tasks_db.models import DBTaskResult

from geo.tokenizer import CityTokenizer, StreetTokenizer

@task
def populate_city_tokenizer():
	tokenizer = CityTokenizer()
	tokenizer.populate()
	return {
		'city_dict': tokenizer.city_dict,
		'country_dict': tokenizer.country_dict,
		'ibd_dict': tokenizer.ibd_dict,
		'state_dict': tokenizer.state_dict,
		'alternate_city_dict': tokenizer.alternate_city_dict,
		'alternate_state_dict': tokenizer.alternate_state_dict,
		'alternate_country_dict': tokenizer.alternate_country_dict,
		'country_us_id': tokenizer.country_us_id,
		'country_cn_id': tokenizer.country_cn_id,
		'country_aus_id': tokenizer.country_aus_id,
	}


@task
def populate_street_tokenizer():
	tokenizer = StreetTokenizer()
	tokenizer.populate()
	return {'street_dict': tokenizer.street_dict}


POPULATION_TASKS = {
	'city': populate_city_tokenizer,
	'street': populate_street_tokenizer,
}

_lock = Lock()
_loaded = {}


def start_population(*, force=False):
	"""Queue missing snapshots at startup, or explicitly refresh both snapshots."""
	with transaction.atomic():
		if connection.vendor == 'postgresql':
			# Serialize concurrent web process startups against the same database.
			with connection.cursor() as cursor:
				cursor.execute('SELECT pg_advisory_xact_lock(%s)', [45125770211045])
		for population_task in POPULATION_TASKS.values():
			if force or not DBTaskResult.objects.filter(
				task_path=population_task.module_path, backend_name=population_task.backend,
			).exists():
				population_task.enqueue()


def population_results():
	"""Return the newest database-backed task for each tokenizer."""
	return {
		name: DBTaskResult.objects.filter(
			task_path=population_task.module_path, backend_name=population_task.backend,
		).defer('return_value', 'args_kwargs', 'traceback').order_by('-enqueued_at', '-id').first()
		for name, population_task in POPULATION_TASKS.items()
	}


def population_status(results=None):
	results = population_results() if results is None else results
	status_map = {
		TaskResultStatus.READY: 'pending',
		TaskResultStatus.RUNNING: 'running',
		TaskResultStatus.SUCCESSFUL: 'completed',
		TaskResultStatus.FAILED: 'failed',
	}
	statuses = {name: status_map[result.status] if result else 'pending'
	            for name, result in results.items()}
	if 'failed' in statuses.values():
		global_status = 'failed'
	elif all(status == 'completed' for status in statuses.values()):
		global_status = 'completed'
	elif 'running' in statuses.values():
		global_status = 'running'
	else:
		global_status = 'pending'
	return {'status': global_status, 'tokenizers': statuses}


def get_tokenizers(results=None):
	"""Return both tokenizers only after the worker has finished both snapshots."""
	results = population_results() if results is None else results
	if any(result is None or result.status != TaskResultStatus.SUCCESSFUL
	       for result in results.values()):
		return None
	with _lock:
		for name, result in results.items():
			if name not in _loaded or _loaded[name][0] != result.id:
				if name == 'street':
					tokenizer = StreetTokenizer()
					tokenizer.load_snapshot(result.return_value['street_dict'])
				else:
					tokenizer = CityTokenizer()
					for key, value in result.return_value.items():
						if key in ('city_dict', 'country_dict', 'state_dict'):
							value = dict(sorted(value.items(), key=lambda item: len(item[0]), reverse=True))
						setattr(tokenizer, key, value)
					tokenizer.populated = True
				_loaded[name] = (result.id, tokenizer)
		return _loaded['city'][1], _loaded['street'][1]

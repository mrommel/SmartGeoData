# define the name of the virtual environment directory
VENV := .venv
MIGRATION ?= 0001

.PHONY: all venv run make_migrations migrate createsuperuser

# default target, when make executed without arguments
all: venv


$(VENV)/bin/python:
	python3 -m venv $(VENV)

$(VENV)/.requirements-installed: requirements.txt | $(VENV)/bin/python
	./$(VENV)/bin/python -m pip install -r requirements.txt
	touch $@

# venv is a shortcut target
venv: $(VENV)/.requirements-installed

run: venv
	./$(VENV)/bin/python manage.py runserver 9112

make_migrations: venv
	./$(VENV)/bin/python manage.py makemigrations
	./$(VENV)/bin/python manage.py sqlmigrate geo 0002  # change this
	./$(VENV)/bin/python manage.py migrate

migrate: venv
	./$(VENV)/bin/python manage.py migrate --run-syncdb

createsuperuser: venv
	./$(VENV)/bin/python manage.py createsuperuser
# mrommel + ...

.PHONY: venv install test test-docker

VENV ?= .venv
PYTHON ?= python
PIP ?= $(VENV)/bin/pip

venv:
	$(PYTHON) -m venv $(VENV)

install: venv
	$(PIP) install -r requirements.txt

test:
	pytest -q

test-docker:
	docker compose run --rm ownerbot_app pytest -q

PYTHON ?= python3
NETBIRD_PYTHON := tools/netbird/.venv/bin/python

.PHONY: validate-netbird test-netbird format-netbird

$(NETBIRD_PYTHON):
	$(PYTHON) -m venv tools/netbird/.venv

tools/netbird/.venv/.requirements: tools/netbird/requirements.txt | $(NETBIRD_PYTHON)
	$(NETBIRD_PYTHON) -m pip install -r tools/netbird/requirements.txt
	touch $@

validate-netbird: tools/netbird/.venv/.requirements
	$(NETBIRD_PYTHON) tools/netbird/gate.py

test-netbird: tools/netbird/.venv/.requirements
	$(NETBIRD_PYTHON) tools/netbird/gate.py --contracts-only

format-netbird: tools/netbird/.venv/.requirements
	$(NETBIRD_PYTHON) -m ruff format tools/netbird tests/netbird

.PHONY: render-netbird-bootstrap
render-netbird-bootstrap: tools/netbird/.venv/.requirements
	$(NETBIRD_PYTHON) tools/netbird/bootstrap.py

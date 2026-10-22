PY := ./venv/bin/python
PIP := ./venv/bin/pip

.PHONY: setup fetch server-start server-stop server-status app selftest lint clean assets

setup:
	./setup.sh

fetch:
	./scripts/fetch_assets.sh

server-start:
	COQUI_TOS_AGREED=1 $(PY) rocky_say.py --server start

server-stop:
	$(PY) rocky_say.py --server stop

server-status:
	$(PY) rocky_say.py --server status

app:
	./scripts/make_app.sh
	open -n ./Rocky.app

selftest:
	$(PY) rocky_eyes.py --selftest shots/eyes
	$(PY) rocky_desktop_app.py --selftest

lint:
	python3.11 -m compileall -q rocky_desktop_app.py rocky_eyes.py rocky_say.py app.py

assets:
	@test -f assets/rocky_ref_15s.wav || \
		(echo "Missing assets. Run ./scripts/fetch_assets.sh (or restore_assets.sh /path/to/assets)"; exit 1)
	@echo "assets present"

clean:
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete

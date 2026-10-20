PYTHON ?= python
.PHONY: test feasibility dev demo benchmark build
test:
	$(PYTHON) -m pytest -m "not live" -q
feasibility:
	$(PYTHON) -m hydra.probe
build:
	cd frontend && npm run build
dev demo:
	$(PYTHON) -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
benchmark:
	@echo "Benchmark harness is deferred; no benchmark values are fabricated."
	@exit 2

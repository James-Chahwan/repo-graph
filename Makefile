# repo-graph developer tasks.
.PHONY: test test-fast perf install-matrix bench help

help:
	@echo "test           full pytest suite"
	@echo "test-fast      skip e2e subprocess tests"
	@echo "perf           opt-in performance gates"
	@echo "install-matrix fresh-machine install matrix in Docker (pass/fail)"
	@echo "bench          run the A/B benchmark harness (see bench/README.md)"

test:
	pytest

test-fast:
	pytest -m "not e2e"

perf:
	pytest -m perf

# Clean-room install validation: builds a fresh image and runs every install path.
install-matrix:
	docker build -f docker/Dockerfile -t repo-graph-install-matrix .
	docker run --rm repo-graph-install-matrix

bench:
	python bench/run_bench.py

# repo-graph developer tasks.
.PHONY: test test-fast perf install-matrix bench skills help

help:
	@echo "test           full pytest suite"
	@echo "test-fast      skip e2e subprocess tests"
	@echo "perf           opt-in performance gates"
	@echo "install-matrix fresh-machine install matrix in Docker (pass/fail)"
	@echo "bench          run the A/B benchmark harness (see bench/README.md)"
	@echo "skills         copy skills/ into the Claude Code plugin (claude-plugin/skills/)"

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

# The skills live in glia (skills/ there, since glia 0.5.4). skills/ here is a
# copy, and the Claude Code plugin carries a copy of that, because it can't reach
# outside its own directory (marketplace installs copy only the plugin root).
# Copy from the glia tag this repo pins. tests/test_skills.py fails until the
# two copies here match.
GLIA ?= ../glia
skills:
	test -d $(GLIA)/skills
	rm -rf skills claude-plugin/skills
	cp -r $(GLIA)/skills skills
	cp -r skills claude-plugin/skills

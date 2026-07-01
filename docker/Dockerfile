# Fresh-machine install matrix.
#
# Proves `repo-graph install` works end to end on a clean OS with no prior config:
# installs the package, runs the installer for all 9 agents, asserts every config
# and instructions file landed, builds the graph on a sample repo, runs a `status`
# query, then uninstalls and asserts a clean reversal. `docker run` exits non-zero
# if any check fails.
#
#   docker build -f docker/Dockerfile -t repo-graph-install-matrix .
#   docker run --rm repo-graph-install-matrix
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# uv / uvx for the zero-install launch path
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app
COPY . /app

# Install this version (PyPI's published version predates the installer), pulling
# the Rust engine wheel + deps from PyPI — same as a real user's clean machine.
RUN pip install --no-cache-dir .

CMD ["python", "docker/install_matrix.py"]

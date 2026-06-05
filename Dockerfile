FROM python:3.12-slim
WORKDIR /app
# git lets the server clone a repo when REPO_GRAPH_REPO / --repo is a git URL
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY . .
RUN pip install --no-cache-dir .
ENTRYPOINT ["repo-graph"]

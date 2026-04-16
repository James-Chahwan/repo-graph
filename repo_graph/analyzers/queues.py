"""
Queue consumer analyzer.

Cross-cutting analyzer that detects background-job / message-queue consumers:
  - Python:   @celery.task, @shared_task, @app.task, @dramatiq.actor
  - JS/TS:    new Worker("q", ...), queue.process(...)   (BullMQ / Bull)
  - Ruby:     include Sidekiq::Worker / Sidekiq::Job / < ApplicationJob
  - Elixir:   use Oban.Worker
  - Go:       nats.Subscribe("subject", ...), nats.QueueSubscribe("subject", ...)

Emits `queue_consumer` nodes + `handled_by` edges to the file anchor; the
generator's auto-flow pass treats these as entrypoints with `kind: queue`.
"""

from __future__ import annotations

import re
from pathlib import Path

from .base import (
    AnalysisResult,
    Edge,
    LanguageAnalyzer,
    Node,
    read_safe,
    rel_path,
)


# Python — celery / dramatiq
_PY_CELERY_DECORATOR = re.compile(
    r"@(?:\w+\.)?(?:task|shared_task|actor)(?:\s*\([^)]*\))?\s*\n+"
    r"(?:@[^\n]+\n)*\s*def\s+(\w+)",
)
_PY_CELERY_IMPORT = re.compile(
    r"(?:^|\n)\s*(?:from\s+celery|import\s+celery|from\s+dramatiq|import\s+dramatiq)",
)

# JS/TS — BullMQ / Bull
_JS_BULL_WORKER = re.compile(
    r"""new\s+Worker\s*\(\s*['"`]([A-Za-z0-9_:\-]+)['"`]""",
)
_JS_BULL_PROCESS = re.compile(
    r"""(\w+)\.process\s*\(\s*(?:['"`]([A-Za-z0-9_:\-]+)['"`]\s*,\s*)?""",
)
_JS_BULL_IMPORT = re.compile(r"""['"`](?:bullmq|bull)['"`]""")

# Ruby — Sidekiq / ActiveJob
_RB_SIDEKIQ = re.compile(
    r"""class\s+(\w+)[^\n]*\n[^\n]*(?:include\s+Sidekiq::(?:Worker|Job)|<\s+ApplicationJob)""",
)

# Elixir — Oban
_EX_OBAN = re.compile(
    r"""defmodule\s+([\w.]+)\s+do[^\n]*\n\s*use\s+Oban\.Worker""",
)

# Go — NATS
_GO_NATS_SUB = re.compile(
    r"""(?:\.Subscribe|\.QueueSubscribe|\.PullSubscribe|\.ChanSubscribe)\s*\(\s*"([^"]+)""",
)
# Fallback: Subscribe(varname, ...) — subject is a variable. Emit a consumer
# keyed on the file instead of a bogus name, so the consumer still shows up.
_GO_NATS_SUB_ANY = re.compile(
    r"""\.(?:Subscribe|QueueSubscribe|PullSubscribe|ChanSubscribe)\s*\(""",
)
_GO_NATS_IMPORT = re.compile(r'"github\.com/nats-io/nats\.go"')


def _qc_id(name: str, file_rel: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_") or "q"
    file_slug = re.sub(r"[^a-zA-Z0-9]+", "_", file_rel).strip("_")
    return f"queue_{slug}__{file_slug}"


class QueueConsumerAnalyzer(LanguageAnalyzer):
    """Cross-cutting queue-consumer analyzer."""

    @staticmethod
    def detect(index) -> bool:
        # Tight patterns — require import/use boundary, not a bare substring.
        py_signals = ("from celery", "import celery", "from dramatiq", "import dramatiq")
        js_signals = ("'bullmq'", '"bullmq"', "'bull'", '"bull"', "`bullmq`", "`bull`")
        rb_signals = ("Sidekiq::Worker", "Sidekiq::Job", "< ApplicationJob")
        ex_signals = ("use Oban.Worker",)
        go_signals = ('"github.com/nats-io/nats.go"',)

        groups = [
            ((".py",), py_signals),
            ((".ts", ".tsx", ".js", ".jsx", ".mjs"), js_signals),
            ((".rb",), rb_signals),
            ((".ex", ".exs"), ex_signals),
            ((".go",), go_signals),
        ]
        for exts, signals in groups:
            for ext in exts:
                for f in index.files_with_ext(ext):
                    snippet = read_safe(f)
                    if not snippet:
                        continue
                    if any(sig in snippet for sig in signals):
                        return True
        return False

    def scan(self) -> AnalysisResult:
        nodes: list[Node] = []
        edges: list[Edge] = []
        seen: set[str] = set()

        self._scan_python(nodes, edges, seen)
        self._scan_js(nodes, edges, seen)
        self._scan_ruby(nodes, edges, seen)
        self._scan_elixir(nodes, edges, seen)
        self._scan_go(nodes, edges, seen)

        state = self._state(nodes)
        return AnalysisResult(nodes=nodes, edges=edges, state_sections=state)

    def _add(
        self, name: str, file_rel: str,
        nodes: list[Node], edges: list[Edge], seen: set[str],
    ) -> None:
        qid = _qc_id(name, file_rel)
        if qid in seen:
            return
        seen.add(qid)
        nodes.append(Node(
            id=qid, type="queue_consumer", name=name, file_path=file_rel,
        ))
        edges.append(Edge(
            from_id=qid, to_id=f"file::{file_rel}", type="handled_by",
        ))

    def _scan_python(self, nodes, edges, seen) -> None:
        for py in self.index.files_with_ext(".py"):
            content = read_safe(py)
            if not content or not _PY_CELERY_IMPORT.search(content):
                continue
            file_rel = rel_path(self.repo_root, py)
            for m in _PY_CELERY_DECORATOR.finditer(content):
                self._add(m.group(1), file_rel, nodes, edges, seen)

    def _scan_js(self, nodes, edges, seen) -> None:
        for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs"):
            for f in self.index.files_with_ext(ext):
                content = read_safe(f)
                if not content or not _JS_BULL_IMPORT.search(content):
                    continue
                file_rel = rel_path(self.repo_root, f)
                for m in _JS_BULL_WORKER.finditer(content):
                    self._add(m.group(1), file_rel, nodes, edges, seen)
                for m in _JS_BULL_PROCESS.finditer(content):
                    name = m.group(2) or m.group(1)
                    self._add(name, file_rel, nodes, edges, seen)

    def _scan_ruby(self, nodes, edges, seen) -> None:
        for rb in self.index.files_with_ext(".rb"):
            content = read_safe(rb)
            if not content:
                continue
            file_rel = rel_path(self.repo_root, rb)
            for m in _RB_SIDEKIQ.finditer(content):
                self._add(m.group(1), file_rel, nodes, edges, seen)

    def _scan_elixir(self, nodes, edges, seen) -> None:
        for ext in (".ex", ".exs"):
            for f in self.index.files_with_ext(ext):
                content = read_safe(f)
                if not content:
                    continue
                file_rel = rel_path(self.repo_root, f)
                for m in _EX_OBAN.finditer(content):
                    self._add(m.group(1), file_rel, nodes, edges, seen)

    def _scan_go(self, nodes, edges, seen) -> None:
        for go in self.index.files_with_ext(".go"):
            content = read_safe(go)
            if not content or not _GO_NATS_IMPORT.search(content):
                continue
            file_rel = rel_path(self.repo_root, go)
            literal_hits = 0
            for m in _GO_NATS_SUB.finditer(content):
                self._add(m.group(1), file_rel, nodes, edges, seen)
                literal_hits += 1
            # Variable-bound subjects: at least one Subscribe call exists but
            # no string literal was captured — register one consumer per file.
            if literal_hits == 0 and _GO_NATS_SUB_ANY.search(content):
                self._add(go.stem, file_rel, nodes, edges, seen)

    def _state(self, nodes: list[Node]) -> dict[str, str]:
        qcs = [n for n in nodes if n.type == "queue_consumer"]
        if not qcs:
            return {}
        return {"Queues": f"{len(qcs)} consumers\n"}

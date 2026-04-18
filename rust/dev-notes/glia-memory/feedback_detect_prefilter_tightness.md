---
name: Detect prefilter must be tight, not substring
description: Cross-cutting analyzer detect() prefilters should require import/use boundary, not bare word matches
type: feedback
originSessionId: e18af0c7-26eb-409e-8c0d-89cbaf6550d0
---
When writing `detect()` for a cross-cutting analyzer, never match bare substrings ("Bull", "click", "cobra") — they false-positive on unrelated code (e.g., "Bull" matched payment-component classes in webplatformfrontend).

**Why:** webplatformfrontend lit up QueueConsumerAnalyzer because it had a PaymentCard component with "Bull" in the class name. splorts-frontend similarly false-positived on CliEntrypointAnalyzer. Scan() correctly filtered so no bad nodes were emitted, but the analyzer still ran unnecessarily across the whole repo.

**How to apply:** use import-boundary signals — quoted module names (`"commander"`, `"bullmq"`), full import statements (`from celery`, `use clap::`), or full Go import paths (`"github.com/nats-io/nats.go"`). The pattern is in `cli.py` and `queues.py` detect(): a list of (extensions, signals) groups, each signal is a string that only appears in real imports.

Accept that our own analyzer source files will self-trigger detect() because the regex patterns are strings in the source. scan() filters correctly so no output noise — it's just a negligible perf cost.

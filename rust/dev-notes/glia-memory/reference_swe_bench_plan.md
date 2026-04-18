---
name: v0.4.13 SWE-bench Lite benchmark plan — latent loop proof artifact
description: Concrete benchmark plan for the latent loop proof: model, conditions, sample size, compute, cost. SCOPE REDUCED 2026-04-17 from SWE-bench Verified N=200 → SWE-bench Lite N=20-30 at ~$20-30.
type: reference
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**For v0.4.13 (was v0.4.12b, moved 2026-04-17 when 0.4.13 was carved out as the separate proof release). Pair with `project_040_vision.md` for context.**

## 2026-04-17 scope reduction

User verbatim: *"SWE-bench Lite is 300 problems... Pick 20-30 problems... Maybe $20-30 total"*. Rationale: the headline claim is qualitative ("same model, different context") — 20-30 problems from SWE-bench Lite (the already-tractable subset) is plenty to show directional effect without chasing statistical rigor. The arXiv-grade N=200/500 plan below is preserved for future reference, but the v0.4.13 cut is the cheap subset.

**Active plan:** SWE-bench Lite, N=20-30, 4090 Runpod, ~$20-30 total.

**Original plan (below) kept as record of the larger version if the small run signals go.**

---

## What the benchmark proves

The format thesis: **latent injection of graph context is dramatically more token-efficient than text projection while preserving (or improving) task performance.**

Specifically:
- 50k-node graph as text = ~30,000 tokens of context window burned
- Same graph as soft-prompt-prefix = ~few hundred "virtual tokens" carrying same information
- That's the ~100x compression claim

If Path B beats baseline on SWE-bench Verified, repo-graph stops being "another MCP server" and becomes "the format that demonstrated 100x context efficiency on real benchmarks."

## Three conditions (same model, same tasks)

1. **Baseline** — model alone, no graph
2. **Path A** — graph as dense text prepended to prompt
3. **Path B** — graph as latent prefix injected into hidden state (soft-prompt-prefix via candle)

Same scoring harness, same tasks, three runs.

## Model choice

**Qwen 2.5 Coder 7B.** Strongest cheap open coding model. Runs on a single 4090 (24GB VRAM, 7B fp16 fits at ~14GB + KV cache; 4-bit quant is ~4GB). candle-friendly.

If candle's model-surgery for Qwen fights us, fall back to Llama 3.1 8B or Mistral 7B.

## Sample sizes — what's actually conclusive

- **N=50** — smoke test only. Pass-rate differences under ~15% aren't statistically real. Use to confirm Path B works *at all*.
- **N=100** — barely conclusive, only if effect size is large. **Skip — worst of both worlds.**
- **N=200–250** — blog-credible. ~6% confidence interval. Real number.
- **N=500 (full SWE-bench Verified)** — arXiv / paper-grade. Definitive.

**Staged plan:**
- Stage 1: N=50 → if Path B beats Path A by any margin → green light
- Stage 2: N=200 → publishable number
- Stage 3 (later, if warranted): N=500 → arXiv

## Compute

**Use Runpod or Modal, not DigitalOcean** (DO GPU droplets are 2-3x more expensive than specialist shops).

- Runpod 4090 ~$0.34-0.69/hr (cheapest persistent)
- Modal serverless (great dev loop)
- Lambda A100 ~$1.29/hr (overkill for 7B inference)

**4090 is the right tool for 7B inference benchmarks.** A100 is for training. 4090 vs A100 difference is wall-time only — same model + same context = same accuracy delta either way. SWE-bench wall time is bottlenecked by Docker build + test validation (CPU/disk), not GPU inference, so 4090 is closer to 1.3x slower than A100, not 2-3x.

## Cost estimates

- N=50 smoke: ~$15-30
- N=200 publishable: ~$80-120
- N=500 arXiv: ~$300-400
- **Total worst case for the publishable outcome: ~$150 all-in (debug + re-runs)**

## Implementation timing (real, no hedging)

- Soft-prompt-prefix in candle: 3-7 days
- Constrained decoding for structural ops (outlines or candle logit processor): 2-3 days
- SWE-bench Verified harness wiring (use official harness from https://github.com/SWE-bench/SWE-bench): 2-4 days
- Compute runs: 1-2 days wall time
- Analysis + write-up: 2-3 days

**Total: ~2-3 weeks focused work.** If candle's model-surgery APIs fight us, add a week. Not months.

## Output deliverables

The artifact, not the release:
- Three numbers (baseline / Path A / Path B pass rates)
- One chart (side-by-side)
- One blog post / arXiv preprint
- HN / r/MachineLearning / Twitter posts

If Path B with a 7B model approaches frontier-model performance on SWE-bench, that's the slide deck and the front-page story.

## Don't gate the public release on this

v0.4.12a (Path A) ships to PyPI as 0.4.0. v0.4.12b (Path B) is a follow-up artifact, not a release. **Two news cycles instead of one.**

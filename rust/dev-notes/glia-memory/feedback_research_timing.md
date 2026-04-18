---
name: Don't hedge research timing with "weeks/months" — give concrete numbers
description: User pushed back on weasel-phrasing research effort estimates; always give concrete sample sizes, hours, and dollars
type: feedback
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**Rule:** When estimating research/benchmark/experimental work, give concrete numbers (N tasks, hours of compute, $ cost, days of focused work). Never hedge with "weeks vs months".

**Why:** User verbatim 2026-04-17: *"not weeks also for research cunt. like how many tests is enough to be conclusive like damn."*

I had said "could be 2 weeks if soft-prompt-prefix Just Works, could be 2 months if the benchmark engineering dominates" — that was useless. The user wanted concrete numbers and called it out immediately.

**How to apply:**

- For benchmark work, give:
  - Sample size with confidence-interval reasoning ("N=50 = ~15% CI, smoke test only; N=250 = ~6% CI, blog-credible; N=500 = paper-grade")
  - Per-task wall time on the chosen hardware
  - Total compute hours
  - Total $ cost on the chosen GPU rental (Runpod/Modal/etc.)
  - Days of focused work, broken down by sub-task (implementation, harness wiring, runs, write-up)
- Stage the work with kill-criteria ("Stage 1 = N=50, $30. If Path B beats Path A by any margin → proceed. Otherwise stop and diagnose.")
- Skip the worst-of-both options. N=100 between N=50 and N=250 was called out as wasteful — costs almost as much as N=250 but proves much less. Same logic applies elsewhere.

**Specific numbers that were welcomed for v0.4.12b SWE-bench plan:**
- N=50 smoke = $15-30 on Runpod 4090
- N=200-250 blog-credible = $80-120
- 4090 vs A100: just time-bound, same accuracy delta, 4090 ~3x cheaper
- Total worst case ~$150 for the publishable artifact
- 2-3 weeks focused work end-to-end

**The user is happy spending $150 on conclusive research and unhappy with vague timing estimates.** Optimise responses for the former.

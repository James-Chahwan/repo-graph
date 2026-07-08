# repo-graph benchmark

Model: `claude-haiku-4-5-20251001` · 2026-07-01 · median (p25-p75) over N runs per arm.
Metrics are from Claude Code's own result JSON (`total_cost_usd`, `num_turns`, `usage`). Controls: same model, same prompt, fresh clone, `--strict-mcp-config` (the without arm has no MCP servers at all; the with arm has only repo-graph). See bench/README.md.

| Repo | Task | Arm | Correct | Cost | Turns | Explore calls | Graph calls | Tokens | Time |
|------|------|-----|---------|------|-------|---------------|-------------|--------|------|
| quokka-stack | demo-bug | without | 2/2 | $0.186 (0.049-0.324) | 16 (2-29) | 13 (1-25) | 0 (0-0) | 3222 (706-5739) | 57s (12-102) |
| quokka-stack | demo-bug | with | 2/2 | $0.312 (0.260-0.364) | 28 (23-32) | 23 (19-27) | 0 (0-0) | 6938 (6223-7652) | 100s (90-111) |
| oci | t1-symptom | without | 2/2 | $0.070 (0.059-0.082) | 5 (4-6) | 4 (3-5) | 0 (0-0) | 2364 (2045-2684) | 42s (40-43) |
| oci | t1-symptom | with | 2/2 | $0.065 (0.026-0.105) | 6 (4-8) | 5 (3-7) | 0 (0-0) | 1939 (1567-2311) | 29s (24-34) |
| oci | t2-discovery | without | 0/2 | $0.026 (0.009-0.043) | 1 (1-1) | 0 (0-0) | 0 (0-0) | 831 (709-953) | 10s (9-12) |
| oci | t2-discovery | with | 2/2 | $0.172 (0.103-0.242) | 13 (6-20) | 6 (5-8) | 4 (0-7) | 6104 (3015-9193) | 87s (40-135) |
| oci | t3-blast | without | 2/2 | $0.365 (0.311-0.419) | 15 (7-23) | 16 (13-19) | 0 (0-0) | 6824 (4553-9095) | 88s (51-125) |
| oci | t3-blast | with | 2/2 | $0.186 (0.088-0.284) | 16 (6-26) | 12 (5-20) | 0 (0-0) | 6257 (3119-9395) | 91s (50-132) |
| quokka | t1-symptom | without | 2/2 | $0.071 (0.051-0.092) | 10 (9-10) | 8 (8-9) | 0 (0-0) | 2064 (1926-2203) | 30s (28-31) |
| quokka | t1-symptom | with | 2/2 | $0.065 (0.046-0.085) | 8 (8-8) | 7 (7-7) | 0 (0-0) | 1990 (1986-1994) | 32s (27-36) |
| quokka | t2-discovery | without | 2/2 | $0.069 (0.057-0.081) | 9 (8-10) | 8 (7-9) | 0 (0-0) | 2054 (1854-2255) | 31s (26-36) |
| quokka | t2-discovery | with | 2/2 | $0.135 (0.096-0.173) | 14 (10-19) | 12 (9-14) | 0 (0-0) | 3774 (2554-4994) | 52s (32-73) |
| quokka | t3-blast | without | 0/2 | $0.030 (0.011-0.049) | 1 (1-1) | 0 (0-0) | 0 (0-0) | 1650 (1411-1890) | 20s (17-23) |
| quokka | t3-blast | with | 1/2 | $0.058 (0.009-0.107) | 6 (1-11) | 5 (0-10) | 0 (0-0) | 2216 (1010-3421) | 34s (14-53) |

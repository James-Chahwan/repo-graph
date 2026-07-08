# repo-graph benchmark

Model: `claude-sonnet-5` · 2026-07-01 · median (p25-p75) over N runs per arm.
Metrics are from Claude Code's own result JSON (`total_cost_usd`, `num_turns`, `usage`). Controls: same model, same prompt, fresh clone, `--strict-mcp-config` (the without arm has no MCP servers at all; the with arm has only repo-graph). See bench/README.md.

| Repo | Task | Arm | Correct | Cost | Turns | Explore calls | Graph calls | Tokens | Time |
|------|------|-----|---------|------|-------|---------------|-------------|--------|------|
| quokka-stack | demo-bug | without | 2/2 | $0.516 (0.080-0.951) | 2 (0-4) | 2 (2-2) | 0 (0-0) | 3408 (-1582-8398) | 8s (-0-17) |
| quokka-stack | demo-bug | with | 2/2 | $0.181 (0.076-0.286) | 4 (3-4) | 2 (2-3) | 0 (0-0) | 7042 (6922-7161) | 15s (13-17) |
| oci | t1-symptom | without | 2/2 | $0.380 (0.335-0.426) | 10 (8-13) | 10 (7-12) | 0 (0-0) | 8148 (6964-9333) | 57s (34-79) |
| oci | t1-symptom | with | 2/2 | $0.636 (0.367-0.906) | 17 (10-24) | 13 (10-16) | 1 (-0-2) | 10079 (8266-11892) | 88s (52-124) |
| oci | t2-discovery | without | 2/2 | $0.537 (0.443-0.631) | 1 (1-1) | 2 (2-3) | 0 (0-0) | 2180 (1840-2520) | 23s (22-25) |
| oci | t2-discovery | with | 2/2 | $1.088 (0.812-1.363) | 22 (18-26) | 12 (6-17) | 6 (3-9) | 17052 (12982-21123) | 156s (109-204) |
| oci | t3-blast | without | 2/2 | $1.058 (0.017-2.098) | 19 (-0-38) | 16 (-1-34) | 0 (0-0) | 15918 (5019-26818) | 153s (-1-307) |
| oci | t3-blast | with | 2/2 | $0.455 (0.287-0.624) | 11 (8-14) | 10 (7-12) | 0 (0-0) | 9762 (9297-10227) | 62s (57-67) |
| quokka | t1-symptom | without | 2/2 | $0.253 (0.228-0.279) | 9 (8-10) | 8 (6-10) | 0 (0-0) | 6626 (6203-7050) | 36s (21-51) |
| quokka | t1-symptom | with | 2/2 | $0.425 (0.237-0.613) | 14 (4-24) | 6 (6-7) | 4 (-2-10) | 8431 (5730-11132) | 55s (15-95) |

# repo-graph benchmark

Model: `claude-sonnet-5` · 2026-07-01 · median (p25-p75) over N runs per arm.
Metrics are from Claude Code's own result JSON (`total_cost_usd`, `num_turns`, `usage`). Controls: same model, same prompt, fresh clone, `--strict-mcp-config` (the without arm has no MCP servers at all; the with arm has only repo-graph). See bench/README.md.

| Repo | Task | Arm | Correct | Cost | Turns | Explore calls | Graph calls | Tokens | Time |
|------|------|-----|---------|------|-------|---------------|-------------|--------|------|
| quokka-stack | locate-backend-entry | without | 3/3 | $0.172 (0.118-0.286) | 6 (4-6) | 5 (3-5) | 0 (0-0) | 6672 (5329-6796) | 18s (14-22) |
| quokka-stack | locate-backend-entry | with | 3/3 | $0.182 (0.120-0.236) | 4 (4-7) | 3 (3-6) | 0 (0-0) | 5822 (5811-6948) | 21s (15-23) |
| quokka-stack | xstack-friends | without | 3/3 | $0.274 (0.234-0.291) | 5 (1-5) | 3 (0-4) | 0 (0-0) | 5585 (144-6111) | 11s (4-30) |
| quokka-stack | xstack-friends | with | 3/3 | $0.406 (0.267-0.437) | 6 (5-8) | 0 (0-2) | 3 (3-4) | 5880 (5879-6214) | 15s (15-26) |
| quokka-stack | xstack-notifications | without | 3/3 | $0.334 (0.144-0.444) | 1 (1-6) | 0 (0-3) | 0 (0-0) | 277 (252-7307) | 4s (4-25) |
| quokka-stack | xstack-notifications | with | 3/3 | $0.370 (0.275-0.385) | 5 (5-5) | 0 (0-0) | 3 (3-3) | 6047 (6003-6448) | 15s (13-19) |

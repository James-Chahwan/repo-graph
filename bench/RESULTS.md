# repo-graph benchmark

Model: `claude-sonnet-5` · 2026-07-01 · median (p25-p75) over N runs per arm.
Metrics are from Claude Code's own result JSON (`total_cost_usd`, `num_turns`, `usage`). Controls: same model, same prompt, fresh clone, `--strict-mcp-config` (the without arm has no MCP servers at all; the with arm has only repo-graph). See bench/README.md.

| Repo | Task | Arm | Correct | Cost | Turns | Explore calls | Graph calls | Tokens | Time |
|------|------|-----|---------|------|-------|---------------|-------------|--------|------|
| fastapi-fullstack | locate-entry | without | 4/4 | $0.116 (0.081-0.182) | 4 (2-5) | 2 (1-4) | 0 (0-0) | 5150 (5010-5330) | 12s (7-14) |
| fastapi-fullstack | locate-entry | with | 4/4 | $0.299 (0.216-0.307) | 8 (3-8) | 1 (1-1) | 4 (1-5) | 5960 (5530-5993) | 19s (9-25) |
| fastapi-fullstack | find-routes | without | 4/4 | $0.087 (0.076-0.166) | 2 (2-3) | 1 (1-2) | 0 (0-0) | 5181 (5167-5383) | 9s (6-11) |
| fastapi-fullstack | find-routes | with | 4/4 | $0.244 (0.241-0.358) | 4 (4-6) | 0 (0-1) | 2 (2-3) | 5908 (5777-6009) | 15s (12-20) |
| fastapi-fullstack | trace-to-data | without | 4/4 | $0.204 (0.166-0.269) | 7 (6-7) | 6 (5-6) | 0 (0-0) | 6734 (6564-7381) | 27s (26-35) |
| fastapi-fullstack | trace-to-data | with | 3/4 | $0.434 (0.383-0.490) | 15 (12-17) | 1 (0-1) | 12 (10-13) | 7758 (7383-8488) | 50s (46-60) |
| gin-examples | locate-entry | without | 4/4 | $0.106 (0.098-0.198) | 4 (3-4) | 2 (2-3) | 0 (0-0) | 5127 (5084-5198) | 10s (9-11) |
| gin-examples | locate-entry | with | 4/4 | $0.278 (0.265-0.379) | 6 (5-7) | 0 (0-0) | 4 (3-4) | 5976 (5930-6075) | 20s (16-32) |
| gin-examples | find-routes | without | 4/4 | $0.104 (0.092-0.168) | 3 (2-4) | 2 (1-3) | 0 (0-0) | 5100 (5014-5205) | 12s (10-17) |
| gin-examples | find-routes | with | 4/4 | $0.302 (0.264-0.346) | 6 (5-8) | 0 (0-2) | 4 (2-5) | 5963 (5714-6097) | 21s (15-26) |
| gin-examples | trace-handler | without | 4/4 | $0.123 (0.102-0.203) | 4 (3-4) | 3 (2-3) | 0 (0-0) | 5446 (5268-5524) | 15s (12-19) |
| gin-examples | trace-handler | with | 4/4 | $0.358 (0.317-0.471) | 10 (6-12) | 0 (0-1) | 6 (4-8) | 6314 (5841-7052) | 32s (25-39) |
| nestjs-starter | locate-entry | without | 4/4 | $0.099 (0.090-0.177) | 4 (3-4) | 2 (2-3) | 0 (0-0) | 5102 (5052-5200) | 10s (10-11) |
| nestjs-starter | locate-entry | with | 4/4 | $0.258 (0.249-0.339) | 5 (5-6) | 0 (0-0) | 2 (2-3) | 5704 (5668-5742) | 16s (12-18) |
| nestjs-starter | find-controller | without | 4/4 | $0.091 (0.077-0.161) | 2 (2-3) | 2 (1-2) | 0 (0-0) | 5025 (4977-5119) | 9s (7-13) |
| nestjs-starter | find-controller | with | 4/4 | $0.209 (0.209-0.295) | 3 (3-3) | 0 (0-0) | 1 (1-1) | 5454 (5448-5460) | 10s (8-12) |
| nestjs-starter | trace-service | without | 4/4 | $0.110 (0.108-0.205) | 4 (4-5) | 4 (3-4) | 0 (0-0) | 5323 (5227-5409) | 15s (14-18) |
| nestjs-starter | trace-service | with | 4/4 | $0.326 (0.299-0.389) | 10 (9-12) | 0 (0-0) | 8 (6-10) | 6138 (6105-6588) | 33s (23-41) |
| django-oscar | locate-entry | without | 4/4 | $0.088 (0.075-0.164) | 2 (2-3) | 1 (1-2) | 0 (0-0) | 5144 (5076-5357) | 8s (6-14) |
| django-oscar | locate-entry | with | 4/4 | $0.232 (0.125-0.317) | 4 (2-4) | 0 (0-1) | 2 (0-2) | 5716 (5698-5782) | 10s (10-12) |
| django-oscar | find-models | without | 4/4 | $0.120 (0.099-0.192) | 4 (3-4) | 2 (2-3) | 0 (0-0) | 5354 (5287-5644) | 12s (11-14) |
| django-oscar | find-models | with | 4/4 | $0.250 (0.123-0.324) | 4 (2-5) | 0 (0-1) | 2 (0-3) | 5829 (5656-5959) | 12s (9-16) |
| django-oscar | trace-view | without | 3/4 | $0.250 (0.084-0.312) | 9 (3-10) | 8 (2-10) | 0 (0-0) | 6495 (5560-6830) | 35s (14-38) |
| django-oscar | trace-view | with | 4/4 | $0.680 (0.585-0.766) | 20 (18-22) | 7 (4-10) | 8 (5-11) | 10564 (9923-11654) | 85s (78-102) |

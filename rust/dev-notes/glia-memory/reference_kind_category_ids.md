---
name: Correct kind/category u32 IDs
description: Actual NodeKindId and EdgeCategoryId values from code-domain — must match exactly when mapping in Python or other consumers
type: reference
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
Source: `rust/code-domain/src/lib.rs`

### NodeKindId values
| ID | Name |
|----|------|
| 1 | MODULE |
| 2 | CLASS |
| 3 | FUNCTION |
| 4 | METHOD |
| 5 | ROUTE |
| 6 | PACKAGE |
| 7 | INTERFACE |
| 8 | STRUCT |
| 9 | ENDPOINT |
| 10 | ENUM |
| 11-22 | Cross-stack (GRPC_SERVICE through CLI_INVOCATION) |
| 23 | DATA_SOURCE (DB client) |
| 24 | CACHE |
| 25 | BLOB_STORE |
| 26 | SEARCH_INDEX |
| 27 | EMAIL_SERVICE |
| 28 | COMPONENT (v0.4.11a) |
| 29 | HOOK (v0.4.11a) |
| 30 | SERVICE (v0.4.11a) |
| 31 | DIRECTIVE (v0.4.11a) |
| 32 | PIPE (v0.4.11a) |
| 33 | GUARD (v0.4.11a) |
| 34 | COMPOSABLE (v0.4.11a) |

### EdgeCategoryId values
| ID | Name |
|----|------|
| 1 | DEFINES |
| 2 | CONTAINS |
| 3 | IMPORTS |
| 4 | CALLS |
| 5 | USES |
| 6 | DOCUMENTS |
| 7 | TESTS |
| 8 | INJECTS |
| 9 | HANDLED_BY |
| 10 | HTTP_CALLS |
| 11-17 | Cross-stack (GRPC_CALLS through CLI_INVOKES) |
| 18 | ACCESSES_DATA (DB/cache/blob/search/email edges, v0.4.11a D1) |

**Why:** Python mapping in graph.py had wrong IDs (ROUTE was 6 not 5, CLASS was 4 not 2) which broke flow detection. Always verify against the Rust source.

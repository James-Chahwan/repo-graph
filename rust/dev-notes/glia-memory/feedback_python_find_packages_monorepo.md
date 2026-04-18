---
name: Python analyzer _find_packages must use scan_project_dirs
description: Python _find_packages was only checking repo root + src/ + lib/, missing monorepo subdirs like backend/app/
type: feedback
originSessionId: 6408138d-8c57-417e-b3fa-73a15b35a7bf
---
`_find_packages()` in python_lang.py must use `scan_project_dirs()` to find all project subdirectories, not just check the repo root directly. Then check src/ and lib/ within each found directory.

**Why:** FastAPI full-stack template has packages at `backend/app/` which was missed. The analyzer detected 0 routes despite having `@router.get()` decorators because `backend/` wasn't scanned.

**How to apply:** Any analyzer's package/module discovery should go through `scan_project_dirs()` to handle monorepo layouts. Don't assume source is directly under repo root.

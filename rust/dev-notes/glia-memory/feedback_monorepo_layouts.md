---
name: Monorepo layout support
description: scan_project_dirs must handle packages/*, apps/*, services/*, src/*, crates/*, lib/* and fallback detection for projects without standard markers
type: feedback
originSessionId: 6408138d-8c57-417e-b3fa-73a15b35a7bf
---
_MONOREPO_DIRS must include: packages, apps, services, modules, libs, projects, workspace, src, crates.

**Why:** Real projects use diverse layouts. Ripgrep uses `crates/`, .NET uses `src/`, Ansible uses `lib/ansible/`. Each round of testing found a missing layout pattern. Also need fallback detection: C/C++ projects may have no build marker (nginx uses auto/configure), PHP projects may lack composer.json (WordPress has raw .php files).

**How to apply:** When adding new analyzers, always use `scan_project_dirs()` and add a fallback detection path for projects that don't use standard marker files. Check common workspace patterns for the language.

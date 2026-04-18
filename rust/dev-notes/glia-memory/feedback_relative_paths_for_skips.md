---
name: Use relative paths for skip checks
description: All analyzers must use rel_path() for file skip checks, never raw absolute paths — /tmp/ in absolute paths caused a real bug
type: feedback
originSessionId: 6408138d-8c57-417e-b3fa-73a15b35a7bf
---
Always compute `file_rel = rel_path(self.repo_root, file)` BEFORE skip checks, then check against `file_rel` not `str(file)`.

**Why:** The Ruby analyzer had `"/tmp/" in str(rb_file)` which matched the absolute path `/tmp/rails-test/...` and skipped ALL files. This was a real bug found testing Rails.

**How to apply:** In every analyzer's scan loop, compute rel_path first, then do all string-based skip checks on the relative path. Fixed across all analyzers: ruby.py, csharp.py, swift.py, php.py, c_cpp.py, java.py.

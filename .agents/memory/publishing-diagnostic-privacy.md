---
name: Publishing diagnostic privacy
description: Why dependency-build diagnostics deliberately trade raw detail for safe fixed hints.
---

Keep shared publishing diagnostics limited to exit status and fixed,
actionable hints. Do not replace this with streaming raw installer output
or a URL-only regex redactor.

**Why:** Installers run third-party package build scripts, which can print
arbitrary secrets outside recognizable URL formats. Even successful installs
can print sensitive index links. No general regex redactor can guarantee safety
for that output, so detailed diagnosis belongs in an isolated reproduction
without production secrets.

**How to apply:** When extending build diagnostics, add known failure
classifications with fixed text rather than echoing matching raw lines.
Preserve nonzero build status; safe logging must not hide installation failure.
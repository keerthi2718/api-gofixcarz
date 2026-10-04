---
name: Python publishing tools
description: Replit Python base toolchains can provide standalone pip without an importable pip module.
---

Do not assume that an available `pip` executable means the API interpreter can run `python -m pip`.

**Why:** Publishing with the Python 3.13 base module failed because pip was supplied separately by the Nix toolchain, not installed in the application's interpreter. The standalone pip supports `--python` to target that interpreter explicitly.

**How to apply:** Verify installer availability separately from interpreter imports. Keep dependency installs directed at the API interpreter and retain fail-closed, private installer diagnostics. Do not change Python versions or disable installation failures to bypass this distinction.
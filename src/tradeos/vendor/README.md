# Vendored dependencies

Third-party code copied into the tree rather than installed from PyPI.

## Why

An unmaintained package that we depend on can be yanked, renamed, or have its
account compromised. `pandas-ta` is the cautionary example: its GitHub repo now
404s, its PyPI history was wiped to two betas, and its stated licence URL is a
dead domain. That is not a risk worth carrying in a repository that handles
money.

Vendoring also keeps the installer honest. WOLF installs with `curl | sh` and no
sudo, so every dependency that ships a compiled wheel is a platform where the
install can fail. Everything here is pure Python.

## plotext 5.3.2

* Source: https://github.com/piccolomo/plotext
* Commit: `4d19108b93e34a60ba789681756450ae126a76ed` (2024-09-23)
* Licence: MIT, preserved at `plotext/LICENSE`
* Dependencies: none outside the standard library

### Changes made

Kept to the minimum needed to run from this location.

1. **Absolute self-imports rewritten as relative.** Upstream uses
   `from plotext._utility import ...` throughout, which only resolves when the
   package sits at the top level.
2. **`__name__ = "plotext"` removed from `__init__.py`.** Relative imports
   resolve `.` against `__name__`, so that line made every internal import look
   for a top-level `plotext` that does not exist here. It is cosmetic upstream
   and fatal when vendored.
3. **`plotext_cli.py` and `__main__.py` deleted.** They implement a shell tool
   for plotting CSV files, which WOLF does not use, and they were the only
   modules left importing the package absolutely.

### Updating

Re-clone upstream, reapply the three changes above, then run the vendor tests.
Do not edit anything else here: local fixes belong in our own code so the next
update does not silently drop them.

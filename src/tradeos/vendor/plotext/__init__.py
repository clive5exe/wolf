"""plotext plots directly on terminal."""

# Upstream sets ``__name__ = "plotext"`` here, which is cosmetic for it and
# fatal for us: relative imports resolve ``.`` against ``__name__``, so with it
# in place every ``from ._core import *`` looks for a top-level ``plotext``
# package that does not exist once the code is vendored. Removed deliberately.

__version__ = "5.3.2"

from ._core import *  # noqa: F401,F403

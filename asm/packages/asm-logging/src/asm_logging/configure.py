"""Process-wide logging configuration: one stdout handler, idempotent."""

import logging
import sys


def configure_logging(*, level: str = "INFO") -> None:
    """Configures the root logger: one stdout handler at `level`.

    Idempotent — safe to call more than once; replaces the handler list instead of
    stacking duplicates. Raises ValueError if `level` isn't a recognized level name.
    """
    numeric_level = logging.getLevelNamesMapping().get(level.upper())
    if numeric_level is None:
        raise ValueError(f"Unknown log level: {level!r}")

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(numeric_level)
    root.handlers = [handler]

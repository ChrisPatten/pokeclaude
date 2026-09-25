"""PokeClaude Gen III save file parser package.

Exposes ``__version__``, read from the ``VERSION`` file at the repo root
(the single source of truth for the project's version — see
``scripts/bump_version.py`` and ``CHANGELOG.md``). Falls back to
``"0.0.0-unknown"`` if VERSION is missing, e.g. when this package is
vendored or copied without the rest of the repo.
"""

from pathlib import Path

_VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"

try:
    __version__ = _VERSION_FILE.read_text(encoding="utf-8").strip()
    if not __version__:
        raise ValueError("VERSION file is empty")
except (OSError, ValueError):
    __version__ = "0.0.0-unknown"

__all__ = ["__version__"]

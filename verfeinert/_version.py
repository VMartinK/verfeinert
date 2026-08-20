"""Runtime version resolution for Verfeinert."""

from __future__ import annotations

from importlib import metadata


PACKAGE_NAME = "verfeinert"
SOURCE_TREE_VERSION = "0.3.1"


def runtime_version(
    *,
    package_name: str = PACKAGE_NAME,
    fallback: str = SOURCE_TREE_VERSION,
) -> str:
    """Return the installed package version, with a source-tree fallback."""
    try:
        return metadata.version(package_name)
    except metadata.PackageNotFoundError:
        return fallback


__version__ = runtime_version()


__all__ = [
    "__version__",
    "runtime_version",
]

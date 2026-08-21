"""PyCBC Inference Pipeline integration for Asimov."""

from .pycbc import PyCBC

__all__ = ["PyCBC"]

try:
    from importlib.metadata import PackageNotFoundError, version
except ImportError:
    from importlib_metadata import PackageNotFoundError, version

try:
    __version__ = version(__name__)
except PackageNotFoundError:
    __version__ = "unknown"

__version__ = "0.1.0"

__all__ = ["Workflow"]


def __getattr__(name):
    if name == "Workflow":
        from .engine import Workflow
        return Workflow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

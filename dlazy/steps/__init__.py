from .base import Step

_registry = {}


def register_step(type_name):
    def decorator(cls):
        cls.type = type_name
        _registry[type_name] = cls
        return cls
    return decorator


def create_step(defn, param, ctx):
    type_name = defn.get("type")
    if type_name not in _registry:
        raise ValueError(f"Unknown step type: {type_name}. Available: {list(_registry)}")
    return _registry[type_name](defn, param, ctx)


from . import scf

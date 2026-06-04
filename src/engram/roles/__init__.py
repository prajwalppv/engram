"""Role registry + discovery. Built-ins here; third-party roles via the
``engram.roles`` entry-point group (ship a role as a separate pip package)."""
from __future__ import annotations

from importlib.metadata import entry_points

from .base import Role
from .em import EMRole
from .generic import GenericRole
from .pm import PMRole
from .swe import SWERole

_BUILTINS: dict[str, type[Role]] = {
    "generic": GenericRole,
    "swe": SWERole,
    "pm": PMRole,
    "em": EMRole,
}


def _discover(name: str) -> type[Role] | None:
    try:
        eps = entry_points(group="engram.roles")
    except TypeError:  # pragma: no cover
        eps = entry_points().get("engram.roles", [])  # type: ignore[attr-defined]
    for ep in eps:
        if ep.name == name:
            obj = ep.load()
            if isinstance(obj, type) and issubclass(obj, Role):
                return obj
    return None


def available_roles() -> list[str]:
    names = set(_BUILTINS)
    try:
        for ep in entry_points(group="engram.roles"):
            names.add(ep.name)
    except Exception:  # pragma: no cover
        pass
    return sorted(names)


def get_role(name: str) -> Role:
    cls = _BUILTINS.get(name) or _discover(name)
    if cls is None:
        return GenericRole()
    return cls()


def all_roles() -> list[Role]:
    return [get_role(n) for n in available_roles()]

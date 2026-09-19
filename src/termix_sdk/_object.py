# Adapted from stripe-python (stripe/_stripe_object.py), MIT License,
# Copyright (c) 2010-2018 Stripe. See NOTICE for the full license text.
"""TermixObject: the base class of every value the SDK hands back.

Much simpler than stripe's StripeObject on purpose: Termix resources are
not independently retrievable/saveable the way Stripe's are (there is no
`host.save()` — you call `client.hosts.update(id, **params)`), so this
drops StripeObject's unsaved-value diffing, `serialize()`, and `refresh_from`
entirely. What's kept: dict-backed storage with attribute access,
`to_dict()`, a JSON `__str__`, and `construct_from` classmethod recursion
into typed model subclasses (used by the generated `models/` package —
see docs/sdk-plan.md section 2, item 9).
"""

from __future__ import annotations

import json
from typing import Any, ClassVar, cast

from ._response import TermixResponse
from ._util import redact_value as _redact


class TermixObject:
    """Dict-backed base class with attribute access.

    `obj.some_field` and `obj["some_field"]` are equivalent. Use
    `.to_dict()` to get a plain `dict` (recursively converting any nested
    `TermixObject`/model instances too).
    """

    # Dict method names people reach for out of habit, so the AttributeError
    # points at .to_dict() instead of looking like a missing API field.
    _DICT_METHOD_NAMES: ClassVar[frozenset[str]] = frozenset(
        {"get", "keys", "values", "items", "pop", "setdefault", "update"}
    )

    # Set by generated model subclasses: field name -> nested model class,
    # for fields whose value should recurse into that class instead of a
    # plain TermixObject. Union-typed fields (an OpenAPI oneOf) are left as
    # plain dicts/TermixObject; picking the right variant isn't attempted.
    _inner_class_types: ClassVar[dict[str, type[TermixObject]]] = {}

    def __init__(self, last_response: TermixResponse | None = None) -> None:
        object.__setattr__(self, "_data", {})
        object.__setattr__(self, "_last_response", last_response)

    @property
    def last_response(self) -> TermixResponse | None:
        return self._last_response

    # -- dict-like access -------------------------------------------------

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._data

    # Deliberately *not* implemented as real methods: `.get()`, `.keys()`,
    # `.values()`, `.items()`, `.pop()`, `.setdefault()`, `.update()`. The
    # spec has real fields named `items` (`GET /releases/rss`'s response)
    # and could grow others from this list; a bound method here would
    # permanently shadow that field. `__getattr__` below gives a field
    # named e.g. "items" priority over the dict-method meaning, and falls
    # back to a clarifying error only when no such field exists. Use
    # `obj["items"]` or `obj.to_dict()` for real dict operations.

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self):
        return iter(self._data)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, TermixObject):
            return self._data == other._data
        return NotImplemented

    # -- attribute access --------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._data[name]
        except KeyError as err:
            if name in self._DICT_METHOD_NAMES:
                raise AttributeError(
                    f"'{name}' is a dict method, but {type(self).__name__!r} "
                    f"is not a dict and has no field named {name!r} either. "
                    f"Use .to_dict() to get a real dict, or obj[{name!r}] if "
                    f"you expect a field by that name."
                ) from err
            raise AttributeError(
                f"{type(self).__name__!r} object has no field {name!r}. "
                f"Known fields: {sorted(self._data)!r}"
            ) from err

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_") or name in self.__dict__:
            object.__setattr__(self, name, value)
        else:
            self._data[name] = value

    # -- construction from a raw dict --------------------------------------

    @classmethod
    def construct_from(
        cls,
        values: Any,
        *,
        last_response: TermixResponse | None = None,
    ) -> Any:
        """Build an instance of `cls` (or, for a bare array response, a
        `list` of them) from a raw JSON value, recursing into
        `_inner_class_types` for known nested fields.
        """
        if isinstance(values, list):
            return [cls.construct_from(item, last_response=last_response) for item in values]
        if not isinstance(values, dict):
            # A handful of endpoints answer 200 with a bare scalar/None.
            return values

        instance = cls(last_response=last_response)
        for key, value in cast(dict[str, Any], values).items():
            nested_cls = instance._inner_class_types.get(key)
            if nested_cls is not None:
                instance._data[key] = nested_cls.construct_from(value, last_response=last_response)
            elif isinstance(value, dict):
                instance._data[key] = TermixObject.construct_from(
                    value, last_response=last_response
                )
            elif isinstance(value, list):
                instance._data[key] = [
                    TermixObject.construct_from(item, last_response=last_response)
                    if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                instance._data[key] = value
        return instance

    # -- output -------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        def convert(value: Any) -> Any:
            if isinstance(value, TermixObject):
                return value.to_dict()
            if isinstance(value, list):
                return [convert(v) for v in cast(list[Any], value)]
            return value

        return {key: convert(value) for key, value in self._data.items()}

    def _redacted_dict(self) -> dict[str, Any]:
        def convert(key: str, value: Any) -> Any:
            if isinstance(value, TermixObject):
                return value._redacted_dict()
            if isinstance(value, list):
                return [
                    v._redacted_dict() if isinstance(v, TermixObject) else _redact(key, v)
                    for v in cast(list[Any], value)
                ]
            return _redact(key, value)

        return {key: convert(key, value) for key, value in self._data.items()}

    def __str__(self) -> str:
        return json.dumps(self._redacted_dict(), sort_keys=True, indent=2, default=str)

    def __repr__(self) -> str:
        ident = type(self).__name__
        obj_id = self._data.get("id")
        if obj_id is not None:
            return f"<{ident} id={obj_id!r}> JSON: {self}"
        return f"<{ident}> JSON: {self}"

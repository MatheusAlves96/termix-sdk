# Adapted from stripe-python (stripe/_util.py), MIT License,
# Copyright (c) 2010-2018 Stripe. See NOTICE for the full license text.
"""Logging and secret-redaction helpers shared across the package.

Kept deliberately small: stripe's `_util.py` also carries telemetry,
dashboard-link building, and `class_method_variant` for its legacy
classmethod resource API — none of which apply here (see
docs/sdk-plan.md section 5).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

logger: logging.Logger = logging.getLogger("termix_sdk")

# Field names carrying a secret. Matched case-insensitively against the
# *end* of the field name, so `password`, `sudoPassword`,
# `autostartKeyPassword`, `tmx_...` API keys stored under `key`/`token`
# fields, etc. are all caught. See docs/api-schema-validation.md and
# HostRecord in spec/termix-openapi.json for the concrete field names this
# was built from.
_SECRET_FIELD_SUFFIXES = (
    "password",
    "key",
    "keypassword",
    "secret",
    "token",
)

# Header names whose value should never be logged.
_SECRET_HEADER_NAMES = frozenset({"authorization", "cookie", "set-cookie"})


def looks_secret(field_name: str) -> bool:
    lowered = field_name.lower()
    return any(lowered.endswith(suffix) for suffix in _SECRET_FIELD_SUFFIXES)


def redact_value(field_name: str, value: Any) -> Any:
    if isinstance(value, str) and value and looks_secret(field_name):
        return "<redacted>"
    return value


def redact_headers(headers: Mapping[str, str]) -> dict:
    return {
        k: ("<redacted>" if k.lower() in _SECRET_HEADER_NAMES else v)
        for k, v in headers.items()
    }


def redact_mapping(data: Mapping[str, Any]) -> dict:
    """Shallow redaction for logging a request/response body. Nested dicts
    are redacted one level deep, which covers every secret field the spec
    documents (they're all top-level on their record); deeper structures are
    left as-is rather than walked recursively on every log line.
    """
    out = {}
    for key, value in data.items():
        if isinstance(value, dict):
            out[key] = {k: redact_value(k, v) for k, v in value.items()}
        else:
            out[key] = redact_value(key, value)
    return out


def logfmt(props: Mapping[str, Any]) -> str:
    def fmt(key: str, val: Any) -> str:
        val = redact_value(key, val)
        val = str(val)
        if "\n" in val:
            val = "\\n".join(val.split("\n"))
        if '"' in val:
            val = val.replace('"', '\\"')
        if " " in val or "=" in val:
            val = f'"{val}"'
        return f"{key}={val}"

    return " ".join(fmt(key, val) for key, val in sorted(props.items()))


def log_debug(message: str, **params: Any) -> None:
    if params:
        message = f"{message} {logfmt(params)}"
    logger.debug(message)


def log_info(message: str, **params: Any) -> None:
    if params:
        message = f"{message} {logfmt(params)}"
    logger.info(message)

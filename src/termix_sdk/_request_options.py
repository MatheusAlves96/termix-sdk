# Adapted from stripe-python (stripe/_request_options.py), MIT License,
# Copyright (c) 2010-2018 Stripe. See NOTICE for the full license text.
"""Per-call overrides, passed as the trailing `options=` argument on every
generated method.
"""

from __future__ import annotations

from collections.abc import Mapping

from typing_extensions import NotRequired, TypedDict


class RequestOptions(TypedDict, total=False):
    timeout: NotRequired[float]
    """Overrides the client's default timeout for this call only."""

    headers: NotRequired[Mapping[str, str]]
    """Extra headers, merged over the client's default_headers."""

    impersonate_user: NotRequired[str]
    """Sets `x-admin-target-user` for this call. Only takes effect when the
    client is authenticated with a JWT — with an API key the backend
    rejects it with 403 `IMPERSONATION_NOT_ALLOWED`
    (`auth-manager.ts:609` in the Termix source), and the SDK raises
    `PermissionError` from that response rather than trying to guess.
    """

    max_network_retries: NotRequired[int]
    """Overrides the client's default retry count for this call only."""


ADMIN_TARGET_USER_HEADER = "x-admin-target-user"
"""Matches the constant of the same name in Termix's `auth-manager.ts`."""


def request_headers(options: RequestOptions | None) -> Mapping[str, str]:
    if not options:
        return {}
    headers = dict(options.get("headers") or {})
    impersonate = options.get("impersonate_user")
    if impersonate:
        headers[ADMIN_TARGET_USER_HEADER] = impersonate
    return headers

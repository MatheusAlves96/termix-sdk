# Adapted from stripe-python (stripe/_stripe_client.py), MIT License,
# Copyright (c) 2010-2018 Stripe. See NOTICE for the full license text.
"""TermixClient: the sync entry point.

Resource attributes (`client.hosts`, `client.credentials`, ...) are not
here yet — they're wired in by `tools/sdk-gen` once the resource-map exists
(docs/sdk-plan.md phases F3/F4). Everything below is the F1 core: options,
the requestor, a generic low-level `request()` escape hatch, and lifecycle
(`close()`/context manager).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import TracebackType
from typing import TYPE_CHECKING, Any

from ._api_requestor import APIRequestor
from ._client_options import ClientOptions
from ._http_client import HTTPClient
from ._request_options import RequestOptions
from ._response import TermixResponse

# --- generated resource imports start ---

from .resources import credentials as _credentials
from .resources import snippets as _snippets
from .resources import system as _system

# --- generated resource imports end ---

if TYPE_CHECKING:
    from ._auth import PendingTOTP


class TermixClient:
    """
    Example:
        >>> client = TermixClient(base_url="https://termix.example.com", api_key="tmx_...")
        >>> client.request("GET", "/health")
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        jwt: str | None = None,
        service_urls: dict[str, str] | None = None,
        timeout: float = 30.0,
        verify: bool = True,
        max_network_retries: int = 2,
        default_headers: dict[str, str] | None = None,
        _http_client: HTTPClient | None = None,
    ) -> None:
        self._options = ClientOptions(
            base_url=base_url,
            service_urls=service_urls,
            api_key=api_key,
            jwt=jwt,
            timeout=timeout,
            verify=verify,
            max_network_retries=max_network_retries,
            default_headers=default_headers,
        )
        self._requestor = APIRequestor(self._options, http_client=_http_client)

        # --- generated resource attributes start ---

        self.credentials = _credentials.CredentialsService(self._requestor)
        self.snippets = _snippets.SnippetsService(self._requestor)
        self.system = _system.SystemService(self._requestor)

        # --- generated resource attributes end ---

    @classmethod
    def _with_options(cls, options: ClientOptions, requestor: APIRequestor) -> TermixClient:
        """Build a client that shares an existing requestor — used by
        `login()`/TOTP verification (F2) to return a new, JWT-authenticated
        client without re-parsing constructor arguments.
        """
        instance = cls.__new__(cls)
        instance._options = options
        instance._requestor = requestor
        return instance

    @classmethod
    def login(
        cls,
        *,
        base_url: str,
        username: str,
        password: str,
        remember_me: bool = False,
        service_urls: dict[str, str] | None = None,
        timeout: float = 30.0,
        verify: bool = True,
        max_network_retries: int = 2,
        default_headers: dict[str, str] | None = None,
        _http_client: HTTPClient | None = None,
    ) -> TermixClient | PendingTOTP:
        """`POST /users/login`. Returns a ready, JWT-authenticated
        `TermixClient` — or, if the account has TOTP enabled and this
        device isn't already trusted, a `PendingTOTP`: call
        `.verify(code)` on it with the 6-digit code to get the client.
        See `_auth.py` for why this always behaves like a native app
        request under the hood.
        """
        from ._auth import login as _login

        return _login(
            base_url=base_url,
            username=username,
            password=password,
            remember_me=remember_me,
            service_urls=service_urls,
            timeout=timeout,
            verify=verify,
            max_network_retries=max_network_retries,
            default_headers=default_headers,
            _http_client=_http_client,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        service: str | None = None,
        query: Mapping[str, Any] | None = None,
        json_body: Any | None = None,
        files: Mapping[str, Any] | None = None,
        options: RequestOptions | None = None,
    ) -> TermixResponse | None:
        """Low-level escape hatch: call any endpoint the generated resources
        don't cover yet, or that was deliberately left out of the SDK's
        surface (docs/sdk-plan.md section 2, item 10).
        """
        return self._requestor.request(
            method,
            path,
            service=service,
            query=query,
            json_body=json_body,
            files=files,
            options=options,
        )

    def close(self) -> None:
        self._requestor.close()

    def __enter__(self) -> TermixClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
